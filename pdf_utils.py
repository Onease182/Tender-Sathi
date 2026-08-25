# -*- coding: utf-8 -*-
"""Small utility helpers for PDF/file handling — no GUI dependencies.

NOTE: This file was not part of the uploaded set but is imported by
pdf_viewer.py and partner_docs.py. It contains pure logic (no Tkinter /
Qt code), so it is unaffected by the PySide port. Reconstructed here
from usage so the app runs end-to-end — replace with your original
pdf_utils.py if you already have one (it should be a drop-in match).
"""

HAS_FITZ = False
fitz = None


def _ensure_fitz():
    """Lazy-import PyMuPDF on first use to avoid startup penalty."""
    global fitz, HAS_FITZ
    if HAS_FITZ:
        return
    try:
        import fitz as _fitz
        fitz = _fitz
        HAS_FITZ = True
    except ImportError:
        HAS_FITZ = False


def get_fitz():
    """Return the fitz module, importing it on first call if needed.

    IMPORTANT: other modules should call this (or is_fitz_available())
    instead of doing `from pdf_utils import fitz, HAS_FITZ` at import
    time. A plain import grabs the module-level names *before* the lazy
    import below has ever run, so it always sees fitz=None / HAS_FITZ=False
    even when PyMuPDF is installed and working fine.
    """
    _ensure_fitz()
    return fitz


def is_fitz_available():
    """Return True if PyMuPDF is installed and importable, triggering the
    lazy import if it hasn't run yet."""
    _ensure_fitz()
    return HAS_FITZ


def _human_size(num_bytes):
    try:
        num_bytes = float(num_bytes)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024.0:
            return f"{int(num_bytes)} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


def _count_pdf_pages(file_path):
    _ensure_fitz()
    if not file_path or not HAS_FITZ:
        return -1
    if not str(file_path).lower().endswith(".pdf"):
        return -1
    try:
        with fitz.open(file_path) as doc:
            return len(doc)
    except Exception:
        return -1