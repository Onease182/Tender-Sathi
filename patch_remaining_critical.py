#!/usr/bin/env python3
"""Patch remaining critical state and output-safety bugs in Bididing-doc.

This script patches the local ``Bidding-App-main`` source tree to address:

1. profile deselection retaining old partner fields/images;
2. profile deletion retaining deleted image paths;
3. loading a draft retaining an unrelated employer PDF;
4. PDF splitting continuing after an unexpected page count.

The script is idempotent, creates ``.bak`` backups before editing files, and
runs syntax compilation plus focused text-level smoke checks.

Usage:
    python patch_remaining_critical.py --repo /path/to/Bididing-doc
    python patch_remaining_critical.py --repo /path/to/Bididing-doc --check-only
"""

from __future__ import annotations

import argparse
import py_compile
import shutil
import sys
from pathlib import Path


APP_HELPER = '''\n    def _clear_role_state(self, role):\n        """Clear form, image, and signature state for one partner role."""\n        field_map = profiles.ROLE_FIELD_KEYS.get(role, {})\n        for entry_key in field_map.values():\n            self.set_form_value(entry_key, "")\n\n        for img_key in profiles.ROLE_IMAGE_KEYS.get(role, []):\n            self.image_mapping.pop(img_key, None)\n            status_label = getattr(self, f"status_{img_key}", None)\n            if status_label:\n                self._mark_status(status_label, False)\n\n        self.image_mapping.pop("AUTHORISED_SIG", None)\n        auth_status = getattr(self, "status_AUTHORISED_SIG", None)\n        if auth_status:\n            self._mark_status(auth_status, False)\n'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 0:
        raise RuntimeError(f"Expected source block not found: {label}")
    if count > 1:
        raise RuntimeError(f"Source block is ambiguous ({count} matches): {label}")
    return text.replace(old, new, 1)


def patch_app(path: Path, check_only: bool) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "    def on_profile_selected(self, role, choice):\n"
    helper_present = "    def _clear_role_state(self, role):\n" in text

    if not helper_present:
        text = replace_once(text, marker, APP_HELPER + "\n" + marker, "App role-state helper")

    old_no_profile = '''        if not profile_id:\n            self.session_docs[role] = {c: [] for c in profiles.ATTACHMENT_CATEGORIES}\n            self._refresh_partner_docs(role)\n            self._update_jv_name_suggestion()\n            self._update_percentage_total()\n            self._clear_doc_preview(role)\n            return\n'''
    new_no_profile = '''        if not profile_id:\n            self._clear_role_state(role)\n            self.session_docs[role] = {c: [] for c in profiles.ATTACHMENT_CATEGORIES}\n            self._refresh_partner_docs(role)\n            self._update_jv_name_suggestion()\n            self._update_percentage_total()\n            self._clear_doc_preview(role)\n            return\n'''
    if old_no_profile in text:
        text = replace_once(text, old_no_profile, new_no_profile, "profile deselection cleanup")

    old_delete_cleanup = '''            field_map = profiles.ROLE_FIELD_KEYS[role]\n            for data_key, entry_key in field_map.items():\n                self.set_form_value(entry_key, "")\n\n            for img_key in profiles.ROLE_IMAGE_KEYS.get(role, []):\n                status_label = getattr(self, f"status_{img_key}", None)\n                if status_label:\n                    self._mark_status(status_label, False)\n\n            self._refresh_partner_docs(role)\n'''
    new_delete_cleanup = '''            self._clear_role_state(role)\n            self._refresh_partner_docs(role)\n'''
    if old_delete_cleanup in text:
        text = replace_once(text, old_delete_cleanup, new_delete_cleanup, "profile deletion cleanup")

    if check_only:
        if "self._clear_role_state(role)" not in text:
            raise RuntimeError("app.py still lacks role-state cleanup calls")
        print(f"{path}: patch present")
        return

    write_with_backup(path, text)


def patch_draft_pdf_reset(path: Path, check_only: bool) -> None:
    text = path.read_text(encoding="utf-8")
    old = '''        employer_pdf_path = draft.get("employer_pdf_path") or ""\n        if employer_pdf_path and os.path.exists(employer_pdf_path):\n            self._set_employer_pdf(employer_pdf_path, notify_on_error=False)\n'''
    new = '''        # Always clear the previous draft's PDF before loading this draft.\n        # Otherwise a draft without a valid PDF inherits an unrelated viewer.\n        self._clear_employer_pdf()\n        employer_pdf_path = draft.get("employer_pdf_path") or ""\n        if employer_pdf_path and os.path.exists(employer_pdf_path):\n            self._set_employer_pdf(employer_pdf_path, notify_on_error=False)\n'''
    if old in text:
        text = replace_once(text, old, new, "draft employer PDF reset")
    elif "self._clear_employer_pdf()" not in text:
        raise RuntimeError("Draft PDF reset block not found")

    if check_only:
        print(f"{path}: patch present")
        return
    write_with_backup(path, text)


def patch_pdf_export(path: Path, check_only: bool) -> None:
    text = path.read_text(encoding="utf-8")
    old = '''        if page_count != expected_pages:\n            warnings.append(\n                f"Expected {expected_pages} pages for a {partner_count}-partner "\n                f"bid but the generated PDF has {page_count}. Some sections "\n                "may not line up correctly — please check the split output "\n                "before submitting."\n            )\n'''
    new = '''        if page_count != expected_pages:\n            message = (\n                f"Expected {expected_pages} pages for a {partner_count}-partner "\n                f"bid but the generated PDF has {page_count}. Refusing to split "\n                "because fixed page offsets could produce mislabeled sections."\n            )\n            logger.error(message)\n            raise ValueError(message)\n'''
    if old in text:
        text = replace_once(text, old, new, "PDF page-count guard")
    elif "Refusing to split" not in text:
        raise RuntimeError("PDF page-count guard block not found")

    if check_only:
        print(f"{path}: patch present")
        return
    write_with_backup(path, text)


def write_with_backup(path: Path, text: str) -> None:
    original = path.read_text(encoding="utf-8")
    if text == original:
        print(f"{path}: already patched")
        return
    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(text, encoding="utf-8")
    print(f"{path}: patched; backup={backup}")


def run_smoke_checks(source_dir: Path) -> None:
    app_text = (source_dir / "app.py").read_text(encoding="utf-8")
    export_text = (source_dir / "pdf_export.py").read_text(encoding="utf-8")

    assert "def _clear_role_state(self, role):" in app_text
    assert app_text.count("self._clear_role_state(role)") >= 2
    assert "self._clear_employer_pdf()" in app_text
    assert "Refusing to split" in export_text
    print("Smoke checks passed: state cleanup, PDF reset, and page-count guard are present.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="Repository root")
    parser.add_argument("--check-only", action="store_true", help="Do not modify files")
    args = parser.parse_args()

    source_dir = args.repo.expanduser().resolve() / "Bidding-App-main"
    targets = [source_dir / "app.py", source_dir / "pdf_export.py"]
    if not source_dir.is_dir() or any(not path.is_file() for path in targets):
        print(f"Error: expected source files were not found under {source_dir}", file=sys.stderr)
        return 2

    try:
        patch_app(targets[0], args.check_only)
        patch_draft_pdf_reset(targets[0], args.check_only)
        patch_pdf_export(targets[1], args.check_only)
        run_smoke_checks(source_dir)
    except Exception as exc:
        print(f"Patch failed: {exc}", file=sys.stderr)
        return 1

    if args.check_only:
        return 0

    for path in targets:
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            print(f"Compilation failed for {path}: {exc}", file=sys.stderr)
            return 1
        print(f"Compiled successfully: {path}")

    print("Remaining critical-bug patch completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

