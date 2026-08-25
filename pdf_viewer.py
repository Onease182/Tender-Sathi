# -*- coding: utf-8 -*-
"""Paginated preview window and employer-PDF viewer widgets.

PySide6 port — same behaviour as the customtkinter original. CTkToplevel
-> QDialog, CTkImage -> QPixmap, filedialog/messagebox -> Qt equivalents.
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage, QFont
from PySide6.QtWidgets import (
    QApplication, QDialog, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QScrollArea, QFileDialog, QMessageBox,
)

from pdf_utils import fitz, HAS_FITZ


def _pixmap_from_png_bytes(img_bytes, target_width=None):
    image = QImage.fromData(img_bytes, "PNG")
    pixmap = QPixmap.fromImage(image)
    if target_width and pixmap.width() > 0:
        ratio = target_width / pixmap.width()
        pixmap = pixmap.scaled(
            target_width, int(pixmap.height() * ratio),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
    return pixmap


class PDFViewerMixin:
    """Employer-PDF viewer (paginated) and the modal document preview window."""

    def upload_employer_pdf(self):
        if not HAS_FITZ:
            QMessageBox.critical(
                self, "Missing Library",
                "PyMuPDF is required to view PDFs.\n"
                "Please install it by running:\npip install PyMuPDF",
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(self, "Select PDF", "", "PDF files (*.pdf)")
        if not file_path:
            return

        if self._set_employer_pdf(file_path):
            QMessageBox.information(
                self, "Success",
                "PDF loaded!\nUse the 'Copy Text' button to copy the current "
                "page's text, then paste it into the fields.",
            )

    def _set_employer_pdf(self, file_path, notify_on_error=True):
        """Point the viewer at an already-known PDF path (no file dialog).
        Used both by upload_employer_pdf (after the user picks a file) and
        by draft loading (restoring a previously-uploaded path). Returns
        True on success."""
        if not HAS_FITZ:
            return False
        try:
            with fitz.open(file_path) as doc:
                page_count = len(doc)
        except Exception as e:
            if notify_on_error:
                QMessageBox.critical(self, "Error", f"Failed to read PDF:\n{e}")
            return False

        self._employer_pdf_path = file_path
        self._employer_pdf_page_count = page_count
        self._employer_pdf_page_index = 0
        self._render_employer_pdf_page()
        return True

    def _render_employer_pdf_page(self):
        self._clear_layout(self.pdf_viewer_layout)
        self.pdf_images = []

        if not self._employer_pdf_path or self._employer_pdf_page_count == 0:
            return

        idx = self._employer_pdf_page_index
        try:
            with fitz.open(self._employer_pdf_path) as doc:
                page = doc[idx]
                page_text = page.get_text()
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")

            pixmap = _pixmap_from_png_bytes(img_bytes, target_width=650)
            self.pdf_images = [pixmap]

            nav = QWidget()
            nav_layout = QHBoxLayout(nav)
            nav_layout.setContentsMargins(0, 0, 0, 5)
            self.pdf_viewer_layout.addWidget(nav)

            prev_btn = QPushButton("< Prev")
            prev_btn.setFixedSize(70, 25)
            prev_btn.setEnabled(idx != 0)
            prev_btn.clicked.connect(self._prev_employer_pdf_page)
            nav_layout.addWidget(prev_btn)

            page_lbl = QLabel(f"Page {idx + 1} of {self._employer_pdf_page_count}")
            nav_layout.addWidget(page_lbl)

            next_btn = QPushButton("Next >")
            next_btn.setFixedSize(70, 25)
            next_btn.setEnabled(idx < self._employer_pdf_page_count - 1)
            next_btn.clicked.connect(self._next_employer_pdf_page)
            nav_layout.addWidget(next_btn)
            nav_layout.addStretch(1)

            page_container = QWidget()
            page_container_layout = QVBoxLayout(page_container)
            self.pdf_viewer_layout.addWidget(page_container)

            img_lbl = QLabel()
            img_lbl.setPixmap(pixmap)
            page_container_layout.addWidget(img_lbl, alignment=Qt.AlignHCenter)

            if page_text.strip():
                copy_btn = QPushButton(f"Copy Text from Page {idx + 1}")
                copy_btn.setFixedHeight(25)
                copy_btn.clicked.connect(
                    lambda checked=False, t=page_text: self.copy_text_to_clipboard(t)
                )
                page_container_layout.addWidget(copy_btn)

            self.pdf_viewer_layout.addStretch(1)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read PDF:\n{e}")

    def _prev_employer_pdf_page(self):
        if self._employer_pdf_page_index > 0:
            self._employer_pdf_page_index -= 1
            self._render_employer_pdf_page()

    def _next_employer_pdf_page(self):
        if self._employer_pdf_page_index < self._employer_pdf_page_count - 1:
            self._employer_pdf_page_index += 1
            self._render_employer_pdf_page()

    def copy_text_to_clipboard(self, text):
        QApplication.clipboard().setText(text)
        QMessageBox.information(
            self, "Copied",
            "Text copied to clipboard!\nYou can now paste it (Ctrl+V) into the input fields.",
        )

    def _preview_document(self, file_path):
        if not file_path or not os.path.exists(file_path):
            QMessageBox.critical(self, "Error", "File not found or path is empty.")
            return

        ext = os.path.splitext(file_path)[1].lower()

        preview_window = QDialog(self)
        preview_window.setWindowTitle(f"Preview - {os.path.basename(file_path)}")
        preview_window.resize(950, 750)
        preview_window.setModal(True)

        outer_layout = QVBoxLayout(preview_window)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(header)

        title_lbl = QLabel(os.path.basename(file_path))
        title_lbl.setFont(QFont("", 15, QFont.Bold))
        header_layout.addWidget(title_lbl)
        header_layout.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(preview_window.close)
        header_layout.addWidget(close_btn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll.setWidget(scroll_content)
        outer_layout.addWidget(scroll)

        preview_window._preview_images = []

        if ext in (".png", ".jpg", ".jpeg"):
            try:
                pixmap = QPixmap(file_path)
                max_w, max_h = 900, 700
                w, h = pixmap.width(), pixmap.height()
                ratio = min(max_w / w, max_h / h, 1.0) if w and h else 1.0
                new_size = (int(w * ratio), int(h * ratio))
                scaled = pixmap.scaled(
                    new_size[0], new_size[1], Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                preview_window._preview_images.append(scaled)

                lbl = QLabel()
                lbl.setPixmap(scaled)
                scroll_layout.addWidget(lbl, alignment=Qt.AlignHCenter)
            except Exception as e:
                err_lbl = QLabel(f"Error loading image:\n{e}")
                err_lbl.setStyleSheet("color: #e74c3c;")
                scroll_layout.addWidget(err_lbl)

        elif ext == ".pdf":
            if not HAS_FITZ:
                err_lbl = QLabel("PyMuPDF is required to preview PDFs.\nInstall: pip install PyMuPDF")
                err_lbl.setStyleSheet("color: #e74c3c;")
                scroll_layout.addWidget(err_lbl)
                preview_window.exec()
                return

            try:
                with fitz.open(file_path) as doc:
                    page_count = len(doc)
            except Exception as e:
                err_lbl = QLabel(f"Error loading PDF:\n{e}")
                err_lbl.setStyleSheet("color: #e74c3c;")
                scroll_layout.addWidget(err_lbl)
                preview_window.exec()
                return

            preview_window._preview_page_index = 0

            def render_page():
                self._clear_layout(scroll_layout)
                preview_window._preview_images = []

                idx = preview_window._preview_page_index
                try:
                    with fitz.open(file_path) as doc:
                        page = doc[idx]
                        pix = page.get_pixmap(dpi=150)
                        img_bytes = pix.tobytes("png")

                    pixmap = _pixmap_from_png_bytes(img_bytes, target_width=900)
                    preview_window._preview_images = [pixmap]

                    nav = QWidget()
                    nav_layout = QHBoxLayout(nav)
                    nav_layout.setContentsMargins(0, 0, 0, 5)
                    scroll_layout.addWidget(nav)

                    prev_btn = QPushButton("< Prev")
                    prev_btn.setFixedSize(70, 25)
                    prev_btn.setEnabled(idx != 0)
                    prev_btn.clicked.connect(go_prev)
                    nav_layout.addWidget(prev_btn)

                    page_lbl = QLabel(f"Page {idx + 1} of {page_count}")
                    page_lbl.setFont(QFont("", 12, QFont.Bold))
                    nav_layout.addWidget(page_lbl)

                    next_btn = QPushButton("Next >")
                    next_btn.setFixedSize(70, 25)
                    next_btn.setEnabled(idx < page_count - 1)
                    next_btn.clicked.connect(go_next)
                    nav_layout.addWidget(next_btn)
                    nav_layout.addStretch(1)

                    page_container = QWidget()
                    page_container_layout = QVBoxLayout(page_container)
                    scroll_layout.addWidget(page_container)

                    img_lbl = QLabel()
                    img_lbl.setPixmap(pixmap)
                    page_container_layout.addWidget(img_lbl, alignment=Qt.AlignHCenter)
                except Exception as e:
                    err_lbl = QLabel(f"Error loading PDF:\n{e}")
                    err_lbl.setStyleSheet("color: #e74c3c;")
                    scroll_layout.addWidget(err_lbl)

            def go_prev():
                if preview_window._preview_page_index > 0:
                    preview_window._preview_page_index -= 1
                    render_page()

            def go_next():
                if preview_window._preview_page_index < page_count - 1:
                    preview_window._preview_page_index += 1
                    render_page()

            render_page()
        else:
            info_lbl = QLabel("Preview not available for this file type.")
            info_lbl.setStyleSheet("color: #888;")
            scroll_layout.addWidget(info_lbl)

        preview_window.exec()
