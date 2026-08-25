# -*- coding: utf-8 -*-
"""Collapsible left sidebar: project selector, module nav, collapse toggle."""

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtWidgets import (
    QFrame, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QButtonGroup, QSizePolicy,
)

from theme import SIZE

# (module_id, icon_glyph, label) — icon_glyph is a plain unicode glyph so we
# don't take a Lucide/QtAwesome dependency; swap for QIcon(...) if you wire
# up an icon font or SVG icon set.
MODULES = [
    ("lead", "★", "Lead Partner"),
    ("first", "★", "First Partner"),
    ("second", "★", "Second Partner"),
    ("project", "▤", "Project Info"),
]

# project_selector item labels. The sidebar only knows about labels and
# item data (draft id, or the sentinel below) — it has no idea what a
# "draft" is in storage terms. That lives in drafts.py / app.py.
CURRENT_BID_LABEL = "Current Bid (unsaved)"
NEW_BID_LABEL = "+ New Bid…"
_NEW_BID_SENTINEL = "__new_bid__"


class CollapsibleSidebar(QFrame):
    module_selected = Signal(str)          # emits module id
    theme_toggled = Signal(str)            # emits "Light" | "Dark"
    draft_selected = Signal(str)           # emits draft id, or "" for Current Bid
    new_bid_requested = Signal()           # "+ New Bid…" was picked
    save_draft_requested = Signal()        # Save button clicked
    delete_draft_requested = Signal()      # Delete button clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        # Elevation shadow is applied/refreshed by App.change_appearance_mode_event()
        # so its color tracks the active Light/Dark mode.
        self._expanded_w = SIZE["sidebar_w"]
        self._collapsed_w = SIZE["sidebar_w_collapsed"]
        self._collapsed = False
        self.setFixedWidth(self._expanded_w)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 14, 12, 12)
        root.setSpacing(10)

        # ---- Header: logo + collapse toggle ----
        header = QVBoxLayout()
        header.setSpacing(2)
        self.logo = QLabel("JV BID PRO")
        self.logo.setObjectName("SidebarLogo")
        header.addWidget(self.logo)
        self.tagline = QLabel("Document Suite")
        self.tagline.setObjectName("SidebarTagline")
        header.addWidget(self.tagline)
        root.addLayout(header)

        self.collapse_btn = QPushButton("⟨⟨")
        self.collapse_btn.setObjectName("CollapseToggle")
        self.collapse_btn.setCursor(Qt.PointingHandCursor)
        self.collapse_btn.clicked.connect(self.toggle_collapsed)
        root.addWidget(self.collapse_btn)

        # ---- Project selector ----
        # Item 0 is always "Current Bid (unsaved)" (itemData=None) — the
        # in-memory form contents, whether or not they're tied to a saved
        # draft. Saved drafts are inserted after it (itemData=draft id),
        # and "+ New Bid…" (itemData=_NEW_BID_SENTINEL) is always last.
        self.project_label = QLabel("PROJECT")
        self.project_label.setObjectName("SidebarTagline")
        root.addWidget(self.project_label)

        self.project_selector = QComboBox()
        self.project_selector.addItem(CURRENT_BID_LABEL, None)
        self.project_selector.addItem(NEW_BID_LABEL, _NEW_BID_SENTINEL)
        self.project_selector.currentIndexChanged.connect(self._on_project_selector_changed)
        root.addWidget(self.project_selector)

        self.draft_actions_row = QWidget()
        draft_actions = QHBoxLayout(self.draft_actions_row)
        draft_actions.setContentsMargins(0, 0, 0, 0)
        draft_actions.setSpacing(6)
        self.save_draft_btn = QPushButton("💾 Save")
        self.save_draft_btn.setObjectName("NavItem")
        self.save_draft_btn.setCursor(Qt.PointingHandCursor)
        self.save_draft_btn.clicked.connect(self.save_draft_requested.emit)
        draft_actions.addWidget(self.save_draft_btn)

        self.delete_draft_btn = QPushButton("🗑")
        self.delete_draft_btn.setObjectName("NavItem")
        self.delete_draft_btn.setFixedWidth(36)
        self.delete_draft_btn.setCursor(Qt.PointingHandCursor)
        self.delete_draft_btn.setEnabled(False)
        self.delete_draft_btn.clicked.connect(self.delete_draft_requested.emit)
        draft_actions.addWidget(self.delete_draft_btn)
        root.addWidget(self.draft_actions_row)

        # ---- Module nav ----
        self.nav_label = QLabel("MODULES")
        self.nav_label.setObjectName("SidebarTagline")
        root.addWidget(self.nav_label)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_buttons = {}
        for mod_id, glyph, label in MODULES:
            btn = QPushButton(f"{glyph}   {label}")
            btn.setObjectName("NavItem")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, m=mod_id: self.module_selected.emit(m))
            self._nav_group.addButton(btn)
            self._nav_buttons[mod_id] = (btn, glyph, label)
            root.addWidget(btn)
        self._nav_buttons["project"][0].setChecked(True)

        root.addStretch(1)

        # ---- Footer: theme mode ----
        self.theme_label = QLabel("THEME")
        self.theme_label.setObjectName("SidebarTagline")
        root.addWidget(self.theme_label)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        self.theme_combo.currentTextChanged.connect(self.theme_toggled.emit)
        root.addWidget(self.theme_combo)

        self._anim = QPropertyAnimation(self, b"minimumWidth")
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim2 = QPropertyAnimation(self, b"maximumWidth")
        self._anim2.setDuration(140)
        self._anim2.setEasingCurve(QEasingCurve.OutCubic)

    # -- project switcher -----------------------------------------------
    def _on_project_selector_changed(self, index):
        if index < 0:
            return
        data = self.project_selector.itemData(index)
        if data == _NEW_BID_SENTINEL:
            self.new_bid_requested.emit()
        else:
            self.draft_selected.emit(data or "")

    def set_drafts(self, drafts, current_draft_id=None):
        """Repopulate the switcher. `drafts` is a list of {"id", "name"}
        dicts, most-recently-updated first. Does not emit signals."""
        self.project_selector.blockSignals(True)
        self.project_selector.clear()
        self.project_selector.addItem(CURRENT_BID_LABEL, None)
        for d in drafts:
            self.project_selector.addItem(d["name"], d["id"])
        self.project_selector.addItem(NEW_BID_LABEL, _NEW_BID_SENTINEL)

        target_index = 0
        if current_draft_id:
            found = self.project_selector.findData(current_draft_id)
            if found >= 0:
                target_index = found
        self.project_selector.setCurrentIndex(target_index)
        self.project_selector.blockSignals(False)

        self.delete_draft_btn.setEnabled(bool(current_draft_id))
        self.save_draft_btn.setText("💾 Update" if current_draft_id else "💾 Save")

    # -- public API ---------------------------------------------------------
    def set_active(self, module_id: str):
        btn = self._nav_buttons.get(module_id)
        if btn:
            btn[0].setChecked(True)

    def toggle_collapsed(self):
        self._collapsed = not self._collapsed
        target = self._collapsed_w if self._collapsed else self._expanded_w

        for widget in (
            self.logo, self.tagline, self.project_label, self.project_selector,
            self.draft_actions_row, self.nav_label, self.theme_label, self.theme_combo,
        ):
            widget.setVisible(not self._collapsed)

        for mod_id, (btn, glyph, label) in self._nav_buttons.items():
            btn.setText(glyph if self._collapsed else f"{glyph}   {label}")

        self.collapse_btn.setText("⟩⟩" if self._collapsed else "⟨⟨")

        for anim, prop in ((self._anim, "minimumWidth"), (self._anim2, "maximumWidth")):
            anim.stop()
            anim.setStartValue(self.width())
            anim.setEndValue(target)
            anim.start()