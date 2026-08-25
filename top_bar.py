# -*- coding: utf-8 -*-
"""Sticky top bar: breadcrumb trail, Ctrl+K hint, and primary actions."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy

from theme import SIZE
from format_utils import format_percentage

BREADCRUMBS = {
    "project": "Project Info",
    "lead": "Lead Partner",
    "first": "First Partner",
    "second": "Second Partner",
}


class StickyTopBar(QFrame):
    generate_requested = Signal()
    generate_pdfs_requested = Signal()
    clear_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(SIZE["topbar_h"])

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 12, 0)
        row.setSpacing(10)

        self.crumb_root = QLabel("Bid Workspace")
        self.crumb_root.setObjectName("Breadcrumb")
        row.addWidget(self.crumb_root)

        sep = QLabel("/")
        sep.setObjectName("Breadcrumb")
        row.addWidget(sep)

        self.crumb_current = QLabel("Project Info")
        self.crumb_current.setObjectName("BreadcrumbCurrent")
        row.addWidget(self.crumb_current)

        row.addStretch(1)

        # Live percentage badge (kept in sync from app.py)
        self.percentage_badge = QLabel("Split: 0%")
        self.percentage_badge.setObjectName("PercentageBadge")
        row.addWidget(self.percentage_badge)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_requested.emit)
        row.addWidget(self.clear_btn)

        self.pdfs_btn = QPushButton("Generate PDFs")
        self.pdfs_btn.setCursor(Qt.PointingHandCursor)
        self.pdfs_btn.clicked.connect(self.generate_pdfs_requested.emit)
        row.addWidget(self.pdfs_btn)

        self.generate_btn = QPushButton("Generate Bid")
        self.generate_btn.setObjectName("Primary")
        self.generate_btn.setCursor(Qt.PointingHandCursor)
        self.generate_btn.clicked.connect(self.generate_requested.emit)
        row.addWidget(self.generate_btn)

    def set_breadcrumb(self, module_id: str):
        self.crumb_current.setText(BREADCRUMBS.get(module_id, module_id))

    def set_percentage(self, total: float, ok: bool):
        self.percentage_badge.setText(f"Split: {format_percentage(total)}%")