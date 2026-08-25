# -*- coding: utf-8 -*-
"""
BidDocumentGenerator — placeholder replacement, image replacement,
table cleanup, and document generation. Pure document logic, no Tkinter.
"""

import os
import re
import shutil
import subprocess
import tempfile
import logging
from pathlib import Path
from datetime import datetime

from docx import Document
from lxml import etree

logger = logging.getLogger(__name__)


class BidDocumentGenerator:
    """Core logic for generating bid documents."""

    def __init__(self, base_path):
        self.base_path = Path(base_path)
        self.ensure_dirs()

    def ensure_dirs(self):
        for dir_name in ["templates", "output", "assets"]:
            (self.base_path / dir_name).mkdir(parents=True, exist_ok=True)

    def is_empty_value(self, value):
        if value is None:
            return True
        return str(value).strip() == ""

    def replace_text_in_paragraph(self, paragraph, key, value):
        if key not in paragraph.text:
            return
            
        # FIX 2: Replace with empty string if empty, so we don't leave raw {{KEY}} tags in the doc
        val = "" if self.is_empty_value(value) else str(value)
        full_text = paragraph.text.replace(key, val)
        
        if paragraph.runs:
            first_run = paragraph.runs[0]
            paragraph.clear()
            new_run = paragraph.add_run(full_text)
            new_run.bold = first_run.bold
            new_run.italic = first_run.italic
            if first_run.font.name:
                new_run.font.name = first_run.font.name
            if first_run.font.size:
                new_run.font.size = first_run.font.size

    def replace_all_in_paragraph(self, paragraph, placeholders):
        """Replace every placeholder found in a single paragraph."""
        
        # FIX 2: Try to replace within individual runs to preserve formatting
        for run in paragraph.runs:
            for key, value in placeholders.items():
                if key in run.text:
                    val = "" if self.is_empty_value(value) else str(value)
                    run.text = run.text.replace(key, val)
        
        # Fallback for placeholders that span multiple runs
        full_text = paragraph.text
        remaining_keys = {
            k: v for k, v in placeholders.items() 
            if k in full_text
        }
        
        if not remaining_keys:
            return
            
        new_text = full_text
        for key, value in remaining_keys.items():
            val = "" if self.is_empty_value(value) else str(value)
            new_text = new_text.replace(key, val)
            
        if paragraph.runs:
            first_run = paragraph.runs[0]
            paragraph.clear()
            new_run = paragraph.add_run(new_text)
            new_run.bold = first_run.bold
            new_run.italic = first_run.italic
            if first_run.font.name:
                new_run.font.name = first_run.font.name
            if first_run.font.size:
                new_run.font.size = first_run.font.size

    def _clear_table_cell(self, cell):
        for p in cell.paragraphs:
            for run in p.runs:
                run.text = ""
        for child in list(cell._element):
            tag = etree.QName(child).localname if hasattr(child, 'tag') else ""
            if tag not in ("p", "tbl", "tcPr"):
                child.getparent().remove(child)

    def clean_empty_partner_sections(self, doc, bid_data):
       """Remove paragraphs and table cells containing empty partner
       placeholders, and blank out whole signature-block columns for any
       signatory (CEO/MD1/MD2) whose name field is empty."""

       shared_fields = []   # duplicated identically across every column
       signatory_fields = []  # unique to one column
       for prefix in ("LEAD", "FIRST", "SECOND"):
           shared_fields += [f"{prefix}_PARTNER_NAME", f"{prefix}_PARTNER_SHORT", f"{prefix}_ADDRESS"]
           signatory_fields += [f"{prefix}_PARTNER_CEO", f"{prefix}_PARTNER_MD1", f"{prefix}_PARTNER_MD2"]

       empty_shared = [f for f in shared_fields if self.is_empty_value(bid_data.get(f))]
       empty_signatory = {f for f in signatory_fields if self.is_empty_value(bid_data.get(f))}

       if not empty_shared and not empty_signatory:
           return

       shared_placeholders = []
       for field in empty_shared:
           shared_placeholders.extend([f"{{{{{field}}}}}", field])

       all_empty_placeholders = list(shared_placeholders)
       for field in empty_signatory:
           all_empty_placeholders.extend([f"{{{{{field}}}}}", field])

       paragraphs_to_remove = []
       for paragraph in doc.paragraphs:
           for ph in all_empty_placeholders:
               if ph in paragraph.text:
                   paragraphs_to_remove.append(paragraph)
                   break
       for p in paragraphs_to_remove:
           p._element.getparent().remove(p._element)

       for table in doc.tables:
           # Map column index -> the signatory field that owns it, by
           # scanning every row (the placeholder only appears once, but
           # we don't know which row ahead of time).
           column_field = {}
           for row in table.rows:
               if len(row.cells) == 1:
                   continue
               for col_idx, cell in enumerate(row.cells):
                   for field in signatory_fields:
                       if f"{{{{{field}}}}}" in cell.text:
                           column_field[col_idx] = field
                           break

           columns_to_clear = {
               col_idx for col_idx, field in column_field.items()
               if field in empty_signatory
           }

           for row in list(table.rows):
               if len(row.cells) == 1:
                   cell_text = row.cells[0].text
                   for ph in all_empty_placeholders:
                       if ph in cell_text:
                           table._element.remove(row._element)
                           break
                   continue

               for col_idx, cell in enumerate(row.cells):
                   if col_idx in columns_to_clear:
                       self._clear_table_cell(cell)
                   elif shared_placeholders:
                       for ph in shared_placeholders:
                           if ph in cell.text:
                               self._clear_table_cell(cell)
                               break

   # ------------------------------------------------------------------
   # FIX BUG 1: Use exact placeholder matching, not substring
  
    def remove_partner_blocks(self, doc, partner_prefix):
        paragraphs_to_remove = []
        for paragraph in doc.paragraphs:
            text = paragraph.text
            if f"{{{{{partner_prefix}_" in text or f"{partner_prefix}_" in text:
                paragraphs_to_remove.append(paragraph)
        for p in paragraphs_to_remove:
            try:
                p._element.getparent().remove(p._element)
            except Exception:
                pass

        for table in doc.tables:
            rows_to_remove = []
            for row in table.rows:
                for cell in row.cells:
                    cell_text = cell.text
                    if f"{{{{{partner_prefix}_" in cell_text or f"{partner_prefix}_" in cell_text:
                        rows_to_remove.append(row)
                        break
            for row in rows_to_remove:
                try:
                    table._element.remove(row._element)
                except Exception:
                    pass

    def replace_in_document(self, doc, placeholders):
        for p in doc.paragraphs:
            self.replace_all_in_paragraph(p, placeholders)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        self.replace_all_in_paragraph(p, placeholders)
        for section in doc.sections:
            for p in section.header.paragraphs:
                self.replace_all_in_paragraph(p, placeholders)
            for p in section.footer.paragraphs:
                self.replace_all_in_paragraph(p, placeholders)

    def _all_paragraphs(self, doc):
        """Yield paragraphs from document body, tables, headers, and footers."""
        yield from doc.paragraphs
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    yield from cell.paragraphs
        for section in doc.sections:
            yield from section.header.paragraphs
            yield from section.footer.paragraphs

    def unresolved_placeholders(self, doc):
        """Return unresolved {{PLACEHOLDER}} tokens after replacement."""
        found = set()
        for paragraph in self._all_paragraphs(doc):
            found.update(re.findall(r"\{\{[^{}]+\}\}", paragraph.text))
        return sorted(found)

    _EMBED_ATTR = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed'

    def replace_images_batch(self, doc, image_mapping, remove_keys=None):
        """Replace images and remove only explicitly requested alt-text keys."""
        replacements = 0
        remove_keys = set(remove_keys or ())

        def process_paragraph(paragraph):
            nonlocal replacements
            part = paragraph.part
            for run in paragraph.runs:
                for drawing in run._element.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing'):
                    for blip in drawing.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}blip'):
                        embed = blip.get(self._EMBED_ATTR)
                        if not embed:
                            continue
                        docPr = drawing.find('.//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}docPr')
                        if docPr is None:
                            continue
                        alt_text = docPr.get('descr') or docPr.get('title') or ''
                        candidate_keys = set(image_mapping).union(remove_keys)
                        matches = [key for key in candidate_keys if key.upper() in alt_text.upper()]
                        if not matches:
                            continue
                        # Prefer the most specific role-qualified key if an
                        # alt text contains more than one searchable token.
                        key = max(matches, key=len)
                        if key in remove_keys:
                            drawing_parent = drawing.getparent()
                            if drawing_parent is not None:
                                drawing_parent.remove(drawing)
                                replacements += 1
                                logger.info(f"Removed image with alt text matching {key}")
                            break
                        img_path = image_mapping.get(key)
                        if img_path and os.path.exists(img_path):
                            try:
                                new_rId, _image = part.get_or_add_image(img_path)
                                blip.set(self._EMBED_ATTR, new_rId)
                                replacements += 1
                            except Exception as e:
                                logger.error(f"Failed to replace image {key}: {e}")
                        break

        for p in doc.paragraphs:
            process_paragraph(p)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        process_paragraph(p)
        for section in doc.sections:
            for p in section.header.paragraphs:
                process_paragraph(p)
            for p in section.footer.paragraphs:
                process_paragraph(p)
        return replacements

    def determine_partner_count(self, data):
        if data.get("BID_TYPE") == "Single Bidder":
            lead_name = data.get("LEAD_PARTNER_NAME", "")
            if self.is_empty_value(lead_name):
                raise ValueError("Lead partner name is required for single bidder.")
            return 1
        lead_name = data.get("LEAD_PARTNER_NAME", "")
        first_name = data.get("FIRST_PARTNER_NAME", "")
        second_name = data.get("SECOND_PARTNER_NAME", "")
        lead_present = not self.is_empty_value(lead_name)
        first_present = not self.is_empty_value(first_name)
        second_present = not self.is_empty_value(second_name)
        if not lead_present:
            raise ValueError("At least the lead partner must be filled to generate the bid.")
        if second_present and not first_present:
            raise ValueError("The first partner must be filled before the second partner.")
        return 3 if second_present else 2 if first_present else 1

    def select_template(self, partner_count):
        if partner_count == 1:
            template_name = "master_template_1.docx"
            if not (self.base_path / "templates" / template_name).exists():
                template_name = "master_template_2.docx"
            return template_name
        elif partner_count == 2:
            return "master_template_2.docx"
        else:
            return "master_template_3.docx"

    def generate(self, data, image_mapping):
        partner_count = self.determine_partner_count(data)
        template_name = self.select_template(partner_count)
        template_path = self.base_path / "templates" / template_name

        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        doc = Document(template_path)

        if partner_count == 1:
            self.remove_partner_blocks(doc, "FIRST")
            self.remove_partner_blocks(doc, "SECOND")
        elif partner_count == 2:
            self.remove_partner_blocks(doc, "SECOND")

        self.clean_empty_partner_sections(doc, data)

        placeholders = {f"{{{{{k}}}}}": v for k, v in data.items()}
        self.replace_in_document(doc, placeholders)
        image_mapping = dict(image_mapping or {})
        # Build an explicit role-specific removal set. Do not add deletion
        # sentinels to image_mapping, because that can collide with stale or
        # cross-role image assignments.
        remove_image_keys = set()
        for prefix in ("LEAD", "FIRST", "SECOND"):
            for suffix in ("PARTNER_MD1", "PARTNER_MD2"):
                key = f"{prefix}_{suffix}"
                if self.is_empty_value(data.get(key)):
                    remove_image_keys.add(key)
        self.replace_images_batch(doc, image_mapping, remove_keys=remove_image_keys)
        unresolved = self.unresolved_placeholders(doc)
        if unresolved:
            raise ValueError(
                "The selected template contains unresolved placeholders: "
                + ", ".join(unresolved)
            )
        jv_name = data.get("JV_NAME", "bid")
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', jv_name)[:50].strip('_')
        if not safe_name:
            safe_name = "bid"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"generated_bid_{safe_name}_{timestamp}.docx"
        
        output_path = self.base_path / "output" / output_filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Save first to a temporary file, then replace the destination atomically.
        with tempfile.NamedTemporaryFile(
            prefix=".bid_", suffix=".docx", dir=output_path.parent, delete=False
        ) as tmp:
            temp_path = Path(tmp.name)
        try:
            doc.save(str(temp_path))
            temp_path.replace(output_path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
        return output_path

    def convert_to_pdf(self, docx_path):
        """Convert a generated .docx to .pdf for preview/splitting.

        Tries docx2pdf first (uses Microsoft Word — works on Windows/Mac,
        matches this app's existing environment). Falls back to LibreOffice
        headless conversion if docx2pdf/Word isn't available.
        """
        docx_path = Path(docx_path)
        pdf_path = docx_path.with_suffix(".pdf")

        try:
            from docx2pdf import convert as _docx2pdf_convert
            _docx2pdf_convert(str(docx_path), str(pdf_path))
            if pdf_path.exists():
                return pdf_path
        except Exception as e:
            logger.warning(f"docx2pdf conversion failed, trying LibreOffice: {e}")

        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if soffice:
            subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf",
                 "--outdir", str(docx_path.parent), str(docx_path)],
                check=True, timeout=120,
            )
            if pdf_path.exists():
                return pdf_path

        raise RuntimeError(
            "Could not convert the document to PDF. Install Microsoft Word "
            "(for docx2pdf) or LibreOffice, then try again."
        )