from __future__ import annotations

from typing import Any

def parse_grn_pdf(file_obj) -> dict:
    meta: dict[str, Any] = {"ocr_used": False}
    text = ""
    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
    except Exception:
        text = ""

    if text and text.strip():
        return {"ok": True, "meta": meta, "raw_text": text}

    # Fallback OCR if available
    import shutil
    if not shutil.which("tesseract"):
        return {"ok": False, "code": "UNSUPPORTED_SCAN", "meta": meta}

    try:
        meta["ocr_used"] = True
        # Try pdf2image first
        text_parts: list[str] = []
        try:
            from pdf2image import convert_from_bytes  # type: ignore
            data = file_obj.read()
            pages = convert_from_bytes(data)
            import pytesseract  # type: ignore
            for img in pages:
                text_parts.append(pytesseract.image_to_string(img))
            text = "\n".join(text_parts)
        except Exception:
            # Try fitz (PyMuPDF) as alternate path
            import fitz  # type: ignore
            import pytesseract  # type: ignore
            doc = fitz.open(stream=file_obj.read(), filetype="pdf")
            for page in doc:
                pix = page.get_pixmap()
                import PIL.Image as Image  # type: ignore
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                text_parts.append(pytesseract.image_to_string(img))
            text = "\n".join(text_parts)
        if text.strip():
            return {"ok": True, "meta": meta, "raw_text": text}
    except Exception:
        return {"ok": False, "code": "UNSUPPORTED_SCAN", "meta": meta}

    return {"ok": False, "code": "UNSUPPORTED_SCAN", "meta": meta}

