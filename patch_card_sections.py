#!/usr/bin/env python3
"""Add card-based form sections to the Bididing-doc PySide6 frontend.

The patch keeps the existing ``create_field`` and signal wiring intact. It
introduces a small routing layout that places existing form rows into titled
cards, then adds matching QSS for the card surface and typography.

Usage:
    python patch_card_sections.py --repo /path/to/Bididing-doc
    python patch_card_sections.py --repo /path/to/Bididing-doc --check-only
"""

from __future__ import annotations

import argparse
import py_compile
import shutil
import sys
from pathlib import Path


FORM_CLASS = '''\n\nclass SectionedFormGrid:\n    """Route legacy row-based form calls into titled visual cards."""\n\n    def __init__(self, parent, sections):\n        self.parent = parent\n        self.sections = sections\n        self._next_row = 0\n        outer = QVBoxLayout(parent)\n        outer.setContentsMargins(0, 0, 0, 0)\n        outer.setSpacing(14)\n        self._cards = []\n        for start, end, title, subtitle in sections:\n            card = QFrame(parent)\n            card.setObjectName("FormCard")\n            card_layout = QVBoxLayout(card)\n            card_layout.setContentsMargins(16, 14, 16, 16)\n            card_layout.setSpacing(8)\n\n            heading = QLabel(title)\n            heading.setObjectName("CardTitle")\n            card_layout.addWidget(heading)\n            if subtitle:\n                description = QLabel(subtitle)\n                description.setObjectName("CardSubtitle")\n                description.setWordWrap(True)\n                card_layout.addWidget(description)\n\n            grid_host = QWidget(card)\n            grid = QGridLayout(grid_host)\n            grid.setContentsMargins(0, 6, 0, 0)\n            grid.setHorizontalSpacing(10)\n            grid.setVerticalSpacing(8)\n            card_layout.addWidget(grid_host)\n            outer.addWidget(card)\n            self._cards.append((start, end, grid))\n\n        outer.addStretch(1)\n\n    def _section_for_row(self, row):\n        for start, end, grid in self._cards:\n            if start <= row <= end:\n                return start, grid\n        return self._cards[-1][0], self._cards[-1][2]\n\n    def addWidget(self, widget, row, column, row_span=1, column_span=1, *args):\n        start, grid = self._section_for_row(row)\n        grid.addWidget(widget, row - start, column, row_span, column_span, *args)\n        self._next_row = max(self._next_row, row + row_span)\n\n    def rowCount(self):\n        return self._next_row\n'''

APP_REPLACEMENTS = [
    (
        'from format_utils import format_percentage\n',
        'from format_utils import format_percentage\n' + FORM_CLASS,
        "SectionedFormGrid definition",
    ),
    (
        '''    def _make_scroll_grid(self, parent_tab):\n        scroll = QScrollArea()\n        scroll.setWidgetResizable(True)\n        content = QWidget()\n        grid = QGridLayout(content)\n        grid.setContentsMargins(0, 0, 0, 0)\n        grid.setHorizontalSpacing(10)\n        grid.setVerticalSpacing(8)\n        scroll.setWidget(content)\n\n        parent_layout = QVBoxLayout(parent_tab)\n        parent_layout.setContentsMargins(0, 0, 0, 0)\n        parent_layout.addWidget(scroll)\n        return content, grid\n''',
        '''    def _make_scroll_grid(self, parent_tab, sections):\n        scroll = QScrollArea()\n        scroll.setWidgetResizable(True)\n        content = QWidget()\n        grid = SectionedFormGrid(content, sections)\n        scroll.setWidget(content)\n\n        parent_layout = QVBoxLayout(parent_tab)\n        parent_layout.setContentsMargins(0, 0, 0, 0)\n        parent_layout.addWidget(scroll)\n        return content, grid\n''',
        "sectioned scroll-grid factory",
    ),
    (
        '''        left_frame = QWidget()\n        left_grid = QGridLayout(left_frame)\n        layout.addWidget(left_frame)\n        layout.addStretch(1)\n''',
        '''        scroll = QScrollArea()\n        scroll.setWidgetResizable(True)\n        content = QWidget()\n        left_grid = SectionedFormGrid(\n            content,\n            [\n                (0, 4, "Project identity", "Define the bid and employer context."),\n                (5, 9, "Bid settings", "Set timing, validity, and document conventions."),\n            ],\n        )\n        scroll.setWidget(content)\n        layout.addWidget(scroll)\n''',
        "project card sections",
    ),
    (
        'content, grid = self._make_scroll_grid(self.tab_lead)\n',
        '''content, grid = self._make_scroll_grid(\n            self.tab_lead,\n            [\n                (0, 0, "Partner profile", "Load a reusable profile or save the current details."),\n                (1, 3, "Organisation details", "Enter the lead partner identity and address."),\n                (4, 6, "Authorised persons", "Add signatories and their supporting signatures."),\n                (7, 7, "Ownership", "The lead partner share must contribute to a 100% total."),\n                (8, 99, "Supporting documents", "Attach evidence required for this partner."),\n            ],\n        )\n''',
        "lead card sections",
    ),
    (
        'content_first, grid_first = self._make_scroll_grid(self.tab_first)\n',
        '''content_first, grid_first = self._make_scroll_grid(\n            self.tab_first,\n            [\n                (0, 0, "Partner profile", "Load a reusable profile or save the current details."),\n                (1, 3, "Organisation details", "Enter the first partner identity and address."),\n                (4, 6, "Authorised persons", "Add signatories and their supporting signatures."),\n                (7, 7, "Ownership", "The first partner share must contribute to a 100% total."),\n                (8, 99, "Supporting documents", "Attach evidence required for this partner."),\n            ],\n        )\n''',
        "first-partner card sections",
    ),
    (
        'content_second, grid_second = self._make_scroll_grid(self.tab_second)\n',
        '''content_second, grid_second = self._make_scroll_grid(\n            self.tab_second,\n            [\n                (0, 0, "Partner profile", "Load a reusable profile or save the current details."),\n                (1, 3, "Organisation details", "Enter the second partner identity and address."),\n                (4, 6, "Authorised persons", "Add signatories and their supporting signatures."),\n                (7, 7, "Ownership", "The second partner share must contribute to a 100% total."),\n                (8, 99, "Supporting documents", "Attach evidence required for this partner."),\n            ],\n        )\n''',
        "second-partner card sections",
    ),
]

THEME_INSERT = '''\n    /* ---------- Form cards ---------- */\n    QFrame#FormCard {{\n        background-color: {p['bg_surface']};\n        border: {sz['border']}px solid {p['border']};\n        border-radius: {r['lg']}px;\n    }}\n    QLabel#CardTitle {{\n        color: {p['text']}; font-size: 14px; font-weight: 700;\n    }}\n    QLabel#CardSubtitle {{\n        color: {p['text_muted']}; font-size: {f['size_sm']}px;\n    }}\n'''


def write_with_backup(path: Path, text: str) -> None:
    original = path.read_text(encoding="utf-8")
    if original == text:
        print(f"{path}: already patched")
        return
    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(text, encoding="utf-8")
    print(f"{path}: patched; backup={backup}")


def apply_replacements(path: Path, replacements: list[tuple[str, str, str]], check_only: bool) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new, label in replacements:
        if new in text:
            continue
        if old not in text:
            raise RuntimeError(f"Could not find patch target: {label}")
        text = text.replace(old, new, 1)
    if check_only:
        required = ["class SectionedFormGrid:", "def _make_scroll_grid(self, parent_tab, sections):"]
        if not all(item in text for item in required):
            raise RuntimeError(f"{path}: card patch is incomplete")
        print(f"{path}: card patch present")
    else:
        write_with_backup(path, text)


def patch_theme(path: Path, check_only: bool) -> None:
    text = path.read_text(encoding="utf-8")
    if "QFrame#FormCard" not in text:
        anchor = "    /* ---------- Scroll areas ---------- */\n"
        if anchor not in text:
            raise RuntimeError("Theme insertion anchor not found")
        text = text.replace(anchor, THEME_INSERT + "\n" + anchor, 1)
    if check_only:
        if "QFrame#FormCard" not in text or "QLabel#CardTitle" not in text:
            raise RuntimeError("theme.py: card styles are missing")
        print(f"{path}: card styles present")
    else:
        write_with_backup(path, text)


def smoke_check(app_path: Path, theme_path: Path) -> None:
    app = app_path.read_text(encoding="utf-8")
    theme = theme_path.read_text(encoding="utf-8")
    assert app.count("grid = SectionedFormGrid(content, sections)") == 1
    assert "left_grid = SectionedFormGrid(" in app
    assert app.count("self._make_scroll_grid(") == 3
    assert "Project identity" in app
    assert "Supporting documents" in app
    assert "QFrame#FormCard" in theme
    print("Smoke checks passed: card routing, section definitions, and QSS styles are present.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="Repository root")
    parser.add_argument("--check-only", action="store_true", help="Check without modifying files")
    args = parser.parse_args()

    source = args.repo.expanduser().resolve() / "Bidding-App-main"
    app_path = source / "app.py"
    theme_path = source / "theme.py"
    if not source.is_dir() or not app_path.is_file() or not theme_path.is_file():
        print(f"Error: expected frontend files were not found under {source}", file=sys.stderr)
        return 2

    try:
        apply_replacements(app_path, APP_REPLACEMENTS, args.check_only)
        patch_theme(theme_path, args.check_only)
        smoke_check(app_path, theme_path)
    except Exception as exc:
        print(f"Patch failed: {exc}", file=sys.stderr)
        return 1

    if args.check_only:
        return 0

    for path in (app_path, theme_path):
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            print(f"Compilation failed for {path}: {exc}", file=sys.stderr)
            return 1
        print(f"Compiled successfully: {path}")

    print("Card-section frontend patch completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

