# -*- coding: utf-8 -*-
"""Right-hand pane of the main QSplitter.

Two stacked sections:
  1. A sticky summary of live bid metrics + a readiness checklist.
  2. The employer-PDF live preview (the existing PDFViewerMixin renders
     into `self.pdf_viewer_layout`, which this panel owns).

app.py is responsible for calling `refresh()` periodically / on field
changes with a small dict of computed values — this widget has no
knowledge of `profiles.py` or the form fields themselves.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QWidget, QSizePolicy,
)

from format_utils import format_percentage


def _hsep():
    line = QFrame()
    line.setObjectName("HSep")
    line.setFrameShape(QFrame.HLine)
    return line


class MetricRow(QWidget):
    def __init__(self, label_text):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        self.label = QLabel(label_text)
        self.label.setObjectName("MetricLabel")
        row.addWidget(self.label)
        row.addStretch(1)
        self.value = QLabel("—")
        self.value.setObjectName("MetricValue")
        self.value.setProperty("mono", "true")
        row.addWidget(self.value)

    def set_value(self, text):
        self.value.setText(text)


class ChecklistRow(QWidget):
    def __init__(self, label_text):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        self.dot = QLabel("○")
        self.dot.setFixedWidth(16)
        row.addWidget(self.dot)
        self.label = QLabel(label_text)
        self.label.setObjectName("MetricLabel")
        row.addWidget(self.label)
        row.addStretch(1)

    def set_done(self, done: bool):
        self.dot.setText("●" if done else "○")
        self.dot.setStyleSheet(
            "color: #10b981;" if done else "color: #a1a1aa;"
        )


class StickySummaryPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SummaryPanel")
        self.setMinimumWidth(280)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(8)

        heading = QLabel("Bid Summary")
        heading.setObjectName("SummaryHeading")
        root.addWidget(heading)
        root.addWidget(_hsep())

        self.metric_jv_name = MetricRow("JV Name")
        self.metric_split = MetricRow("Partner Split")
        self.metric_project = MetricRow("Project")
        for m in (self.metric_jv_name, self.metric_split, self.metric_project):
            root.addWidget(m)

        root.addWidget(_hsep())
        checklist_heading = QLabel("Readiness")
        checklist_heading.setObjectName("MetricLabel")
        root.addWidget(checklist_heading)

        self.check_partners = ChecklistRow("Partner names filled")
        self.check_split = ChecklistRow("Split totals 100%")
        self.check_signature = ChecklistRow("Authorized signature uploaded")
        for c in (self.check_partners, self.check_split, self.check_signature):
            root.addWidget(c)

        root.addWidget(_hsep())

        # --- Live document preview ---
        preview_heading_row = QHBoxLayout()
        preview_heading = QLabel("Employer Document Preview")
        preview_heading.setObjectName("SummaryHeading")
        preview_heading_row.addWidget(preview_heading)
        preview_heading_row.addStretch(1)
        self.upload_btn = QPushButton("Upload PDF")
        preview_heading_row.addWidget(self.upload_btn)
        root.addLayout(preview_heading_row)

        self.pdf_viewer_scroll = QScrollArea()
        self.pdf_viewer_scroll.setWidgetResizable(True)
        self.pdf_viewer_frame = QWidget()
        self.pdf_viewer_layout = QVBoxLayout(self.pdf_viewer_frame)
        self.pdf_viewer_scroll.setWidget(self.pdf_viewer_frame)
        root.addWidget(self.pdf_viewer_scroll, stretch=1)

    # -- refresh --------------------------------------------------------
    def refresh(self, *, jv_name, project_name, split_total, split_ok,
                partners_filled, signature_uploaded):
        self.metric_jv_name.set_value(jv_name or "—")
        self.metric_project.set_value(project_name or "—")
        self.metric_split.set_value(f"{format_percentage(split_total)}%")
        self.check_partners.set_done(partners_filled)
        self.check_split.set_done(split_ok)
        self.check_signature.set_done(signature_uploaded)
