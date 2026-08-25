# -*- coding: utf-8 -*-
"""JV Bid Pro — main application class (PySide6, enterprise UI redesign)."""

import os
import json
import logging
import shutil
import sys
import subprocess
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QLineEdit, QComboBox, QStackedWidget, QScrollArea, QGridLayout,
    QVBoxLayout, QHBoxLayout, QSplitter, QMessageBox, QFileDialog, QInputDialog,
)

import profiles
import drafts
import theme
import pdf_export
# from doc_generator import BidDocumentGenerator  # lazy-imported in __init__ to avoid circular import
from pdf_viewer import PDFViewerMixin
from partner_docs import PartnerDocsMixin
from sidebar import CollapsibleSidebar
from top_bar import StickyTopBar
from summary_panel import StickySummaryPanel
from format_utils import format_percentage


class SectionedFormGrid:
    """Route legacy row-based form calls into titled visual cards."""

    def __init__(self, parent, sections):
        self.parent = parent
        self.sections = sections
        self._next_row = 0
        outer = QVBoxLayout(parent)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)
        self._cards = []
        for start, end, title, subtitle in sections:
            card = QFrame(parent)
            card.setObjectName("FormCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 14, 16, 16)
            card_layout.setSpacing(8)

            heading = QLabel(title)
            heading.setObjectName("CardTitle")
            card_layout.addWidget(heading)
            if subtitle:
                description = QLabel(subtitle)
                description.setObjectName("CardSubtitle")
                description.setWordWrap(True)
                card_layout.addWidget(description)

            grid_host = QWidget(card)
            grid = QGridLayout(grid_host)
            grid.setContentsMargins(0, 6, 0, 0)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(8)
            card_layout.addWidget(grid_host)
            outer.addWidget(card)
            self._cards.append((start, end, grid))

        outer.addStretch(1)

    def _section_for_row(self, row):
        for start, end, grid in self._cards:
            if start <= row <= end:
                return start, grid
        return self._cards[-1][0], self._cards[-1][2]

    def addWidget(self, widget, row, column, row_span=1, column_span=1, *args):
        start, grid = self._section_for_row(row)
        grid.addWidget(widget, row - start, column, row_span, column_span, *args)
        self._next_row = max(self._next_row, row + row_span)

    def rowCount(self):
        return self._next_row

# ---- Role prefix mapping for cross-role profile loading ---------------------
ROLE_PREFIXES = {"lead": "LEAD", "first": "FIRST", "second": "SECOND"}
PERCENTAGE_KEYS = {"lead": "L_PER", "first": "F_PER", "second": "S_PER"}

PARTNER_CEO_FIELD_TO_SIG = {
    "LEAD_PARTNER_CEO": "LEAD_CEO_SIG",
    "FIRST_PARTNER_CEO": "FIRST_CEO_SIG",
    "SECOND_PARTNER_CEO": "SECOND_CEO_SIG",
}

PARTNER_ADDRESS_FIELDS = ("LEAD_ADDRESS", "FIRST_ADDRESS", "SECOND_ADDRESS")
MODULE_ORDER = ["project", "lead", "first", "second"]

# ---- Logging ----------------------------------------------------------------
APP_ROOT = Path(__file__).resolve().parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(APP_ROOT / "bid_generation.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

class App(QMainWindow, PDFViewerMixin, PartnerDocsMixin):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("JV Bid Pro - Professional Document Suite")
        self.resize(1440, 900)

        self.app_root = APP_ROOT
        from doc_generator import BidDocumentGenerator
        self.generator = BidDocumentGenerator(self.app_root)
        self.image_mapping = {}
        self.partner_docs_widgets = {}
        self.doc_preview_widgets = {}

        self._jv_name_manual = False
        self._setting_jv_name_auto = False

        self.session_docs = {
            r: {c: [] for c in profiles.ATTACHMENT_CATEGORIES}
            for r in profiles.PARTNER_ROLES
        }

        self._current_draft_id = None
        self.profile_save_btns = {}  # Tracks the save buttons for dynamic text


        self._build_shell()

        self.entries = {}
        self.labels = {}
        self._partner_tabs_enabled = True
        self.setup_project_tab()
        self.setup_lead_tab()
        self.setup_partners_tab()

        self._wire_shell()
        self._refresh_draft_selector()
        self.change_appearance_mode_event("Light")

        self._summary_timer = QTimer(self)
        self._summary_timer.setInterval(600)
        self._summary_timer.timeout.connect(self._refresh_summary)
        QTimer.singleShot(2000, self._summary_timer.start)

    def _build_shell(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = CollapsibleSidebar()
        root_layout.addWidget(self.sidebar)

        main_col = QWidget()
        main_col_layout = QVBoxLayout(main_col)
        main_col_layout.setContentsMargins(0, 0, 0, 0)
        main_col_layout.setSpacing(0)
        root_layout.addWidget(main_col, stretch=1)

        self.top_bar = StickyTopBar()
        main_col_layout.addWidget(self.top_bar)


        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        main_col_layout.addWidget(self.splitter, stretch=1)

        pages_wrap = QWidget()
        pages_wrap.setObjectName("PageSurface")
        pages_layout = QVBoxLayout(pages_wrap)
        pages_layout.setContentsMargins(16, 16, 16, 16)
        self.stacked = QStackedWidget()
        pages_layout.addWidget(self.stacked)
        self.splitter.addWidget(pages_wrap)

        self.tab_project = QWidget()
        self.tab_lead = QWidget()
        self.tab_first = QWidget()
        self.tab_second = QWidget()
        for page in (self.tab_project, self.tab_lead, self.tab_first, self.tab_second):
            self.stacked.addWidget(page)

        self.summary_panel = StickySummaryPanel()
        self.splitter.addWidget(self.summary_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([900, 420])

        self.pdf_viewer_scroll = self.summary_panel.pdf_viewer_scroll
        self.pdf_viewer_frame = self.summary_panel.pdf_viewer_frame
        self.pdf_viewer_layout = self.summary_panel.pdf_viewer_layout
        self.pdf_images = []
        self._employer_pdf_path = None
        self._employer_pdf_page_count = 0
        self._employer_pdf_page_index = 0

    def _wire_shell(self):
        self.sidebar.module_selected.connect(self._navigate)
        self.sidebar.theme_toggled.connect(self.change_appearance_mode_event)
        self.sidebar.draft_selected.connect(self._on_draft_selected)
        self.sidebar.new_bid_requested.connect(self._on_new_bid_requested)
        self.sidebar.save_draft_requested.connect(self._on_save_draft_requested)
        self.sidebar.delete_draft_requested.connect(self._on_delete_draft_requested)

        self.top_bar.generate_requested.connect(self.generate_doc)
        self.top_bar.clear_requested.connect(self.clear_fields)

        self.top_bar.generate_pdfs_requested.connect(self.split_generated_doc)

        self.summary_panel.upload_btn.clicked.connect(self.upload_employer_pdf)

    def _navigate(self, module_id):
        if module_id not in MODULE_ORDER:
            return
        if module_id in ("first", "second") and not self._partner_tabs_enabled:
            return
        self.stacked.setCurrentIndex(MODULE_ORDER.index(module_id))
        self.sidebar.set_active(module_id)
        self.top_bar.set_breadcrumb(module_id)
        # Lazy-load partner docs only when the tab is first shown
        if module_id in ("lead", "first", "second"):
            self._refresh_partner_docs(module_id)

    def _toggle_theme_command(self):
        current = self.sidebar.theme_combo.currentText()
        self.sidebar.theme_combo.setCurrentText("Dark" if current == "Light" else "Light")

    def _refresh_summary(self):
        total = self._update_percentage_total()
        ok = abs(total - 100.0) < 0.01
        self.top_bar.set_percentage(total, ok)

        jv_name = self.get_form_value("JV_NAME") if hasattr(self, "entries") else ""
        project_name = self.get_form_value("PROJECT_NAME") if hasattr(self, "entries") else ""

        partners_filled = bool(self.get_form_value("LEAD_PARTNER_NAME"))
        signature_uploaded = "AUTHORISED_SIG" in self.image_mapping

        self.summary_panel.refresh(
            jv_name=jv_name,
            project_name=project_name,
            split_total=total,
            split_ok=ok,
            partners_filled=partners_filled,
            signature_uploaded=signature_uploaded,
        )

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            else:
                sub_layout = item.layout()
                if sub_layout is not None:
                    self._clear_layout(sub_layout)

    def _set_combo_text_silent(self, combo, text):
        combo.blockSignals(True)
        combo.setCurrentText(text)
        combo.blockSignals(False)

    def _entry_value(self, entry):
        if isinstance(entry, QComboBox):
            return entry.currentText()
        return entry.text()

    def _make_scroll_grid(self, parent_tab, sections):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        grid = SectionedFormGrid(content, sections)
        scroll.setWidget(content)

        parent_layout = QVBoxLayout(parent_tab)
        parent_layout.setContentsMargins(0, 0, 0, 0)
        parent_layout.addWidget(scroll)
        return content, grid

    def create_field(self, grid_layout, row, label_text, field_key, is_combo=False, combo_vals=None, mono=False):
        label = QLabel(label_text)
        label.setObjectName("FieldLabel")
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grid_layout.addWidget(label, row, 0)
        self.labels[field_key] = label

        if is_combo:
            entry = QComboBox()
            entry.setEditable(True)
            if combo_vals:
                entry.addItems(list(combo_vals))
            entry.setMinimumWidth(280)
        else:
            entry = QLineEdit()
            entry.setPlaceholderText(f"Enter {label_text.lower()}...")
            entry.setMinimumWidth(280)
            if mono:
                entry.setProperty("mono", "true")

        grid_layout.addWidget(entry, row, 1)
        self.entries[field_key] = entry
        return entry

    def create_field_with_upload(self, grid_layout, row, label_text, field_key, img_key):
        label = QLabel(label_text)
        label.setObjectName("FieldLabel")
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grid_layout.addWidget(label, row, 0)

        entry = QLineEdit()
        entry.setPlaceholderText(f"Enter {label_text.lower()}...")
        entry.setMinimumWidth(280)
        grid_layout.addWidget(entry, row, 1)
        self.entries[field_key] = entry

        btn = QPushButton("Upload Signature")
        btn.setFixedSize(130, 28)
        btn.clicked.connect(lambda checked=False, k=img_key: self.upload_image(k))
        grid_layout.addWidget(btn, row, 2)

        status = QLabel("✗")
        status.setObjectName("Badge")
        status.setProperty("status", "danger")
        grid_layout.addWidget(status, row, 3)
        setattr(self, f"status_{img_key}", status)
        return entry

    def create_combo_field_with_upload(self, grid_layout, row, label_text, field_key, img_key):
        label = QLabel(label_text)
        label.setObjectName("FieldLabel")
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grid_layout.addWidget(label, row, 0)

        entry = QComboBox()
        entry.setEditable(True)
        entry.setMinimumWidth(280)
        grid_layout.addWidget(entry, row, 1)
        self.entries[field_key] = entry

        btn = QPushButton("Upload Signature")
        btn.setFixedSize(130, 28)
        btn.clicked.connect(lambda checked=False, k=img_key: self.upload_image(k))
        grid_layout.addWidget(btn, row, 2)

        status = QLabel("✗")
        status.setObjectName("Badge")
        status.setProperty("status", "danger")
        grid_layout.addWidget(status, row, 3)
        setattr(self, f"status_{img_key}", status)
        return entry

    def _mark_status(self, status_label, ok: bool):
        status_label.setText("✓" if ok else "✗")
        status_label.setProperty("status", "success" if ok else "danger")
        status_label.style().unpolish(status_label)
        status_label.style().polish(status_label)

    def get_form_value(self, field_key):
        entry = self.entries.get(field_key)
        if entry is None:
            return ""
        return self._entry_value(entry)

    def set_form_value(self, field_key, value):
        entry = self.entries.get(field_key)
        if entry is None or value is None:
            return
        entry.blockSignals(True)
        if isinstance(entry, QComboBox):
            entry.setCurrentText(str(value))
        else:
            entry.setText(str(value))
        entry.blockSignals(False)

    def create_profile_bar(self, grid_layout, role, row):
        bar = QWidget()
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 10, 0, 5)
        grid_layout.addWidget(bar, row, 0, 1, 4)

        label = QLabel("Profile:")
        label.setObjectName("FieldLabel")
        bar_layout.addWidget(label)

        profile_menu = QComboBox()
        profile_menu.addItem("-- No profile --")
        profile_menu.setMinimumWidth(260)
        profile_menu.currentTextChanged.connect(
            lambda choice, r=role: self.on_profile_selected(r, choice)
        )
        bar_layout.addWidget(profile_menu)

        save_btn = QPushButton("Save as Profile")
        save_btn.setFixedWidth(130)
        save_btn.clicked.connect(lambda checked=False, r=role: self.save_current_as_profile(r))
        bar_layout.addWidget(save_btn)

        self.profile_save_btns[role] = save_btn  # Keep reference for dynamic text changing

        delete_btn = QPushButton("Delete")
        delete_btn.setObjectName("Danger")
        delete_btn.setFixedWidth(90)
        delete_btn.clicked.connect(lambda checked=False, r=role: self.delete_selected_profile(r))
        bar_layout.addWidget(delete_btn)

        bar_layout.addStretch(1)

        if not hasattr(self, "profile_menus"):
            self.profile_menus = {}
            self.profile_maps = {}
            self.profile_source_roles = {}
        self.profile_menus[role] = profile_menu
        self.profile_maps[role] = {}
        self.refresh_profile_menu(role)

    def _update_profile_button_state(self, role):
        """Helper to consistently update the save button text for a given role."""
        if role in self.profile_save_btns:
            loaded_pid = self._get_loaded_profile_id(role)
            if loaded_pid:
                self.profile_save_btns[role].setText("Update Profile")
            else:
                self.profile_save_btns[role].setText("Save as Profile")

    def refresh_profile_menu(self, role):
        menu = self.profile_menus.get(role)
        if menu is None:
            return

        current_choice = menu.currentText()
        current_pid = self.profile_maps.get(role, {}).get(current_choice)

        values = ["-- No profile --"]
        name_to_id = {}
        name_to_role = {}

        # Get ALL profiles, since profiles are role-agnostic now
        plist = profiles.list_profiles()
        for p in plist:
            try:
                img_count = len(json.loads(p.get("images", "{}") or "{}"))
                att_count = 0
                try:
                    atts = json.loads(p.get("attachments", "{}") or "{}")
                    att_count = sum(len(v) for v in atts.values())
                except Exception:
                    pass
                extra = []
                if img_count:
                    extra.append("{} imgs".format(img_count))
                if att_count:
                    extra.append("{} docs".format(att_count))
                tag = " [{}]".format(", ".join(extra)) if extra else ""

                # NO ROLE TAG is appended anymore. A profile is just a profile.
                label = p["name"] + tag
            except (json.JSONDecodeError, TypeError):
                label = p["name"]
            values.append(label)
            name_to_id[label] = p["id"]
            name_to_role[label] = p.get("role", role)  # Still track origin role for image translation

        self.profile_maps[role] = name_to_id
        self.profile_source_roles[role] = name_to_role

        menu.blockSignals(True)
        menu.clear()
        menu.addItems(values)
        menu.blockSignals(False)

        if current_pid:
            for lbl, pid in name_to_id.items():
                if pid == current_pid:
                    self._set_combo_text_silent(menu, lbl)
                    self._update_profile_button_state(role)  # FIX: Update button here too
                    return
        self._set_combo_text_silent(menu, "-- No profile --")
        self._update_profile_button_state(role)  # FIX: Update button here too


    def _clear_role_state(self, role):
        """Clear form, image, and signature state for one partner role."""
        field_map = profiles.ROLE_FIELD_KEYS.get(role, {})
        for entry_key in field_map.values():
            self.set_form_value(entry_key, "")

        for img_key in profiles.ROLE_IMAGE_KEYS.get(role, []):
            self.image_mapping.pop(img_key, None)
            status_label = getattr(self, f"status_{img_key}", None)
            if status_label:
                self._mark_status(status_label, False)

        self.image_mapping.pop("AUTHORISED_SIG", None)
        auth_status = getattr(self, "status_AUTHORISED_SIG", None)
        if auth_status:
            self._mark_status(auth_status, False)

    def on_profile_selected(self, role, choice):
        profile_id = self.profile_maps.get(role, {}).get(choice)

        # Dynamically update button text based on whether a profile is loaded
        self._update_profile_button_state(role)

        if not profile_id:
            self._clear_role_state(role)
            self.session_docs[role] = {c: [] for c in profiles.ATTACHMENT_CATEGORIES}
            self._refresh_partner_docs(role)
            self._update_jv_name_suggestion()
            self._update_percentage_total()
            self._clear_doc_preview(role)
            return

        profile = profiles.get_profile(profile_id)
        if not profile:
            QMessageBox.critical(self, "Error", "That profile could not be found.")
            return

        # Read the original role the profile was created in (for image translation)
        source_role = self.profile_source_roles.get(role, {}).get(choice, role)

        # Load text fields dynamically based on current role
        target_field_map = profiles.ROLE_FIELD_KEYS[role]
        for data_key, entry_key in target_field_map.items():
            self.set_form_value(entry_key, profile.get(data_key, ""))

        # Reset image statuses AND clear any stale image_mapping entries left
        # over from a previously-loaded profile in this role slot — otherwise
        # a key this profile doesn't have (e.g. no stamp uploaded) keeps
        # pointing at the last profile's file and gets silently reused.
        role_image_keys = profiles.ROLE_IMAGE_KEYS.get(role, [])
        for img_key in role_image_keys:
            self.image_mapping.pop(img_key, None)
            status_label = getattr(self, f"status_{img_key}", None)
            if status_label:
                self._mark_status(status_label, False)

        # FIX BUG 2: Clear AUTHORISED_SIG when loading a new profile
        self.image_mapping.pop("AUTHORISED_SIG", None)
        auth_status = getattr(self, "status_AUTHORISED_SIG", None)
        if auth_status:
            self._mark_status(auth_status, False)

        # Load images and translate them to the current role's keys. These
        # paths point directly at uploads/profiles/<id>/... — no copy into
        # assets/ needed, doc_generator just reads whatever path it's given.
        # (This also removes the root cause of the old same-file crash —
        # there's no longer a second copy to collide with.)
        copied = profiles.load_profile_images_to_assets(profile_id)
        loaded = 0
        for img_key, dest_path in copied.items():
            # Translate image key from source role to current role (e.g. LEAD_CEO_SIG -> FIRST_CEO_SIG)
            translated_img_key = self._translate_key(img_key, source_role, role)
            self.image_mapping[translated_img_key] = dest_path
            status_label = getattr(self, f"status_{translated_img_key}", None)
            if status_label is not None:
                self._mark_status(status_label, True)
            loaded += 1

        self._update_jv_address_options()
        self._update_authorised_person_options()
        self._sync_authorised_signature()

        logger.info(f"Loaded profile '{profile['name']}' ({source_role} -> {role}), {loaded} images")
        QMessageBox.information(
            self, "Profile Loaded",
            f"Loaded profile: {profile['name']}" + (f" ({loaded} images)" if loaded else ""),
        )

        self.session_docs[role] = {c: [] for c in profiles.ATTACHMENT_CATEGORIES}
        self._refresh_partner_docs(role)
        self._update_jv_name_suggestion()
        self._update_authorised_person_options()
        self._sync_authorised_signature()
        self._update_percentage_total()
        self._clear_doc_preview(role)

        # NEW: If lead profile loaded in Single Bidder mode, sync Firm's Name/Address
        if role == "lead":
            self._on_lead_name_changed_for_single_bidder()
            self._on_lead_address_changed_for_single_bidder()

    def save_current_as_profile(self, role):
        loaded_pid = self._get_loaded_profile_id(role)

        field_map = profiles.ROLE_FIELD_KEYS[role]
        data = {data_key: self.get_form_value(entry_key) for data_key, entry_key in field_map.items()}
        role_image_keys = profiles.ROLE_IMAGE_KEYS.get(role, [])
        role_images = {k: v for k, v in self.image_mapping.items() if k in role_image_keys}

        docs_to_save = {cat: [] for cat in profiles.ATTACHMENT_CATEGORIES}
        for cat, paths in self.session_docs.get(role, {}).items():
            for fpath in paths:
                if os.path.exists(fpath):
                    docs_to_save[cat].append(fpath)

        if loaded_pid:
            # User selected a profile, so they intend to modify it.
            # We must translate current role's image keys back to the profile's original role
            existing_profile = profiles.get_profile(loaded_pid)
            source_role = existing_profile.get("role", role)

            translated_role_images = {}
            for img_key, img_path in role_images.items():
                translated_key = self._translate_key(img_key, role, source_role)
                translated_role_images[translated_key] = img_path

            # FIX BUG 4: Pass source_role so update_profile knows which keys to filter
            profiles.update_profile(loaded_pid, data, translated_role_images, docs_to_save, source_role=source_role)
            self.session_docs[role] = {c: [] for c in profiles.ATTACHMENT_CATEGORIES}
            for r in profiles.PARTNER_ROLES:
                self.refresh_profile_menu(r)

            for lbl, pid in self.profile_maps.get(role, {}).items():
                if pid == loaded_pid:
                    self._set_combo_text_silent(self.profile_menus[role], lbl)
                    break

            self._refresh_partner_docs(role)
            self._update_profile_button_state(role)
            logger.info(f"Updated profile {loaded_pid} ({role})")
            QMessageBox.information(self, "Updated", "Profile updated successfully with the latest changes.")
        else:
            # User began from blank, prompt to save as a new profile
            name, ok = QInputDialog.getText(self, "Save Profile", "Enter a name for this profile:")
            if not ok or not name.strip():
                return
            name = name.strip()

            new_pid = profiles.save_profile(name, role, data, role_images, docs_to_save)
            self.session_docs[role] = {c: [] for c in profiles.ATTACHMENT_CATEGORIES}
            for r in profiles.PARTNER_ROLES:
                self.refresh_profile_menu(r)

            for lbl, pid in self.profile_maps.get(role, {}).items():
                if pid == new_pid:
                    self._set_combo_text_silent(self.profile_menus[role], lbl)
                    break

            self._refresh_partner_docs(role)
            self._update_profile_button_state(role)
            doc_count = sum(len(v) for v in docs_to_save.values())
            logger.info(f"Saved new profile '{name}' ({role}) with {len(role_images)} images and {doc_count} docs")
            msg = f'Profile "{name}" saved'
            if role_images: msg += f" with {len(role_images)} images"
            if doc_count: msg += f" and {doc_count} docs"
            QMessageBox.information(self, "Saved", msg)

    def delete_selected_profile(self, role):
        menu = self.profile_menus.get(role)
        if menu is None:
            return
        choice = menu.currentText()
        profile_id = self.profile_maps.get(role, {}).get(choice)
        if not profile_id:
            QMessageBox.information(self, "Delete Profile", "Select a saved profile first.")
            return
        reply = QMessageBox.question(
            self, "Delete", f'Delete profile "{choice.split(' [')[0]}"?',
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            profiles.delete_profile(profile_id)
            for r in profiles.PARTNER_ROLES:
                self.refresh_profile_menu(r)

            self.session_docs[role] = {c: [] for c in profiles.ATTACHMENT_CATEGORIES}
            self._clear_role_state(role)
            self._refresh_partner_docs(role)
            self._update_jv_name_suggestion()
            self._update_percentage_total()
            self._clear_doc_preview(role)
            self._update_profile_button_state(role)
            logger.info(f"Deleted profile {profile_id} ({role})")

    def setup_project_tab(self):
        layout = QVBoxLayout(self.tab_project)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        left_grid = SectionedFormGrid(
            content,
            [
                (0, 4, "Project identity", "Define the bid and employer context."),
                (5, 9, "Bid settings", "Set timing, validity, and document conventions."),
            ],
        )
        scroll.setWidget(content)
        layout.addWidget(scroll)

        fields = [
            ("JV_NAME", "JV Name", False, None),
            ("JV_ADDRESS", "JV Address", True, []),
            ("PROJECT_NAME", "Project Name", False, None),
            ("IFB_NUMBER", "IFB Number", False, None),
            ("BID_DATE", "Bid Date", False, None),
            ("BID_VALIDITY_PERIOD", "Validity Period", False, None),
            ("EMPLOYER_NAME", "Employer Name", False, None),
            ("EMPLOYER_ADDRESS", "Employer Address", False, None),
        ]
        for i, (key, label, is_c, vals) in enumerate(fields):
            self.create_field(left_grid, i, label, key, is_c, vals)

        self.create_combo_field_with_upload(
            left_grid, len(fields),
            "Authorized Person Name", "AUTHORIZED_PERSON_NAME", "AUTHORISED_SIG",
        )
        self.entries["AUTHORIZED_PERSON_NAME"].currentTextChanged.connect(
            lambda _t: self._sync_authorised_signature()
        )

        self.set_form_value("BID_DATE", datetime.now().strftime("%Y-%m-%d"))
        self.set_form_value("AUTHORIZED_PERSON_NAME", "")
        self.set_form_value("BID_VALIDITY_PERIOD", "120 days")

        self.entries["JV_NAME"].textChanged.connect(lambda _t: self._on_jv_name_keyrelease())

    def setup_lead_tab(self):
        content, grid = self._make_scroll_grid(
            self.tab_lead,
            [
                (0, 0, "Bid type", "Choose whether this is a joint venture or a single-partner bid."),
                (1, 1, "Partner profile", "Load a reusable profile or save the current details."),
                (2, 4, "Organisation details", "Enter the lead partner identity and address."),
                (5, 7, "Authorised persons", "Add signatories and their supporting signatures."),
                (8, 8, "Ownership", "The lead partner share must contribute to a 100% total."),
                (9, 99, "Supporting documents", "Attach evidence required for this partner."),
            ],
        )

        # Explicitly create a strict (non-editable) dropdown for Bid Type
        bid_type_label = QLabel("Bid Type")
        bid_type_label.setObjectName("FieldLabel")
        bid_type_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grid.addWidget(bid_type_label, 0, 0)
        self.labels["BID_TYPE"] = bid_type_label
        
        bid_type_combo = QComboBox()
        bid_type_combo.addItems(["Joint Venture", "Single Bidder"])
        bid_type_combo.setMinimumWidth(280)
        bid_type_combo.setEditable(False)  # Prevents typing custom text
        grid.addWidget(bid_type_combo, 0, 1)
        self.entries["BID_TYPE"] = bid_type_combo
        
        self.set_form_value("BID_TYPE", "Joint Venture")
        bid_type_combo.currentTextChanged.connect(self._on_bid_type_changed)

        self.create_profile_bar(grid, "lead", row=1)

        self.create_field_with_upload(grid, 2, "Name", "LEAD_PARTNER_NAME", "LEAD_STAMP")
        self.entries["LEAD_PARTNER_NAME"].textChanged.connect(lambda _t: self._on_lead_name_changed_for_single_bidder())
        self.create_field(grid, 3, "Short Name", "LEAD_PARTNER_SHORT")
        self.create_field(grid, 4, "Address", "LEAD_ADDRESS")
        self.create_field_with_upload(grid, 5, "CEO/Authorised Person", "LEAD_PARTNER_CEO", "LEAD_CEO_SIG")
        self.create_field_with_upload(grid, 6, "Managing Director", "LEAD_PARTNER_MD1", "LEAD_PARTNER_MD1")
        self.create_field_with_upload(grid, 7, "Managing Director", "LEAD_PARTNER_MD2", "LEAD_PARTNER_MD2")
        self.create_field(grid, 8, "Lead Percentage (%)", "L_PER", mono=True)

        self.entries["LEAD_PARTNER_SHORT"].textChanged.connect(
            lambda _t: self._on_short_name_keyrelease_qt(self.entries["LEAD_PARTNER_SHORT"])
        )
        self.entries["L_PER"].textChanged.connect(lambda _t: self._update_percentage_total())
        self.entries["LEAD_ADDRESS"].textChanged.connect(lambda _t: self._update_jv_address_options())
        self.entries["LEAD_PARTNER_CEO"].textChanged.connect(lambda _t: self._update_authorised_person_options())

        # NEW: Keep Firm's Address in sync with lead address for Single Bidder mode
        self.entries["LEAD_ADDRESS"].textChanged.connect(lambda _t: self._on_lead_address_changed_for_single_bidder())

        self._build_partner_docs_section(grid, "lead")

    def setup_partners_tab(self):
        content_first, grid_first = self._make_scroll_grid(
            self.tab_first,
            [
                (0, 0, "Partner profile", "Load a reusable profile or save the current details."),
                (1, 3, "Organisation details", "Enter the first partner identity and address."),
                (4, 6, "Authorised persons", "Add signatories and their supporting signatures."),
                (7, 7, "Ownership", "The first partner share must contribute to a 100% total."),
                (8, 99, "Supporting documents", "Attach evidence required for this partner."),
            ],
        )

        self.create_profile_bar(grid_first, "first", row=0)

        self.create_field_with_upload(grid_first, 1, "Name", "FIRST_PARTNER_NAME", "FIRST_STAMP")
        self.create_field(grid_first, 2, "Short Name", "FIRST_PARTNER_SHORT")
        self.create_field(grid_first, 3, "Address", "FIRST_ADDRESS")
        self.create_field_with_upload(grid_first, 4, "CEO/Authorised Person", "FIRST_PARTNER_CEO", "FIRST_CEO_SIG")
        self.create_field_with_upload(grid_first, 5, "Managing Director", "FIRST_PARTNER_MD1", "FIRST_PARTNER_MD1")
        self.create_field_with_upload(grid_first, 6, "Managing Director", "FIRST_PARTNER_MD2", "FIRST_PARTNER_MD2")
        self.create_field(grid_first, 7, "First Percentage (%)", "F_PER", mono=True)

        self.entries["FIRST_PARTNER_SHORT"].textChanged.connect(
            lambda _t: self._on_short_name_keyrelease_qt(self.entries["FIRST_PARTNER_SHORT"])
        )
        self.entries["F_PER"].textChanged.connect(lambda _t: self._update_percentage_total())
        self.entries["FIRST_ADDRESS"].textChanged.connect(lambda _t: self._update_jv_address_options())
        self.entries["FIRST_PARTNER_CEO"].textChanged.connect(lambda _t: self._update_authorised_person_options())

        self._build_partner_docs_section(grid_first, "first")

        content_second, grid_second = self._make_scroll_grid(
            self.tab_second,
            [
                (0, 0, "Partner profile", "Load a reusable profile or save the current details."),
                (1, 3, "Organisation details", "Enter the second partner identity and address."),
                (4, 6, "Authorised persons", "Add signatories and their supporting signatures."),
                (7, 7, "Ownership", "The second partner share must contribute to a 100% total."),
                (8, 99, "Supporting documents", "Attach evidence required for this partner."),
            ],
        )

        self.create_profile_bar(grid_second, "second", row=0)

        self.create_field_with_upload(grid_second, 1, "Name", "SECOND_PARTNER_NAME", "SECOND_STAMP")
        self.create_field(grid_second, 2, "Short Name", "SECOND_PARTNER_SHORT")
        self.create_field(grid_second, 3, "Address", "SECOND_ADDRESS")
        self.create_field_with_upload(grid_second, 4, "CEO/Authorised Person", "SECOND_PARTNER_CEO", "SECOND_CEO_SIG")
        self.create_field_with_upload(grid_second, 5, "Managing Director", "SECOND_PARTNER_MD1", "SECOND_PARTNER_MD1")
        self.create_field_with_upload(grid_second, 6, "Managing Director", "SECOND_PARTNER_MD2", "SECOND_PARTNER_MD2")
        self.create_field(grid_second, 7, "Second Percentage (%)", "S_PER", mono=True)

        self.entries["SECOND_PARTNER_SHORT"].textChanged.connect(
            lambda _t: self._on_short_name_keyrelease_qt(self.entries["SECOND_PARTNER_SHORT"])
        )
        self.entries["S_PER"].textChanged.connect(lambda _t: self._update_percentage_total())
        self.entries["SECOND_ADDRESS"].textChanged.connect(lambda _t: self._update_jv_address_options())
        self.entries["SECOND_PARTNER_CEO"].textChanged.connect(lambda _t: self._update_authorised_person_options())

        self._build_partner_docs_section(grid_second, "second")

    def upload_image(self, key):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Image files (*.png *.jpg *.jpeg)"
        )
        if file_path:
            assets_dir = self.app_root / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            suffix = Path(file_path).suffix.lower()
            if suffix not in (".png", ".jpg", ".jpeg"):
                QMessageBox.warning(self, "Unsupported image", "Please select a PNG or JPEG image.")
                return
            dest = assets_dir / f"{key}{suffix}"
            try:
                shutil.copy2(file_path, dest)
            except OSError as exc:
                QMessageBox.critical(self, "Upload failed", f"Could not copy the image:\n{exc}")
                return
            self.image_mapping[key] = str(dest)
            status_label = getattr(self, f"status_{key}")
            self._mark_status(status_label, True)
            logger.info(f"Uploaded image for {key}: {file_path}")

            if key in PARTNER_CEO_FIELD_TO_SIG.values():
                self._sync_authorised_signature()

    def _refresh_combo_options(self, combo_key, source_keys):
        combo = self.entries.get(combo_key)
        if combo is None:
            return
        current_text = combo.currentText()
        values = []
        for key in source_keys:
            val = self.get_form_value(key).strip()
            if val and val not in values:
                values.append(val)
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(values)
        combo.setCurrentText(current_text)
        combo.blockSignals(False)

    def _update_jv_address_options(self):
        self._refresh_combo_options("JV_ADDRESS", PARTNER_ADDRESS_FIELDS)

    def _update_authorised_person_options(self):
        self._refresh_combo_options(
            "AUTHORIZED_PERSON_NAME", tuple(PARTNER_CEO_FIELD_TO_SIG.keys())
        )

    def _sync_authorised_signature(self):
        combo = self.entries.get("AUTHORIZED_PERSON_NAME")
        if combo is None:
            return
        selected_name = combo.currentText().strip()
        status_label = getattr(self, "status_AUTHORISED_SIG", None)
        if not selected_name:
            return

        matched_sig_key = None
        for ceo_field, sig_key in PARTNER_CEO_FIELD_TO_SIG.items():
            if self.get_form_value(ceo_field).strip() == selected_name:
                matched_sig_key = sig_key
                break

        if matched_sig_key is None:
            return

        source_path = self.image_mapping.get(matched_sig_key)
        if source_path and os.path.exists(source_path):
            # AUTHORISED_SIG is just an alias for the matched partner's CEO
            # signature — point at the same file directly rather than
            # copying it into assets/. Wherever source_path already lives
            # (a profile, a draft, or a fresh scratch upload) is fine;
            # doc_generator just reads whatever path it's given.
            self.image_mapping["AUTHORISED_SIG"] = source_path
            if status_label:
                self._mark_status(status_label, True)
            logger.info(f"Authorised Person signature synced from {matched_sig_key}")
        else:
            self.image_mapping.pop("AUTHORISED_SIG", None)
            if status_label:
                self._mark_status(status_label, False)

    def _on_bid_type_changed(self, mode):
        """Switch UI between Joint Venture and Single Bidder modes."""
        is_single = (mode == "Single Bidder")

        # NEW: Update project tab labels based on mode
        jv_name_label = self.labels.get("JV_NAME")
        jv_addr_label = self.labels.get("JV_ADDRESS")
        if jv_name_label:
            jv_name_label.setText("Firm's Name" if is_single else "JV Name")
        if jv_addr_label:
            jv_addr_label.setText("Firm's Address" if is_single else "JV Address")

        # NEW: Enable/disable partner tabs in sidebar
        self._partner_tabs_enabled = not is_single
        if hasattr(self.sidebar, 'set_module_enabled'):
            self.sidebar.set_module_enabled("first", not is_single)
            self.sidebar.set_module_enabled("second", not is_single)
        
        # NEW: If currently on a disabled tab, switch to lead
        current_idx = self.stacked.currentIndex()
        if is_single and current_idx in (MODULE_ORDER.index("first"), MODULE_ORDER.index("second")):
            self._navigate("lead")

        if is_single:
            lead_name = self.get_form_value("LEAD_PARTNER_NAME").strip()
            self._setting_jv_name_auto = True
            self.set_form_value("JV_NAME", lead_name)
            self._setting_jv_name_auto = False
            self.entries["JV_NAME"].setEnabled(False)
            
            # NEW: Auto-fill Firm's Address from lead address
            lead_addr = self.get_form_value("LEAD_ADDRESS").strip()
            self._setting_jv_name_auto = True
            self.set_form_value("JV_ADDRESS", lead_addr)
            self._setting_jv_name_auto = False
            self.entries["JV_ADDRESS"].setEnabled(False)
        else:
            self.entries["JV_NAME"].setEnabled(True)
            self.entries["JV_ADDRESS"].setEnabled(True)
            self._update_jv_name_suggestion()
            self._update_jv_address_options()

        if is_single:
            self.set_form_value("L_PER", "100")
            self.entries["L_PER"].setEnabled(False)
            for key in ("F_PER", "S_PER"):
                entry = self.entries.get(key)
                if entry:
                    self.set_form_value(key, "")
                    entry.setEnabled(False)
        else:
            self.entries["L_PER"].setEnabled(True)
            for key in ("F_PER", "S_PER"):
                entry = self.entries.get(key)
                if entry:
                    entry.setEnabled(True)

        self._update_percentage_total()

    def _on_lead_name_changed_for_single_bidder(self):
        """Keep JV_NAME synced with lead name when in Single Bidder mode."""
        if self.get_form_value("BID_TYPE") == "Single Bidder":
            lead_name = self.get_form_value("LEAD_PARTNER_NAME").strip()
            self._setting_jv_name_auto = True
            self.set_form_value("JV_NAME", lead_name)
            self._setting_jv_name_auto = False

    def _on_lead_address_changed_for_single_bidder(self):
        """Keep Firm's Address synced with lead address when in Single Bidder mode."""
        if self.get_form_value("BID_TYPE") == "Single Bidder":
            lead_addr = self.get_form_value("LEAD_ADDRESS").strip()
            self._setting_jv_name_auto = True
            self.set_form_value("JV_ADDRESS", lead_addr)
            self._setting_jv_name_auto = False

    def _on_jv_name_keyrelease(self):
        if getattr(self, "_setting_jv_name_auto", False):
            return
        self._jv_name_manual = True

    def _on_short_name_keyrelease_qt(self, entry):
        try:
            current = entry.text()
            upper = current.upper()
            if current != upper:
                cursor = entry.cursorPosition()
                entry.blockSignals(True)
                entry.setText(upper)
                entry.setCursorPosition(cursor)
                entry.blockSignals(False)
        except Exception:
            pass
        self._update_jv_name_suggestion()

    def _update_jv_name_suggestion(self):
        if getattr(self, "_jv_name_manual", False):
            return
        if self.get_form_value("BID_TYPE") == "Single Bidder":
            lead = self.get_form_value("LEAD_PARTNER_NAME").strip()
            self._setting_jv_name_auto = True
            self.set_form_value("JV_NAME", lead)
            self._setting_jv_name_auto = False
            return
        lead = self.get_form_value("LEAD_PARTNER_SHORT").strip()
        first = self.get_form_value("FIRST_PARTNER_SHORT").strip()
        second = self.get_form_value("SECOND_PARTNER_SHORT").strip()
        parts = [p for p in (lead, first, second) if p]
        if not parts:
            return
        suggestion = " - ".join(parts) + " J/V"

        self._setting_jv_name_auto = True
        self.set_form_value("JV_NAME", suggestion)
        self._setting_jv_name_auto = False

    def _parse_percent(self, key):
        val = self.get_form_value(key).strip().replace("%", "")
        try:
            return float(val) if val else 0.0
        except ValueError:
            return 0.0

    def _update_percentage_total(self):
        if self.get_form_value("BID_TYPE") == "Single Bidder":
            if hasattr(self, "top_bar"):
                self.top_bar.set_percentage(100.0, True)
            return 100.0
        total = (
            self._parse_percent("L_PER")
            + self._parse_percent("F_PER")
            + self._parse_percent("S_PER")
        )
        if hasattr(self, "top_bar"):
            ok = abs(total - 100.0) < 0.01
            self.top_bar.set_percentage(total, ok)
        return total

    def clear_fields(self):
        reply = QMessageBox.question(
            self, "Confirm", "Clear all entered data?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._do_clear_fields()
        self._refresh_draft_selector()

    def _do_clear_fields(self):
        self._current_draft_id = None


        for entry in self.entries.values():
            entry.blockSignals(True)
            if isinstance(entry, QComboBox):
                if entry.count() > 0:
                    entry.setCurrentIndex(0)
            else:
                entry.clear()
            entry.blockSignals(False)
        self.image_mapping = {}

        all_image_keys = [
            "LEAD_STAMP", "LEAD_CEO_SIG", "LEAD_PARTNER_MD1", "LEAD_PARTNER_MD2",
            "FIRST_STAMP", "FIRST_CEO_SIG", "FIRST_PARTNER_MD1", "FIRST_PARTNER_MD2",
            "SECOND_STAMP", "SECOND_CEO_SIG", "SECOND_PARTNER_MD1", "SECOND_PARTNER_MD2",
            "AUTHORISED_SIG",
        ]
        for img_key in all_image_keys:
            status_label = getattr(self, f"status_{img_key}", None)
            if status_label:
                self._mark_status(status_label, False)

        self.session_docs = {
            r: {c: [] for c in profiles.ATTACHMENT_CATEGORIES}
            for r in profiles.PARTNER_ROLES
        }
        for role in profiles.PARTNER_ROLES:
            if role in self.profile_menus:
                self._set_combo_text_silent(self.profile_menus[role], "-- No profile --")
                self._update_profile_button_state(role)
            self._refresh_partner_docs(role)
            self._clear_doc_preview(role)

        if hasattr(self, "pdf_viewer_layout"):
            self._clear_layout(self.pdf_viewer_layout)
            self.pdf_images = []
            self._employer_pdf_path = None
            self._employer_pdf_page_count = 0
            self._employer_pdf_page_index = 0

        self.set_form_value("BID_DATE", datetime.now().strftime("%Y-%m-%d"))
        self.set_form_value("AUTHORIZED_PERSON_NAME", "Authorized person of JV")
        self.set_form_value("BID_VALIDITY_PERIOD", "120 days")
        self.set_form_value("BID_TYPE", "Joint Venture")

        self._jv_name_manual = False
        self._on_bid_type_changed("Joint Venture")
        self._update_jv_name_suggestion()
        self._update_percentage_total()

        self._update_jv_address_options()
        self._update_authorised_person_options()

    def _refresh_draft_selector(self):
        saved = drafts.list_drafts()
        self.sidebar.set_drafts(
            [{"id": d["id"], "name": d["name"]} for d in saved],
            current_draft_id=self._current_draft_id,
        )

    def _on_new_bid_requested(self):
        reply = QMessageBox.question(
            self, "New Bid",
            "Start a new bid? Unsaved changes to the current one will be "
            "lost unless you save it first.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self._refresh_draft_selector()
            return
        self._do_clear_fields()
        self._refresh_draft_selector()

    def _on_draft_selected(self, draft_id):
        if draft_id == (self._current_draft_id or ""):
            return

        if not draft_id:
            self._current_draft_id = None
            self._refresh_draft_selector()
            return

        reply = QMessageBox.question(
            self, "Load Draft",
            "Load this draft? Unsaved changes to the current bid will be "
            "lost unless you save it first.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self._refresh_draft_selector()
            return
        self._load_draft(draft_id)

    def _on_save_draft_requested(self):
        field_data = {k: self._entry_value(v) for k, v in self.entries.items()}
        linked_profiles = {
            role: self._get_loaded_profile_id(role)
            for role in profiles.PARTNER_ROLES
            if self._get_loaded_profile_id(role)
        }
        session_docs_snapshot = {
            role: {cat: list(paths) for cat, paths in cats.items()}
            for role, cats in self.session_docs.items()
        }

        if self._current_draft_id:
            existing = drafts.get_draft(self._current_draft_id)
            name = existing["name"] if existing else "Untitled Bid"
            drafts.save_draft(
                name, field_data, self.image_mapping, linked_profiles,
                session_docs_snapshot, self._employer_pdf_path,
                draft_id=self._current_draft_id,
            )
            logger.info(f"Updated draft {self._current_draft_id}")
            QMessageBox.information(self, "Saved", f'"{name}" updated.')
        else:
            name, ok = QInputDialog.getText(self, "Save Bid", "Enter a name for this bid:")
            if not ok or not name.strip():
                return
            name = name.strip()
            new_id = drafts.save_draft(
                name, field_data, self.image_mapping, linked_profiles,
                session_docs_snapshot, self._employer_pdf_path,
            )
            self._current_draft_id = new_id
            logger.info(f"Saved new draft '{name}' ({new_id})")
            QMessageBox.information(self, "Saved", f'"{name}" saved.')

        self._refresh_draft_selector()

    def _on_delete_draft_requested(self):
        if not self._current_draft_id:
            return
        existing = drafts.get_draft(self._current_draft_id)
        name = existing["name"] if existing else "this draft"
        reply = QMessageBox.question(
            self, "Delete Draft", f'Delete "{name}"? This cannot be undone.',
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        drafts.delete_draft(self._current_draft_id)
        logger.info(f"Deleted draft {self._current_draft_id}")
        self._current_draft_id = None
        self._refresh_draft_selector()

    def _load_draft(self, draft_id):
        draft = drafts.get_draft(draft_id)
        if not draft:
            QMessageBox.critical(self, "Error", "That draft could not be found.")
            self._current_draft_id = None
            self._refresh_draft_selector()
            return

        self._do_clear_fields()

        for key, value in drafts.get_field_data(draft).items():
            self.set_form_value(key, value)

        self.image_mapping = drafts.load_draft_images_to_assets(draft_id)
        for img_key in self.image_mapping:
            status_label = getattr(self, f"status_{img_key}", None)
            if status_label:
                self._mark_status(status_label, True)

        linked_profiles = drafts.get_linked_profiles(draft)
        for role, profile_id in linked_profiles.items():
            if role not in self.profile_menus or not profile_id:
                continue
            self.refresh_profile_menu(role)
            for label, pid in self.profile_maps.get(role, {}).items():
                if pid == profile_id:
                    self._set_combo_text_silent(self.profile_menus[role], label)
                    self._update_profile_button_state(role)
                    break

        session_docs_data = drafts.get_session_docs(draft)
        for role in profiles.PARTNER_ROLES:
            role_docs = session_docs_data.get(role, {})
            self.session_docs[role] = {
                cat: [p for p in role_docs.get(cat, []) if os.path.exists(p)]
                for cat in profiles.ATTACHMENT_CATEGORIES
            }
            self._refresh_partner_docs(role)

        # Always clear the previous draft's PDF before loading this draft.
        # Otherwise a draft without a valid PDF inherits an unrelated viewer.
        self._clear_employer_pdf()
        employer_pdf_path = draft.get("employer_pdf_path") or ""
        if employer_pdf_path and os.path.exists(employer_pdf_path):
            self._set_employer_pdf(employer_pdf_path, notify_on_error=False)

        self._jv_name_manual = True
        self._update_jv_address_options()
        self._update_authorised_person_options()
        self._sync_authorised_signature()
        self._update_percentage_total()

        # NEW: Refresh UI state for the loaded bid type (Single vs JV)
        self._on_bid_type_changed(self.get_form_value("BID_TYPE"))

        self._current_draft_id = draft_id
        self._refresh_draft_selector()
        logger.info(f"Loaded draft '{draft['name']}' ({draft_id})")

    def _get_loaded_profile_id(self, role):
        menu = self.profile_menus.get(role)
        if not menu:
            return None
        choice = menu.currentText()
        return self.profile_maps.get(role, {}).get(choice)

    def _translate_key(self, key, from_role, to_role):
        if from_role == to_role:
            return key
        from_pre = ROLE_PREFIXES[from_role]
        to_pre = ROLE_PREFIXES[to_role]
        if key == PERCENTAGE_KEYS.get(from_role):
            return PERCENTAGE_KEYS.get(to_role, key)
        if key.startswith(from_pre + "_"):
            return to_pre + "_" + key[len(from_pre) + 1:]
        return key

    def _validate_bid(self, data):
        """Return user-facing validation errors before document generation."""
        errors = []
        is_single = data.get("BID_TYPE", "Joint Venture") == "Single Bidder"

        required_fields = {
            "PROJECT_NAME": "Project name",
            "BID_DATE": "Bid date",
            "EMPLOYER_NAME": "Employer name",
            "LEAD_PARTNER_NAME": "Lead partner name",
            "LEAD_ADDRESS": "Lead partner address",
        }
        if not is_single:
            required_fields["JV_NAME"] = "JV name"
        for key, label in required_fields.items():
            if not str(data.get(key, "")).strip():
                errors.append(f"{label} is required.")

        try:
            datetime.strptime(str(data.get("BID_DATE", "")).strip(), "%Y-%m-%d")
        except ValueError:
            errors.append("Bid date must use YYYY-MM-DD format.")

        if not is_single:
            percent_values = {}
            for key, label in (("L_PER", "Lead"), ("F_PER", "First partner"), ("S_PER", "Second partner")):
                raw = str(data.get(key, "")).strip().replace("%", "")
                if not raw:
                    percent_values[key] = 0.0
                    continue
                try:
                    value = float(raw)
                except ValueError:
                    errors.append(f"{label} ownership percentage must be numeric.")
                    continue
                if not 0 <= value <= 100:
                    errors.append(f"{label} ownership percentage must be between 0 and 100.")
                percent_values[key] = value

            if not errors or all(key in percent_values for key in ("L_PER", "F_PER", "S_PER")):
                total = sum(percent_values.values())
                if abs(total - 100.0) > 0.01:
                    errors.append(f"Ownership percentages must total 100%; current total is {total:.2f}%.")

        lead = bool(str(data.get("LEAD_PARTNER_NAME", "")).strip())
        first = bool(str(data.get("FIRST_PARTNER_NAME", "")).strip())
        second = bool(str(data.get("SECOND_PARTNER_NAME", "")).strip())
        if not lead:
            errors.append("At least the lead partner must be provided.")

        if not is_single:
            if second and not first:
                errors.append("The first partner must be filled before adding a second partner.")

            for role, prefix in (("first", "FIRST"), ("second", "SECOND")):
                if str(data.get(f"{prefix}_PARTNER_NAME", "")).strip():
                    for suffix, label in (("ADDRESS", "address"), ("PARTNER_CEO", "CEO/authorised person")):
                        if not str(data.get(f"{prefix}_{suffix}", "")).strip():
                            errors.append(f"{role.title()} partner {label} is required.")

        if "AUTHORISED_SIG" not in self.image_mapping:
            errors.append("An authorised-person signature image is required.")
        return errors



    def split_generated_doc(self):
        """Convert a selected .docx to PDF and split into section PDFs."""
        docx_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Word Document",
            str(Path.home()),
            "Word Documents (*.docx)",
        )
        if not docx_path:
            return

        # Convert .docx to PDF
        try:
            pdf_path = self.generator.convert_to_pdf(docx_path)
        except Exception as e:
            QMessageBox.critical(
                self, "Conversion Failed",
                f"Could not convert the document to PDF:\n{e}"
            )
            return

        options = ["1 partner", "2 partners", "3 partners"]
        selected, ok = QInputDialog.getItem(
            self,
            "Select bid layout",
            "How many partners does this document contain?",
            options,
            1,  # default to 2 partners
            False,
        )
        if not ok:
            return
        partner_count = options.index(selected) + 1

        out_dir = QFileDialog.getExistingDirectory(
            self, "Choose folder for split section PDFs", str(Path(pdf_path).parent),
        )
        if not out_dir:
            return

        try:
            written, warnings = pdf_export.split_and_compress(
                pdf_path, partner_count, out_dir,
            )
        except Exception as e:
            QMessageBox.critical(self, "Split Failed", str(e))
            return

        msg = f"Wrote {len(written)} section PDFs to:\n{out_dir}"
        if warnings:
            msg += "\n\nWarnings:\n- " + "\n- ".join(warnings)
        QMessageBox.information(self, "Split Complete", msg)
        logger.info(f"Split {pdf_path} into {len(written)} section PDFs in {out_dir}")

        try:
            if sys.platform == "win32":
                os.startfile(out_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", out_dir])
            else:
                subprocess.Popen(["xdg-open", out_dir])
        except Exception as e:
            logger.error(f"Failed to open folder: {e}")

    def generate_doc(self):
        data = {k: self._entry_value(v) for k, v in self.entries.items()}
        validation_errors = self._validate_bid(data)
        if validation_errors:
            QMessageBox.warning(
                self,
                "Please correct the bid",
                "Generation was stopped because of the following issues:\n\n- "
                + "\n- ".join(validation_errors),
            )
            return

        # Normalize percentage values without adding unnecessary .00 suffixes.
        for pct_key in ("L_PER", "F_PER", "S_PER"):
            if pct_key in data:
                data[pct_key] = format_percentage(
                    str(data[pct_key]).strip().replace("%", "")
                )
                if data[pct_key]:
                    data[pct_key] += "%"

        total_pct = self._update_percentage_total()
        if abs(total_pct - 100.0) > 0.01:
            QMessageBox.critical(
                self, "Invalid Percentage Split",
                "Partner percentage shares must add up to 100%.\n"
                "Current total: {:.2f}%".format(total_pct),
            )
            return

        is_single = data.get("BID_TYPE", "Joint Venture") == "Single Bidder"
        data["AND_CONNECTOR"] = "" if is_single else "And"
        second_partner_name = data.get("SECOND_PARTNER_NAME", "")
        data["HAS_THIRD_PARTNER"] = "False" if self.generator.is_empty_value(second_partner_name) else "True"
        if is_single:
            data["L_PER"] = "100%"
            data["F_PER"] = ""
            data["S_PER"] = ""

        data["AUTHORIZED_CAPACITY"] = "Authorised person of JV"

        try:
            output = self.generator.generate(data, self.image_mapping)

            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setWindowTitle("Success")
            msg_box.setText("Professional Bid Generated Successfully!")
            msg_box.setInformativeText(f"Location:\n{output}")

            open_btn = msg_box.addButton("Open Folder", QMessageBox.ActionRole)
            msg_box.addButton(QMessageBox.Ok)

            msg_box.exec()

            if msg_box.clickedButton() == open_btn:
                folder_path = os.path.dirname(str(output))
                try:
                    if sys.platform == "win32":
                        os.startfile(folder_path)
                    elif sys.platform == "darwin":
                        subprocess.Popen(["open", folder_path])
                    else:
                        subprocess.Popen(["xdg-open", folder_path])
                except Exception as e:
                    logger.error(f"Failed to open folder: {e}")

        except Exception as e:
            QMessageBox.critical(self, "Error", "Generation Failed: {}".format(e))

    def change_appearance_mode_event(self, new_appearance_mode: str):
        app = QApplication.instance()
        app.setStyleSheet(theme.build_qss(new_appearance_mode))
        # Drop shadows removed for performance — keep only stylesheet swap
        if hasattr(self, "sidebar") and self.sidebar.theme_combo.currentText() != new_appearance_mode:
            self.sidebar.theme_combo.blockSignals(True)
            self.sidebar.theme_combo.setCurrentText(new_appearance_mode)
            self.sidebar.theme_combo.blockSignals(False)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())