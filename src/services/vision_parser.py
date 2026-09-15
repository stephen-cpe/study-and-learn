import base64
import hashlib
import logging
import os
from typing import List, Optional, Tuple

from PIL import Image

from config_defaults import (
    PDF_NEEDS_OCR_MIN_CHARS_PER_PAGE_DEFAULT,
    PDF_NEEDS_OCR_MIN_TOTAL_CHARS_DEFAULT,
    VISION_MODEL_DEFAULT,
    env_default,
    env_int,
)
from src import db
from src.models import ContentRegistry
from src.services.ai_client import call_ollama
from src.services.exceptions import AIModelUnavailableError
from src.services.vector_store import get_collection_name

logger = logging.getLogger(__name__)


def _encode_image(image_path: str) -> Optional[str]:
    """Read an image file and return its base64-encoded string.

    This is required for Ollama vision models — the ``/api/generate``
    endpoint expects an ``images`` array of base64 strings. Embedding a
    file path in the prompt text does NOT work; the model cannot read
    local files. Returns None if the file cannot be read (caller should
    skip the vision call in that case).
    """
    try:
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        logger.warning("Failed to base64-encode image %s: %s", image_path, str(e))
        return None


# Vision model default (the value lives in config_defaults.py as
# VISION_MODEL_DEFAULT). OCR and figure description are consolidated onto
# this single natively multimodal model (glm-5.3-flash:cloud) — the old
# local-only ``glm-ocr`` path has been removed. If the model is unreachable
# on the active Ollama backend, callers should expect a soft failure
# (empty string) + a WARNING log from :func:`probe_vision_model_availability`
# instead of a hard error.
_DEFAULT_VISION_MODEL = VISION_MODEL_DEFAULT


def _ocr_enabled() -> bool:
    """Return True unless OCR was explicitly disabled.

    Vision OCR defaults to ON. Only an explicit falsy
    ``OCR_FULL`` (false/0/no/off) disables it — unset or empty means
    enabled. This preserves the ``OCR_FULL=false`` opt-out used in tests
    while making capability-on the default.
    """
    raw = os.environ.get("OCR_FULL")
    if raw is None or raw.strip() == "":
        return True
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _figure_enabled() -> bool:
    """Return True unless figure descriptions were explicitly disabled."""
    raw = os.environ.get("OCR_FIGURE_DESCRIPTION")
    if raw is None or raw.strip() == "":
        return True
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _pdf_needs_vision_ocr(file_path: str, basic_text: str = "") -> bool:
    """Decide whether a PDF actually needs vision OCR.

    Text-layer PDFs (the common case — e.g. all 7 current uploads at
    21k-46k chars) skip expensive page rendering + LLM calls entirely.
    Vision OCR runs only when the PDF looks scanned/image-heavy:

    * almost no extractable text (<MIN_TOTAL_CHARS), or
    * sparse text (<MIN_CHARS_PER_PAGE on average), or
    * embedded raster images outnumber pages ("lots of images").

    Never raises — on any inspection error returns True (safe side: run
    vision rather than silently dropping content).
    """
    try:
        total_chars = len((basic_text or "").strip())
        min_total = env_int(
            "PDF_NEEDS_OCR_MIN_TOTAL_CHARS",
            PDF_NEEDS_OCR_MIN_TOTAL_CHARS_DEFAULT,
        )
        min_per_page = env_int(
            "PDF_NEEDS_OCR_MIN_CHARS_PER_PAGE",
            PDF_NEEDS_OCR_MIN_CHARS_PER_PAGE_DEFAULT,
        )
        if total_chars < min_total:
            return True

        from pypdf import PdfReader
        reader = PdfReader(file_path)
        num_pages = len(reader.pages) or 1
        if (total_chars / num_pages) < min_per_page:
            return True

        try:
            image_count = 0
            for page in reader.pages:
                resources = page.get("/Resources")
                if not resources:
                    continue
                xobjects = resources.get("/XObject")
                if not xobjects:
                    continue
                try:
                    xobjects = xobjects.get_object()
                except Exception:
                    pass
                if not hasattr(xobjects, "keys"):
                    continue
                for key in xobjects.keys():
                    try:
                        obj = xobjects[key]
                        try:
                            obj = obj.get_object()
                        except Exception:
                            pass
                        subtype = obj.get("/Subtype") if hasattr(obj, "get") else None
                        if str(subtype) == "/Image":
                            image_count += 1
                    except Exception:
                        continue
            if image_count >= num_pages and num_pages > 0:
                logger.info(
                    "PDF %s has %d embedded images across %d pages — "
                    "enabling vision OCR for figures/diagrams",
                    os.path.basename(file_path), image_count, num_pages,
                )
                return True
        except Exception as e:
            logger.debug("PDF image-count probe failed for %s: %s", file_path, str(e))

        return False
    except Exception as e:
        logger.debug("PDF vision-OCR gate failed for %s: %s", file_path, str(e))
        return True

# Tracks whether the warning has been logged once per process to avoid
# log spam when the vision model is called repeatedly.
_vision_availability_warned = ""


def probe_vision_model_availability(model: Optional[str] = None) -> bool:
    """Best-effort startup probe for the configured vision model.

    Logs a WARNING and returns ``False`` if the model appears unavailable
    on the active Ollama backend. Returns ``True`` otherwise. Never raises.

    Skipped entirely when ``AI_MOCK=true`` (CI/tests). The probe is lazy and
    idempotent — a WARN is logged at most once per process per model name
    to avoid log spam on repeated calls.

    This is a soft check: it does not block app startup. Real vision
    requests will still attempt the call and degrade gracefully via the
    existing try/except wrappers in :func:`ocr_page` and
    :func:`describe_figure`.
    """
    global _vision_availability_warned

    if os.environ.get("AI_MOCK", "").lower() == "true":
        return True

    if model is None:
        model = env_default("OLLAMA_VISION_MODEL", _DEFAULT_VISION_MODEL)

    probe_key = f"{model}"
    if _vision_availability_warned.startswith(f"{probe_key}:"):
        return not _vision_availability_warned.endswith(":unavailable")
    _vision_availability_warned = f"{probe_key}:probing"

    try:
        # Minimal prompt — we only care that the model is reachable and
        # accepts an image-bearing request without returning a "model not
        # found" style error.
        call_ollama(
            "Image: probe\n\nRespond with the single word: ok",
            model=model,
        )
        _vision_availability_warned = f"{probe_key}:available"
        return True
    except AIModelUnavailableError as e:
        hint = (
            f"The consolidated vision model '{model}' is not reachable on "
            f"the active Ollama backend. OCR and figure descriptions will "
            f"degrade to empty strings. If you are using Ollama Cloud, "
            f"confirm `AI_BACKEND=cloud` is set and your API key is valid."
        )
        logger.warning("%s Underlying error: %s", hint, str(e))
        _vision_availability_warned = f"{probe_key}:unavailable"
        return False
    except Exception as e:
        # Non-fatal: the probe is best-effort. Real calls will surface
        # the real error and fall back to empty string.
        logger.debug(
            "Vision model probe returned non-fatal error for '%s': %s",
            model, str(e),
        )
        _vision_availability_warned = f"{probe_key}:available"
        return True


def hash_file(file_path: str) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def is_content_registered(file_hash: str) -> Optional[str]:
    existing = ContentRegistry.query.filter_by(file_hash=file_hash).first()
    if existing:
        return existing.chroma_collection
    return None


def register_content(file_hash: str, extracted_text: str) -> str:
    collection_name = get_collection_name(file_hash)
    existing = ContentRegistry.query.filter_by(file_hash=file_hash).first()
    if existing:
        existing.extracted_text = extracted_text
        db.session.commit()
        return existing.chroma_collection

    entry = ContentRegistry(
        file_hash=file_hash,
        chroma_collection=collection_name,
        extracted_text=extracted_text,
    )
    db.session.add(entry)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        existing = ContentRegistry.query.filter_by(file_hash=file_hash).first()
        if existing:
            return existing.chroma_collection
        raise
    return collection_name


def _get_poppler_path() -> Optional[str]:
    env_poppler = os.environ.get("POPPLER_PATH", "")
    if env_poppler and os.path.isdir(env_poppler):
        return env_poppler

    possible = [
        r"C:\Program Files\poppler\Library\bin",
        r"C:\Program Files\poppler\bin",
        r"C:\poppler\Library\bin",
        r"C:\poppler\bin",
    ]
    for p in possible:
        if os.path.isdir(p):
            return p
    return None



def render_pdf_pages(file_path: str, output_dir: str) -> List[str]:
    poppler_path = _get_poppler_path()
    kwargs = {}
    if poppler_path:
        kwargs["poppler_path"] = poppler_path

    from pdf2image import convert_from_path
    from pdf2image.exceptions import PDFInfoNotInstalledError
    try:
        images = convert_from_path(file_path, dpi=200, **kwargs)
    except PDFInfoNotInstalledError:
        logger.warning("Poppler not found — cannot render PDF pages. Install poppler-utils.")
        return []

    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for i, img in enumerate(images):
        out_path = os.path.join(output_dir, f"page_{i + 1}.png")
        img.save(out_path, "PNG")
        paths.append(out_path)
    return paths


def extract_docx_images(file_path: str, output_dir: str) -> List[str]:
    try:
        from docx import Document
    except ImportError:
        logger.warning("python-docx not available for image extraction")
        return []

    doc = Document(file_path)
    os.makedirs(output_dir, exist_ok=True)
    paths = []

    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            image = rel.target_part
            ext = os.path.splitext(image.partname)[-1] or ".png"
            out_path = os.path.join(output_dir, f"docx_image_{image.partname.replace('/', '_')}{ext}")
            with open(out_path, "wb") as f:
                f.write(image.blob)
            try:
                img = Image.open(out_path)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                png_path = os.path.splitext(out_path)[0] + ".png"
                img.save(png_path, "PNG")
                if png_path != out_path:
                    paths.append(png_path)
                else:
                    paths.append(out_path)
            except Exception:
                paths.append(out_path)

    return paths


def extract_pptx_content(file_path: str, output_dir: str) -> Tuple[str, List[str]]:
    try:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE
    except ImportError:
        logger.warning("python-pptx not available")
        return "", []

    prs = Presentation(file_path)
    text_parts = []
    os.makedirs(output_dir, exist_ok=True)
    slide_images = []

    for i, slide in enumerate(prs.slides):
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    if paragraph.text.strip():
                        text_parts.append(paragraph.text)

            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                try:
                    image = shape.image
                    ext = image.content_type.split("/")[-1]
                    if ext == "jpeg":
                        ext = "jpg"
                    img_path = os.path.join(
                        output_dir, f"slide_{i + 1}_img_{len(slide_images)}.{ext}"
                    )
                    with open(img_path, "wb") as f:
                        f.write(image.blob)
                    try:
                        img = Image.open(img_path)
                        if img.mode != "RGB":
                            img = img.convert("RGB")
                        png_path = os.path.splitext(img_path)[0] + ".png"
                        img.save(png_path, "PNG")
                        if png_path != img_path:
                            os.remove(img_path)
                        slide_images.append(png_path)
                    except Exception:
                        slide_images.append(img_path)
                except Exception:
                    pass

    return "\n".join(text_parts), slide_images


def _resize_image_if_needed(image_path: str) -> str:
    max_dim = int(os.environ.get("OCR_MAX_IMAGE_DIMENSION", "2048"))
    try:
        img = Image.open(image_path)
        w, h = img.size
        if w <= max_dim and h <= max_dim:
            return image_path
        ratio = min(max_dim / w, max_dim / h)
        new_size = (int(w * ratio), int(h * ratio))
        img = img.resize(new_size, Image.LANCZOS)
        img.save(image_path)
    except Exception as e:
        logger.warning("Failed to resize image %s: %s", image_path, str(e))
    return image_path


def ocr_page(image_path: str, mode: str = "text") -> str:
    max_bytes = int(os.environ.get("OCR_MAX_FILE_BYTES", str(50 * 1024 * 1024)))
    file_size = os.path.getsize(image_path)
    if file_size > max_bytes:
        logger.warning(
            "Skipping OCR for %s: file size %d exceeds OCR_MAX_FILE_BYTES (%d)",
            image_path, file_size, max_bytes,
        )
        return ""
    _resize_image_if_needed(image_path)
    abs_path = os.path.abspath(image_path)

    mode_prompts = {
        "text": "Extract all text visible in this image. Return only the extracted text, no commentary.",
        "table": "Extract any tables visible in this image. Preserve row/column structure. Return only the table content.",
        "figure": "Describe the figure, diagram, or chart visible in this image. Focus on visual elements, labels, and structure.",
    }
    if mode not in mode_prompts:
        raise ValueError(f"Unknown OCR mode: {mode}. Use 'text', 'table', or 'figure'.")

    prompt = mode_prompts[mode]
    # Consolidated: all OCR modes use the single vision model
    # (glm-5.3-flash:cloud) via the active backend — no more local-only
    # ``glm-ocr`` + ``force_local`` split.
    model = env_default("OLLAMA_VISION_MODEL", _DEFAULT_VISION_MODEL)

    b64_image = _encode_image(abs_path)
    if not b64_image:
        return ""

    try:
        result = call_ollama(prompt, model=model, images=[b64_image])
        return result.strip() if result else ""
    except Exception as e:
        logger.warning("OCR %s mode failed for %s: %s", mode, image_path, str(e))
        return ""


def ocr_page_full(image_path: str) -> str:
    run_full = _ocr_enabled()
    # When OCR is explicitly disabled (OCR_FULL=false) this helper still
    # honors the legacy contract used in tests: text-only single pass.
    # When enabled (the default), run the consolidated text+table+figure
    # passes through the single vision model.
    modes = ["text", "table", "figure"] if run_full else ["text"]
    parts = []
    for mode in modes:
        try:
            result = ocr_page(image_path, mode=mode)
            if result and result.strip():
                label = {"text": "Text", "table": "Table", "figure": "Figure"}[mode]
                parts.append(f"[{label} OCR]\n{result}")
        except Exception as e:
            logger.warning("OCR %s mode error on %s: %s", mode, image_path, str(e))

    return "\n\n".join(parts)


def describe_figure(image_path: str) -> str:
    if not _figure_enabled():
        return ""

    _resize_image_if_needed(image_path)
    abs_path = os.path.abspath(image_path)

    model = os.environ.get("OLLAMA_VISION_MODEL", _DEFAULT_VISION_MODEL)

    # Best-effort availability check. Logs a WARNING once per process if
    # the configured model is unreachable on Ollama Cloud. Never raises.
    probe_vision_model_availability(model)

    prompt = (
        "Describe what this figure explains in 2-3 sentences, focusing on the key concepts "
        "and how they relate to each other. Include any labels, axis titles, or annotations "
        "visible in the figure."
    )

    b64_image = _encode_image(abs_path)
    if not b64_image:
        return ""

    try:
        result = call_ollama(prompt, model=model, images=[b64_image])
        return result.strip() if result else ""
    except Exception as e:
        logger.warning("Figure description failed for %s: %s", image_path, str(e))
        return ""


def extract_text_with_vision(file_path: str, progress_callback=None) -> str:
    from src.services.document_parser import extract_text as _basic_extract

    ext = os.path.splitext(file_path)[1].lower()

    file_hash = hash_file(file_path)
    existing_collection = is_content_registered(file_hash)
    if existing_collection:
        entry = ContentRegistry.query.filter_by(file_hash=file_hash).first()
        if entry and entry.extracted_text:
            logger.info("Content already registered for hash %s, returning cached text", file_hash)
            return entry.extracted_text

    parts = []

    try:
        basic_text = _basic_extract(file_path)
        if basic_text and basic_text.strip():
            parts.append(basic_text)
    except Exception as e:
        logger.warning("Basic text extraction failed for %s: %s", file_path, str(e))

    if ext in ('.txt', '.md'):
        result = basic_text if parts else ""
        register_content(file_hash, result)
        return result

    ocr_enabled = _ocr_enabled()

    if not ocr_enabled and ext in ('.pdf', '.docx', '.pptx'):
        result = "\n\n".join(parts) if parts else ""
        if not result or not result.strip():
            result = ""
        register_content(file_hash, result)
        return result

    # Smart gate: text-layer PDFs skip vision entirely. Vision OCR runs
    # only when the PDF actually needs it (scanned / image-heavy / sparse
    # text). This keeps OCR capability ON by default without paying LLM
    # cost on plain-text documents.
    if ocr_enabled and ext == '.pdf':
        basic_joined = "\n\n".join(parts) if parts else ""
        if not _pdf_needs_vision_ocr(file_path, basic_joined):
            logger.info(
                "Skipping vision OCR for %s: text layer sufficient "
                "(%d chars), no image-heavy pages detected",
                os.path.basename(file_path), len(basic_joined.strip()),
            )
            result = basic_joined if basic_joined.strip() else ""
            register_content(file_hash, result)
            return result
        logger.info(
            "Vision OCR triggered for %s: scanned or image-heavy PDF detected",
            os.path.basename(file_path),
        )

    output_dir = os.path.join(os.path.dirname(file_path), "_ocr_temp")
    os.makedirs(output_dir, exist_ok=True)

    total_pages = 0
    page_images = []

    if ext == '.pdf':
        page_images = render_pdf_pages(file_path, output_dir)
        total_pages = len(page_images)
    elif ext == '.docx':
        docx_imgs = extract_docx_images(file_path, output_dir)
        page_images = docx_imgs
        total_pages = len(page_images)
    elif ext == '.pptx':
        pptx_text, slide_imgs = extract_pptx_content(file_path, output_dir)
        if pptx_text and pptx_text.strip():
            parts.append(pptx_text)
        page_images = slide_imgs
        total_pages = len(page_images)
    elif ext in ('.png', '.jpg', '.jpeg'):
        page_images = [file_path]
        total_pages = 1

    ocr_outputs = []
    figure_outputs = []
    # (image path, page label, figure caption) for figure persistence.
    figure_candidates = []

    for i, img_path in enumerate(page_images):
        try:
            if progress_callback:
                progress_callback("ocr", i + 1, total_pages)

            ocr_result = ocr_page_full(img_path)
            if ocr_result:
                ocr_outputs.append(ocr_result)
        except Exception as e:
            logger.warning("OCR failed for %s: %s", img_path, str(e))

        fig_desc = ""
        try:
            if progress_callback:
                progress_callback("figure", i + 1, total_pages)

            fig_desc = describe_figure(img_path)
            if fig_desc:
                figure_outputs.append(f"[Figure Description]\n{fig_desc}")
        except Exception as e:
            logger.warning("Figure description failed for %s: %s", img_path, str(e))

        if ext in ('.png', '.jpg', '.jpeg'):
            label = os.path.basename(file_path)
        else:
            label = f"{os.path.basename(file_path)} — page {i + 1}"
        # Persist the pixels when vision described something, or always for
        # direct image uploads (the upload IS the figure). Must run BEFORE
        # temp cleanup deletes page renders below.
        if fig_desc or ext in ('.png', '.jpg', '.jpeg'):
            figure_candidates.append((img_path, label, fig_desc or ""))

    try:
        from src.services.figure_store import save_figure as _save_figure
        for img_path, label, caption in figure_candidates:
            _save_figure(file_hash, img_path, caption=caption, label=label)
    except Exception as e:
        logger.warning("Figure persistence failed for %s: %s", file_path, str(e))

    if ocr_outputs:
        parts.append("[BEGIN OCR OUTPUT]\n" + "\n\n".join(ocr_outputs) + "\n[END OCR OUTPUT]")
    if figure_outputs:
        parts.append("[BEGIN FIGURE DESCRIPTIONS]\n" + "\n\n".join(figure_outputs) + "\n[END FIGURE DESCRIPTIONS]")

    result = "\n\n".join(parts)
    if not result or not result.strip():
        if parts:
            result = parts[0]
        else:
            result = ""

    register_content(file_hash, result)

    for img_path in page_images:
        try:
            if os.path.exists(img_path) and img_path != file_path:
                os.remove(img_path)
        except Exception:
            pass
    try:
        if os.path.exists(output_dir) and output_dir != os.path.dirname(file_path):
            remaining = os.listdir(output_dir)
            if not remaining:
                os.rmdir(output_dir)
    except Exception:
        pass

    return result
