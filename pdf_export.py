# -*- coding: utf-8 -*-
"""Fixed-section PDF splitting + per-page compression for generated bids.

Splits a generated bid PDF into one file per document section (JV
Agreement, Power of Attorney, Letter of Technical Bid, ... one block of
four per partner), each compressed to under 1MB, named after its section.
Sections that span more than one physical page (see MULTI_PAGE_SECTIONS)
are merged into a single output file covering all of their pages, not
split into separate per-page files.
"""

import logging
from pathlib import Path

from pdf_utils import get_fitz, is_fitz_available

logger = logging.getLogger(__name__)

MAX_SIZE_BYTES = 1_000_000  # < 1 MB per split file

# Fixed section sequence. This mirrors the structure baked into
# master_template_2.docx / master_template_3.docx: four shared opening
# sections, followed by four sections per partner in Lead -> First ->
# Second order. The pattern itself is constant across every bid; only the
# number of partner blocks changes (1, 2, or 3), which is already decided
# elsewhere by BidDocumentGenerator.determine_partner_count().
#
# Single-bidder exception: "JV Agreement" and the JV-level "Power of
# Attorney" only apply when there's an actual joint venture. For a
# 1-partner (single bidder) bid, these two sections are removed from the
# template entirely, so they're skipped here too — see build_section_spec.
BASE_SECTIONS = [
    "JV Agreement",
    "Power of Attorney",       # JV-level POA for the Authorized Person
    "Letter of Technical Bid",
    "Letter of Price Bid",
]
# Leading sections in BASE_SECTIONS that are omitted for single-bidder bids.
SINGLE_BIDDER_SKIP_SECTIONS = {"JV Agreement", "Power of Attorney"}
PER_PARTNER_SECTIONS = [
    "Power of Attorney",
    "Self Declaration Certificate",
    "Running Contract Self Declaration",
    "Pending Litigation",
]
PARTNER_LABELS = ["Lead Partner", "First Partner", "Second Partner"]

# Sections that occupy more than one physical page in the generated PDF.
# Every other section is assumed to fit on a single page. These pages are
# NOT split apart — they're merged into one output file per section.
MULTI_PAGE_SECTIONS = {
    "Letter of Technical Bid": 2,
    "Letter of Price Bid": 2,
}


def build_section_spec(partner_count):
    """Return an ordered list of (title, page_count) tuples describing how
    many consecutive source pages belong to each output file, for a bid
    with `partner_count` partners (1, 2, or 3).

    For a single-bidder (partner_count == 1) bid, the JV Agreement and
    JV-level Power of Attorney sections are omitted — they don't exist in
    the single-bidder template."""
    is_single = partner_count <= 1
    base_sections = [
        section for section in BASE_SECTIONS
        if not (is_single and section in SINGLE_BIDDER_SKIP_SECTIONS)
    ]
    spec = [(section, MULTI_PAGE_SECTIONS.get(section, 1)) for section in base_sections]
    for label in PARTNER_LABELS[:max(1, min(partner_count, 3))]:
        for section in PER_PARTNER_SECTIONS:
            title = f"{label} - {section}"
            spec.append((title, MULTI_PAGE_SECTIONS.get(section, 1)))
    return spec


def _safe_filename(title, index):
    cleaned = "".join(c for c in title if c.isalnum() or c in " -_").strip()
    cleaned = cleaned or f"Page {index}"
    return f"{index:02d} - {cleaned}.pdf"


def _compress_pages_under_limit(src_doc, start_page, page_count, max_bytes=MAX_SIZE_BYTES):
    """Return PDF bytes covering src_doc pages [start_page, start_page +
    page_count), downsampling if needed to stay under max_bytes. Plain
    text pages are already tiny; this loop mainly protects sections
    carrying embedded signature/stamp images."""
    fitz = get_fitz()
    end_page = start_page + page_count - 1

    # First attempt: a clean vector copy of the pages (smallest, sharpest).
    merged = fitz.open()
    merged.insert_pdf(src_doc, from_page=start_page, to_page=end_page)
    data = merged.tobytes(deflate=True, garbage=4)
    merged.close()
    if len(data) <= max_bytes:
        return data

    # Fallback: rasterize each page at decreasing DPI until the merged
    # result fits, keeping every page of the section in one file.
    for dpi in (150, 120, 96, 72, 55, 40):
        img_pdf = fitz.open()
        for p in range(start_page, end_page + 1):
            page = src_doc[p]
            pix = page.get_pixmap(dpi=dpi)
            rect = fitz.Rect(0, 0, pix.width, pix.height)
            img_page = img_pdf.new_page(width=pix.width, height=pix.height)
            img_page.insert_image(rect, pixmap=pix)
        data = img_pdf.tobytes(deflate=True, garbage=4)
        img_pdf.close()
        if len(data) <= max_bytes:
            return data

    return data  # best effort — smallest we could achieve


def split_and_compress(pdf_path, partner_count, output_dir):
    """Split `pdf_path` into one file per document section, each
    compressed to under 1 MB, named '<n> - <Section Title>.pdf' in
    `output_dir`. Multi-page sections (see MULTI_PAGE_SECTIONS) are kept
    together as a single merged file rather than split per page.

    Returns (written_paths, warnings). If the PDF has more pages than the
    fixed spec expects, the leftover pages are written out individually as
    'Extra Page N'; if it has fewer, a warning is returned so the caller
    can flag it for review.
    """
    if not is_fitz_available():
        raise RuntimeError("PyMuPDF (fitz) is required to split PDFs.")

    fitz = get_fitz()
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    spec = build_section_spec(partner_count)
    expected_pages = sum(count for _, count in spec)
    warnings = []
    written = []

    with fitz.open(str(pdf_path)) as doc:
        page_count = len(doc)

        if page_count != expected_pages:
            message = (
                f"Expected {expected_pages} pages for a {partner_count}-partner "
                f"bid but the generated PDF has {page_count}. Splitting will "
                "continue in best-effort mode; please review the output."
            )
            warnings.append(message)
            logger.warning(message)

        cursor = 0
        file_index = 1
        for title, count in spec:
            if cursor >= page_count:
                break
            actual_count = min(count, page_count - cursor)
            data = _compress_pages_under_limit(doc, cursor, actual_count)
            out_path = output_dir / _safe_filename(title, file_index)
            out_path.write_bytes(data)
            written.append(out_path)
            logger.info(f"Wrote {out_path.name} ({len(data)/1024:.0f} KB)")
            cursor += actual_count
            file_index += 1

        # Any pages beyond what the fixed spec accounted for (PDF longer
        # than expected) get written out individually so nothing is lost.
        while cursor < page_count:
            data = _compress_pages_under_limit(doc, cursor, 1)
            out_path = output_dir / _safe_filename(f"Extra Page {cursor + 1}", file_index)
            out_path.write_bytes(data)
            written.append(out_path)
            logger.info(f"Wrote {out_path.name} ({len(data)/1024:.0f} KB)")
            cursor += 1
            file_index += 1

    return written, warnings