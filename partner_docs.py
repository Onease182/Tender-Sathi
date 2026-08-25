# -*- coding: utf-8 -*-
"""Partner-document section builder and refresh/upload/remove logic."""

import os
import logging

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QMessageBox,
)

from pdf_utils import _human_size, _count_pdf_pages
import profiles

logger = logging.getLogger(__name__)


class PartnerDocsMixin:
    """Inline per-partner supporting-documents UI + state."""

    def _build_partner_docs_section(self, grid_layout, role):
        if not hasattr(self, "partner_docs_widgets"):
            self.partner_docs_widgets = {}
        self.partner_docs_widgets[role] = {}

        next_row = grid_layout.rowCount()
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 20, 0, 0)
        grid_layout.addWidget(container, next_row, 0, 1, 4)

        sep = QLabel("Supporting Documents")
        sep.setFont(QFont("", 14, QFont.Bold))
        container_layout.addWidget(sep)

        for category in profiles.ATTACHMENT_CATEGORIES:
            cat_label = profiles.CATEGORY_LABELS[category]
            cat_frame = QFrame()
            cat_frame.setFrameShape(QFrame.StyledPanel)
            cat_frame.setStyleSheet("QFrame { border: 1px solid #555; border-radius: 8px; }")
            cat_frame_layout = QVBoxLayout(cat_frame)
            cat_frame_layout.setContentsMargins(10, 8, 10, 6)
            container_layout.addWidget(cat_frame)

            title_row = QWidget()
            title_row_layout = QHBoxLayout(title_row)
            title_row_layout.setContentsMargins(0, 0, 0, 4)
            cat_frame_layout.addWidget(title_row)

            title_label = QLabel(cat_label)
            title_label.setFont(QFont("", 12, QFont.Bold))
            title_row_layout.addWidget(title_label)

            count_lbl = QLabel("(0 files)")
            count_lbl.setStyleSheet("color: #888;")
            title_row_layout.addWidget(count_lbl)
            title_row_layout.addStretch(1)

            upload_btn = QPushButton("+ Upload")
            upload_btn.setFixedSize(90, 26)
            upload_btn.clicked.connect(
                lambda checked=False, c=category, r=role: self._upload_partner_doc(r, c)
            )
            title_row_layout.addWidget(upload_btn)

            file_list_widget = QWidget()
            file_list_layout = QVBoxLayout(file_list_widget)
            file_list_layout.setContentsMargins(0, 0, 0, 0)
            cat_frame_layout.addWidget(file_list_widget)

            self.partner_docs_widgets[role][category] = {
                "frame": cat_frame,
                "count_label": count_lbl,
                "file_list": file_list_widget,
                "file_list_layout": file_list_layout,
            }

    def _refresh_partner_docs(self, role):
        profile_id = self._get_loaded_profile_id(role)
        widgets = self.partner_docs_widgets.get(role, {})

        for cat, w in widgets.items():
            entries = []
            if profile_id:
                attachments = profiles.get_profile_attachments(profile_id)
                for entry in attachments.get(cat, []):
                    fpath = profiles.get_profile_attachment_path(profile_id, cat, entry["id"])
                    entries.append({
                        "id": entry["id"],
                        "name": entry["original_filename"],
                        "size": entry["file_size"],
                        "path": fpath,
                        "is_db": True,
                    })

            for fpath in self.session_docs.get(role, {}).get(cat, []):
                entries.append({
                    "id": fpath,
                    "name": os.path.basename(fpath),
                    "size": os.path.getsize(fpath) if os.path.exists(fpath) else 0,
                    "path": fpath,
                    "is_db": False,
                })

            signature = tuple((e["id"], e["is_db"]) for e in entries)
            if w.get("_last_sig") == signature:
                continue
            w["_last_sig"] = signature

            layout = w["file_list_layout"]
            self._clear_layout(layout)

            w["count_label"].setText("({} files)".format(len(entries)))
            if not entries:
                empty_lbl = QLabel("No files uploaded.")
                empty_lbl.setStyleSheet("color: #aaa;")
                layout.addWidget(empty_lbl)
                continue

            for idx, entry in enumerate(entries):
                row = QFrame()
                row.setStyleSheet(
                    "background-color: #3a3a3a;" if idx % 2 == 0 else "background-color: transparent;"
                )
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(8, 3, 4, 3)
                layout.addWidget(row)

                name = entry["name"]
                if len(name) > 40:
                    name = name[:37] + "..."
                size = _human_size(entry["size"])
                pages = _count_pdf_pages(entry["path"]) if entry["path"] else -1
                pg = " | {} pg".format(pages) if pages > 0 else ""

                name_lbl = QLabel("{}. {}  ({}{})".format(idx + 1, name, size, pg))
                row_layout.addWidget(name_lbl, stretch=1)

                remove_btn = QPushButton("Remove")
                remove_btn.setFixedSize(60, 22)
                remove_btn.setStyleSheet("background-color: #c0392b; color: white;")
                remove_btn.clicked.connect(
                    lambda checked=False, pid=profile_id, c=cat, a=entry["id"], r=role,
                           is_db=entry["is_db"]:
                        self._remove_partner_doc(pid, c, a, r, is_db)
                )
                row_layout.addWidget(remove_btn)

                preview_btn = QPushButton("Preview")
                preview_btn.setFixedSize(60, 22)
                preview_btn.clicked.connect(
                    lambda checked=False, p=entry.get("path"): self._preview_document(p)
                )
                row_layout.addWidget(preview_btn)

    def _upload_partner_doc(self, role, category):
        title = profiles.CATEGORY_LABELS.get(category, category)
        filepaths, _ = QFileDialog.getOpenFileNames(
            self, "Upload {}".format(title), "",
            "Supported files (*.pdf *.png *.jpg *.jpeg);;All files (*.*)",
        )
        if not filepaths:
            return

        profile_id = self._get_loaded_profile_id(role)
        if profile_id:
            for fp in filepaths:
                profiles.add_profile_attachment(profile_id, category, fp)
        else:
            for fp in filepaths:
                self.session_docs[role][category].append(fp)

        self._refresh_partner_docs(role)
        logger.info("Uploaded {} file(s) to {}".format(len(filepaths), role))

    def _remove_partner_doc(self, profile_id, category, att_id, role, is_db=True):
        # FIX 3: Warn the user before permanently deleting a file from the reusable profile database
        if is_db and profile_id:
            reply = QMessageBox.warning(
                self, "Permanently Delete?", 
                "This file is part of the saved partner profile. Removing it will permanently delete it from your profile database.\n\nAre you sure you want to proceed?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                profiles.remove_profile_attachment(profile_id, category, att_id)
                self._refresh_partner_docs(role)
        else:
            if att_id in self.session_docs.get(role, {}).get(category, []):
                self.session_docs[role][category].remove(att_id)
            self._refresh_partner_docs(role)

    def _clear_doc_preview(self, role):
        pass