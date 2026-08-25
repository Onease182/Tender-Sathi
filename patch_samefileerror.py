#!/usr/bin/env python3
"""Patch SameFileError risks in the Bididing-doc image persistence code.

The patch adds a small copy helper to ``drafts.py`` and ``profiles.py``. The
helper resolves source and destination paths before copying and skips the copy
when both paths refer to the same file.

Usage:
    python patch_samefileerror.py
    python patch_samefileerror.py --repo /path/to/Bididing-doc
    python patch_samefileerror.py --repo /path/to/Bididing-doc --check-only
"""

from __future__ import annotations

import argparse
import hashlib
import py_compile
import shutil
import sys
from pathlib import Path


HELPER = '''\n\ndef _copy_if_different(source_path, destination_path):\n    """Copy a file unless source and destination resolve to the same path.\n\n    Returns ``True`` when a copy was performed and ``False`` when the copy was\n    skipped because it would be a self-copy.\n    """\n    source = Path(source_path)\n    destination = Path(destination_path)\n    if source.resolve() == destination.resolve():\n        return False\n    destination.parent.mkdir(parents=True, exist_ok=True)\n    shutil.copy2(source, destination)\n    return True\n'''


TARGETS = {
    "drafts.py": {
        "anchor": 'DRAFTS_DIR = APP_ROOT / "uploads" / "drafts"\n',
        "old": "        shutil.copy2(src, dest)\n",
        "new": "        _copy_if_different(src, dest)\n",
    },
    "profiles.py": {
        "anchor": 'ASSETS_DIR = APP_ROOT / "assets"\n',
        "old": "                shutil.copy2(src_path, dest)\n",
        "new": "                _copy_if_different(src_path, dest)\n",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def patch_file(path: Path, anchor: str, old: str, new: str, check_only: bool) -> bool:
    original = path.read_text(encoding="utf-8")
    helper_present = "def _copy_if_different(source_path, destination_path):" in original
    copy_count = original.count(old)

    if not helper_present and anchor not in original:
        raise RuntimeError(f"patch anchor not found in {path}")

    if check_only:
        if helper_present and copy_count == 0:
            print(f"{path}: already patched")
            return True
        print(f"{path}: needs patching")
        return False

    updated = original
    if not helper_present:
        updated = updated.replace(anchor, anchor + HELPER, 1)
    if copy_count:
        updated = updated.replace(old, new)

    if updated == original:
        print(f"{path}: already patched")
        return True

    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(updated, encoding="utf-8")
    print(f"{path}: patched; backup={backup}")
    return True


def run_smoke_test() -> None:
    """Verify copying to a new path and skipping a same-file copy."""
    import tempfile

    namespace = {"Path": Path, "shutil": shutil}
    exec(HELPER, namespace)
    copy_if_different = namespace["_copy_if_different"]

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "source.png"
        source.write_bytes(b"image-data")
        destination = root / "nested" / "copy.png"

        assert copy_if_different(source, destination) is True
        assert destination.read_bytes() == b"image-data"
        before = sha256(destination)
        assert copy_if_different(destination, destination) is False
        assert sha256(destination) == before

    print("Smoke test passed: same-file copies are skipped.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Repository root containing Bidding-App-main",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Check whether the patch is applied without modifying files",
    )
    args = parser.parse_args()

    source_dir = args.repo.expanduser().resolve() / "Bidding-App-main"
    if not source_dir.is_dir():
        print(f"Error: source directory does not exist: {source_dir}", file=sys.stderr)
        return 2

    all_ok = True
    for filename, config in TARGETS.items():
        path = source_dir / filename
        if not path.is_file():
            print(f"Error: target file does not exist: {path}", file=sys.stderr)
            return 2
        try:
            result = patch_file(path, check_only=args.check_only, **config)
        except Exception as exc:
            print(f"Error patching {path}: {exc}", file=sys.stderr)
            return 1
        all_ok = all_ok and result

    if args.check_only:
        return 0 if all_ok else 1

    run_smoke_test()
    for filename in TARGETS:
        path = source_dir / filename
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            print(f"Compilation failed for {path}: {exc}", file=sys.stderr)
            return 1
        print(f"Compiled successfully: {path}")

    print("SameFileError patch completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

