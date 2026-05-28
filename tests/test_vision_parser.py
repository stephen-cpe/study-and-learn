import os
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def mock_ai(monkeypatch):
    monkeypatch.setenv("AI_MOCK", "true")


@pytest.fixture
def test_png_path(tmp_path):
    from PIL import Image
    img = Image.new("RGB", (100, 100), color="black")
    path = os.path.join(tmp_path, "test.png")
    img.save(path)
    return path


@pytest.fixture
def test_txt_path(tmp_path):
    path = os.path.join(tmp_path, "test.txt")
    with open(path, "w") as f:
        f.write("Hello world. This is a test file.")
    return path


@pytest.fixture
def fixtures_dir():
    return os.path.join(os.path.dirname(__file__), "fixtures")


class TestHashFile:
    def test_same_content(self, test_txt_path):
        from src.services.vision_parser import hash_file
        h1 = hash_file(test_txt_path)
        h2 = hash_file(test_txt_path)
        assert h1 == h2

    def test_different_content(self, tmp_path):
        from src.services.vision_parser import hash_file
        a = os.path.join(tmp_path, "a.txt")
        b = os.path.join(tmp_path, "b.txt")
        with open(a, "w") as f:
            f.write("content A")
        with open(b, "w") as f:
            f.write("content B")
        assert hash_file(a) != hash_file(b)

    def test_empty_file(self, tmp_path):
        from src.services.vision_parser import hash_file
        p = os.path.join(tmp_path, "empty.txt")
        with open(p, "w") as f:
            f.write("")
        result = hash_file(p)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


class TestContentRegistry:
    def test_is_content_registered_none(self):
        with patch("src.services.vision_parser.ContentRegistry") as mock_cr:
            mock_cr.query.filter_by.return_value.first.return_value = None
            from src.services.vision_parser import is_content_registered
            assert is_content_registered("unknown_hash") is None

    def test_is_content_registered_found(self):
        with patch("src.services.vision_parser.ContentRegistry") as mock_cr:
            mock_existing = MagicMock()
            mock_existing.chroma_collection = "doc_dummy123"
            mock_cr.query.filter_by.return_value.first.return_value = mock_existing
            from src.services.vision_parser import is_content_registered
            result = is_content_registered("dummy123")
            assert result == "doc_dummy123"

    def test_register_content_new(self):
        with patch("src.services.vision_parser.ContentRegistry") as mock_cr, \
             patch("src.services.vision_parser.db") as mock_db:
            mock_cr.query.filter_by.return_value.first.return_value = None
            mock_cr.return_value = MagicMock()
            from src.services.vision_parser import register_content
            result = register_content("h" * 64, "sample text")
            assert result.startswith("doc_")
            assert len(result) <= 63

    def test_register_content_existing(self):
        with patch("src.services.vision_parser.ContentRegistry") as mock_cr, \
             patch("src.services.vision_parser.db") as mock_db:
            mock_existing = MagicMock()
            mock_existing.chroma_collection = "doc_existing"
            mock_cr.query.filter_by.return_value.first.return_value = mock_existing
            from src.services.vision_parser import register_content
            result = register_content("h" * 64, "updated text", ocr_text="ocr")
            assert result == "doc_existing"


class TestCollectionName:
    def test_collection_name_length(self):
        from src.services.vector_store import get_collection_name
        h = "a" * 64
        name = get_collection_name(h)
        assert name.startswith("doc_")
        assert len(name) <= 63
        assert len(name) == 4 + 59


class TestOcrPage:
    def test_mock(self, test_png_path):
        from src.services.vision_parser import ocr_page
        result = ocr_page(test_png_path, mode="text")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_invalid_mode(self, test_png_path):
        from src.services.vision_parser import ocr_page
        with pytest.raises(ValueError, match="Unknown OCR mode"):
            ocr_page(test_png_path, mode="invalid")


class TestOcrPageFull:
    def test_full_mock(self, test_png_path, monkeypatch):
        monkeypatch.setenv("OCR_FULL", "true")
        from src.services.vision_parser import ocr_page_full
        result = ocr_page_full(test_png_path)
        assert "[Text OCR]" in result
        assert "[Table OCR]" in result
        assert "[Figure OCR]" in result

    def test_default_text_only(self, test_png_path, monkeypatch):
        monkeypatch.delenv("OCR_FULL", raising=False)
        from src.services.vision_parser import ocr_page_full
        result = ocr_page_full(test_png_path)
        assert "[Text OCR]" in result
        assert "[Table OCR]" not in result
        assert "[Figure OCR]" not in result


class TestDescribeFigure:
    def test_mock(self, test_png_path, monkeypatch):
        monkeypatch.setenv("OCR_FIGURE_DESCRIPTION", "true")
        from src.services.vision_parser import describe_figure
        result = describe_figure(test_png_path)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_disabled_by_default(self, test_png_path, monkeypatch):
        monkeypatch.delenv("OCR_FIGURE_DESCRIPTION", raising=False)
        from src.services.vision_parser import describe_figure
        result = describe_figure(test_png_path)
        assert result == ""


class TestExtractTextWithVision:
    def test_txt_file(self, test_txt_path):
        with patch("src.services.vision_parser.is_content_registered", return_value=None), \
             patch("src.services.vision_parser.register_content"):
            from src.services.document_parser import extract_text_with_vision
            text = extract_text_with_vision(test_txt_path)
            assert "Hello world" in text

    def test_dedup(self, fixtures_dir):
        import os
        pdf_path = os.path.join(fixtures_dir, "sample.pdf")
        with patch("src.services.vision_parser.is_content_registered", return_value="doc_cached"), \
             patch("src.services.vision_parser.ContentRegistry") as mock_cr, \
             patch("src.services.vision_parser.register_content"):
            mock_entry = MagicMock()
            mock_entry.extracted_text = "cached pdf result"
            mock_cr.query.filter_by.return_value.first.return_value = mock_entry

            from src.services.document_parser import extract_text_with_vision
            result = extract_text_with_vision(pdf_path)
            assert result == "cached pdf result"

    def test_image_mock(self, test_png_path):
        with patch("src.services.vision_parser.is_content_registered", return_value=None), \
             patch("src.services.vision_parser.register_content"):
            from src.services.document_parser import extract_text_with_vision
            text = extract_text_with_vision(test_png_path)
            assert isinstance(text, str)

    def test_pdf_single_page(self, fixtures_dir, test_txt_path):
        pdf_path = os.path.join(fixtures_dir, "sample.pdf")
        with patch("src.services.vision_parser.is_content_registered", return_value=None), \
             patch("src.services.vision_parser.register_content"):
            from src.services.document_parser import extract_text_with_vision
            text = extract_text_with_vision(pdf_path)
            assert isinstance(text, str)
            assert len(text) > 0


class TestResize:
    def test_small_image_unchanged(self, test_png_path, monkeypatch):
        monkeypatch.setenv("OCR_MAX_IMAGE_DIMENSION", "2048")
        from src.services.vision_parser import _resize_image_if_needed
        result = _resize_image_if_needed(test_png_path)
        assert result == test_png_path


class TestConcurrentHandling:
    def test_register_content_integrity_error(self, tmp_path):
        with patch("src.services.vision_parser.ContentRegistry") as mock_cr, \
             patch("src.services.vision_parser.db") as mock_db:
            mock_cr.query.filter_by.return_value.first.side_effect = [None, MagicMock(chroma_collection="doc_fallback")]
            mock_cr.return_value = MagicMock()
            mock_db.session.commit.side_effect = Exception("unique constraint")

            from src.services.vision_parser import register_content
            result = register_content("h" * 64, "text")
            assert result == "doc_fallback"
            mock_db.session.rollback.assert_called_once()
