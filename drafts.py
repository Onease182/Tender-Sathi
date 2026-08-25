# -*- coding: utf-8 -*-
"""
drafts.py

SQLite-backed "bid draft" storage for the JV Bid Document Generator.

A draft is a snapshot of everything the sidebar's project switcher needs
in order to leave a bid and come back to it later:

- every form field value (what generate_doc() already builds from
  self.entries — same shape, just persisted)
- signature/stamp image assignments (self.image_mapping)
- which saved partner profile (if any) is linked to each role, so the
  Supporting Documents panel can reattach to that profile's DB-backed
  attachments on load
- ad-hoc supporting-document file paths not yet tied to a saved profile
  (self.session_docs)
- the uploaded employer PDF path, if any

Storage conventions (sqlite3, Path-based DB location, uuid ids, ISO
timestamps, WAL mode) mirror profiles.py so the two modules read the
same either side of a diff.
"""

import sqlite3
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
DB_PATH = APP_ROOT / "db" / "drafts.db"
DRAFTS_DIR = APP_ROOT / "uploads" / "drafts"


def _copy_if_different(source_path, destination_path):
    """Copy a file unless source and destination resolve to the same path.

    Returns ``True`` when a copy was performed and ``False`` when the copy was
    skipped because it would be a self-copy.
    """
    source = Path(source_path)
    destination = Path(destination_path)
    if source.resolve() == destination.resolve():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True

def _connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = _connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS drafts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            field_data TEXT NOT NULL DEFAULT '{}',
            image_mapping TEXT NOT NULL DEFAULT '{}',
            linked_profiles TEXT NOT NULL DEFAULT '{}',
            session_docs TEXT NOT NULL DEFAULT '{}',
            employer_pdf_path TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()
    conn.close()

# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------

def list_drafts():
    """Return [{id, name, updated_at}, ...], most-recently-updated first."""
    init_db()
    conn = _connection()
    rows = conn.execute(
        "SELECT id, name, updated_at FROM drafts ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_draft(draft_id):
    init_db()
    conn = _connection()
    row = conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def save_draft(name, field_data, image_mapping=None, linked_profiles=None,
               session_docs=None, employer_pdf_path=None, draft_id=None):
    """Create a new draft, or overwrite an existing one when draft_id is
    given (an "update" rather than a "save as"). Returns the draft id.
    """
    init_db()
    now = datetime.now().isoformat()
    is_new = draft_id is None
    if is_new:
        draft_id = str(uuid.uuid4())[:12]

    stored_images = _store_draft_images(draft_id, image_mapping or {})

    conn = _connection()
    if is_new:
        conn.execute(
            """INSERT INTO drafts
                (id, name, field_data, image_mapping, linked_profiles,
                 session_docs, employer_pdf_path, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                draft_id, name, json.dumps(field_data or {}),
                json.dumps(stored_images), json.dumps(linked_profiles or {}),
                json.dumps(session_docs or {}), employer_pdf_path or "",
                now, now,
            ),
        )
    else:
        conn.execute(
            """UPDATE drafts
                SET name=?, field_data=?, image_mapping=?, linked_profiles=?,
                    session_docs=?, employer_pdf_path=?, updated_at=?
                WHERE id=?""",
            (
                name, json.dumps(field_data or {}), json.dumps(stored_images),
                json.dumps(linked_profiles or {}), json.dumps(session_docs or {}),
                employer_pdf_path or "", now, draft_id,
            ),
        )
    conn.commit()
    conn.close()
    return draft_id

def delete_draft(draft_id):
    init_db()
    conn = _connection()
    conn.execute("DELETE FROM drafts WHERE id=?", (draft_id,))
    conn.commit()
    conn.close()
    draft_dir = DRAFTS_DIR / draft_id
    if draft_dir.exists():
        shutil.rmtree(draft_dir, ignore_errors=True)

# ------------------------------------------------------------------
# JSON column accessors (defensive against hand-edited/corrupt rows,
# same pattern as profiles.get_profile_attachments)
# ------------------------------------------------------------------

def get_field_data(draft):
    try:
        return json.loads(draft.get("field_data") or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}

def get_linked_profiles(draft):
    try:
        return json.loads(draft.get("linked_profiles") or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}

def get_session_docs(draft):
    try:
        return json.loads(draft.get("session_docs") or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}

# ------------------------------------------------------------------
# Image storage
# ------------------------------------------------------------------
#
# app.py keeps image_mapping[img_key] pointing at whatever path the image
# actually lives at. For a fresh, not-yet-saved upload that's a scratch
# "assets/<img_key><ext>" file; once a draft is saved, _store_draft_images
# freezes a private, draft-scoped copy under DRAFTS_DIR/<draft_id>/ so later
# edits to the live assets/ file (e.g. re-uploading a different LEAD_CEO_SIG
# for a new bid) can't silently repoint an already-saved draft's mapping.
# Loading a draft back just points image_mapping straight at that frozen
# copy — no need to copy it into assets/ again, since doc_generator only
# ever reads the path it's given.

# FIX BUG 3 & 5: Use draft-scoped filenames to prevent cross-draft contamination

def _store_draft_images(draft_id, image_mapping):
    if not image_mapping:
        return {}
    draft_dir = DRAFTS_DIR / draft_id
    draft_dir.mkdir(parents=True, exist_ok=True)
    stored = {}
    for img_key, src_path in image_mapping.items():
        src = Path(src_path)
        if not src.exists():
            continue
        ext = src.suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg"):
            ext = ".png"
        # FIX BUG 3 & 5: Prefix with draft_id to prevent filename collisions
        dest = draft_dir / f"draft_{draft_id}_{img_key}{ext}"
        _copy_if_different(src, dest)
        stored[img_key] = f"draft_{draft_id}_{img_key}{ext}"
    return stored

def load_draft_images_to_assets(draft_id):
    """Return {img_key: path} pointing directly at this draft's frozen
    images under DRAFTS_DIR/<draft_id>/. No copy into assets/ needed —
    these filenames are already draft-scoped, so there's no collision
    risk, and doc_generator just reads whatever path it's given. Name
    kept for compatibility with existing callers.
    """
    draft = get_draft(draft_id)
    if not draft:
        return {}
    try:
        image_map = json.loads(draft.get("image_mapping") or "{}")
    except (json.JSONDecodeError, TypeError):
        image_map = {}

    draft_dir = DRAFTS_DIR / draft_id

    result = {}
    for img_key, filename in image_map.items():
        src = draft_dir / filename
        if src.exists():
            result[img_key] = str(src)
    return result