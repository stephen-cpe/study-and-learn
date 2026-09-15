"""
Figure store — persistent, content-addressed thumbnails for source figures.

The vision pipeline describes figures as text, but the pixels themselves
were discarded (page renders deleted after OCR). This module persists a
downscaled thumbnail per described figure under
``data/figures/<file_hash>/`` with a ``manifest.json`` sidecar, and attaches
figure references to RAG source entries so the deck's sources overlay can
show the original diagrams (circuits, charts, free-body diagrams) behind
the lesson content.

Storage is content-addressed by file hash (like Chroma collections), so
figures are SHARED across users/paths that upload the same file and must
NEVER be deleted by per-path lifecycle routes (complete/cancel/delete).
Only a figure with a non-empty vision caption is persisted — plus every
direct image upload, which IS the figure.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

FIGURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'data', 'figures',
)
FIGURE_MAX_DIMENSION = 1024
FIGURES_PER_SOURCE = 2


def _figures_dir_for(file_hash: str) -> str:
    return os.path.join(FIGURES_DIR, file_hash)


def save_figure(file_hash: str, image_path: str, caption: str = "",
                label: str = "") -> str | None:
    """Persist a downscaled thumbnail + caption. Returns filename or None.

    Never raises — storage failure must never break extraction.
    """
    try:
        if not file_hash or not image_path or not os.path.isfile(image_path):
            return None
        from PIL import Image
        target_dir = _figures_dir_for(file_hash)
        os.makedirs(target_dir, exist_ok=True)
        base = os.path.basename(image_path)
        name, _ext = os.path.splitext(base)
        safe = "".join(c if (c.isalnum() or c in ('-', '_')) else '_' for c in name)[:48]
        filename = f"{safe or 'figure'}.png"
        dest = os.path.join(target_dir, filename)
        counter = 1
        while os.path.exists(dest):
            filename = f"{safe or 'figure'}_{counter}.png"
            dest = os.path.join(target_dir, filename)
            counter += 1
        img = Image.open(image_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > FIGURE_MAX_DIMENSION:
            ratio = FIGURE_MAX_DIMENSION / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        img.save(dest, "PNG")

        manifest_path = os.path.join(target_dir, "manifest.json")
        figures: List[Dict[str, Any]] = []
        try:
            if os.path.isfile(manifest_path):
                with open(manifest_path, encoding="utf-8") as f:
                    figures = json.load(f).get("figures", []) or []
        except Exception:
            figures = []
        figures.append({
            "file": filename,
            "caption": (caption or "").strip(),
            "label": (label or "").strip(),
        })
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump({"file_hash": file_hash, "figures": figures}, f)
        return filename
    except Exception as e:
        logger.warning("save_figure failed for %s: %s", image_path, str(e))
        return None


def get_figures(file_hash: str) -> List[Dict[str, Any]]:
    """Return persisted figures for a file hash ({} list on any error)."""
    try:
        if not file_hash:
            return []
        manifest_path = os.path.join(_figures_dir_for(file_hash), "manifest.json")
        if not os.path.isfile(manifest_path):
            return []
        with open(manifest_path, encoding="utf-8") as f:
            figures = json.load(f).get("figures", []) or []
        out = []
        for fig in figures:
            if not isinstance(fig, dict) or not fig.get("file"):
                continue
            if ".." in fig["file"] or "/" in fig["file"] or "\\" in fig["file"]:
                continue
            full = os.path.join(_figures_dir_for(file_hash), fig["file"])
            if not os.path.isfile(full):
                continue
            out.append({
                "file": fig["file"],
                "caption": fig.get("caption", ""),
                "label": fig.get("label", ""),
            })
        return out
    except Exception as e:
        logger.warning("get_figures failed for %s: %s", str(file_hash)[:8], str(e))
        return []


def figure_url(file_hash: str, filename: str) -> str:
    """Public URL for a persisted figure (served by the figures route)."""
    return f"/figures/{file_hash}/{filename}"


def attach_figures(sources: List[Dict[str, Any]],
                   max_per_source: int = FIGURES_PER_SOURCE) -> List[Dict[str, Any]]:
    """Attach ``figures`` ([{url, caption, label}]) to RAG source entries.

    Looks up each source's ``source_hash`` in the figure store. Mutates and
    returns the list. Never raises.
    """
    try:
        for source in sources or []:
            if not isinstance(source, dict):
                continue
            file_hash = source.get("source_hash", "")
            figs = get_figures(file_hash)[:max(0, max_per_source)]
            if figs:
                source["figures"] = [
                    {
                        "url": figure_url(file_hash, fig["file"]),
                        "caption": fig.get("caption", ""),
                        "label": fig.get("label", ""),
                    }
                    for fig in figs
                ]
        return sources
    except Exception as e:
        logger.warning("attach_figures failed: %s", str(e))
        return sources
