"""
profiles.py

Reusable Partner Profile storage for the JV Bid Document Generator.
"""

import sqlite3
import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
DB_PATH = APP_ROOT / "db" / "profiles.db"
PROFILES_DIR = APP_ROOT / "uploads" / "profiles"
ASSETS_DIR = APP_ROOT / "assets"


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

# Which image keys belong to which partner role.
ROLE_IMAGE_KEYS = {
    "lead": ["LEAD_CEO_SIG", "LEAD_STAMP", "LEAD_PARTNER_MD1", "LEAD_PARTNER_MD2"],
    "first": ["FIRST_CEO_SIG", "FIRST_STAMP", "FIRST_PARTNER_MD1", "FIRST_PARTNER_MD2"],
    "second": ["SECOND_CEO_SIG", "SECOND_STAMP", "SECOND_PARTNER_MD1", "SECOND_PARTNER_MD2"],
}

# Maps the generic data dict keys used by this module to the actual
# placeholder field keys used in app.py's self.entries dict.
ROLE_FIELD_KEYS = {
    "lead": {
        "partner_name": "LEAD_PARTNER_NAME",
        "partner_short": "LEAD_PARTNER_SHORT",
        "address": "LEAD_ADDRESS",
        "partner_ceo": "LEAD_PARTNER_CEO",
        "partner_md1": "LEAD_PARTNER_MD1",
        "partner_md2": "LEAD_PARTNER_MD2",
    },
    "first": {
        "partner_name": "FIRST_PARTNER_NAME",
        "partner_short": "FIRST_PARTNER_SHORT",
        "address": "FIRST_ADDRESS",
        "partner_ceo": "FIRST_PARTNER_CEO",
        "partner_md1": "FIRST_PARTNER_MD1",
        "partner_md2": "FIRST_PARTNER_MD2",
    },
    "second": {
        "partner_name": "SECOND_PARTNER_NAME",
        "partner_short": "SECOND_PARTNER_SHORT",
        "address": "SECOND_ADDRESS",
        "partner_ceo": "SECOND_PARTNER_CEO",
        "partner_md1": "SECOND_PARTNER_MD1",
        "partner_md2": "SECOND_PARTNER_MD2",
    },
}

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
        CREATE TABLE IF NOT EXISTS partner_profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            partner_name TEXT DEFAULT '',
            partner_short TEXT DEFAULT '',
            address TEXT DEFAULT '',
            partner_ceo TEXT DEFAULT '',
            partner_md1 TEXT DEFAULT '',
            partner_md2 TEXT DEFAULT '',
            images TEXT DEFAULT '{}',
            attachments TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()
    conn.close()

    conn = _connection()
    cols = [row[1] for row in conn.execute("PRAGMA table_info(partner_profiles)").fetchall()]
    if "attachments" not in cols:
        conn.execute("ALTER TABLE partner_profiles ADD COLUMN attachments TEXT DEFAULT '{}'")
        conn.commit()
    conn.close()

ATTACHMENT_CATEGORIES = ["experience", "registration", "audits", "bank_guarantee", "line_of_credit"]

CATEGORY_LABELS = {
    "experience": "Experience Letters",
    "registration": "Registration & Legal Documents",
    "audits": "Audit Documents & Financial Statements",
    "bank_guarantee": "Bank Guarantee Documents",
    "line_of_credit": "Line of Credit",
}

PARTNER_ROLES = ["lead", "first", "second"]

PARTNER_ROLE_LABELS = {"lead": "Lead Partner", "first": "First Partner", "second": "Second Partner"}

def _default_attachments_json():
    return {cat: [] for cat in ATTACHMENT_CATEGORIES}

def list_profiles(role=None):
    """Return all profiles, ignoring role. Profiles are role-agnostic."""
    init_db()
    conn = _connection()
    # Return all profiles regardless of role
    rows = conn.execute(
        "SELECT * FROM partner_profiles ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_profile(profile_id):
    init_db()
    conn = _connection()
    row = conn.execute(
        "SELECT * FROM partner_profiles WHERE id=?", (profile_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def save_profile(name, role, data, image_paths=None, documents=None):
    init_db()
    conn = _connection()
    now = datetime.now().isoformat()
    profile_id = str(uuid.uuid4())[:12]

    conn.execute(
        """INSERT INTO partner_profiles
            (id, name, role, partner_name, partner_short, address,
             partner_ceo, partner_md1, partner_md2, images, attachments,
             created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            profile_id, name, role,
            data.get("partner_name", ""), data.get("partner_short", ""),
            data.get("address", ""), data.get("partner_ceo", ""),
            data.get("partner_md1", ""), data.get("partner_md2", ""),
            "{}", json.dumps(_default_attachments_json()), now, now,
        ),
    )
    conn.commit()
    conn.close()

    saved_images = {}
    if image_paths:
        relevant_keys = ROLE_IMAGE_KEYS.get(role, [])
        profile_dir = PROFILES_DIR / profile_id
        profile_dir.mkdir(parents=True, exist_ok=True)
        for img_key in relevant_keys:
            src_path = image_paths.get(img_key)
            if src_path and os.path.exists(src_path):
                ext = Path(src_path).suffix.lower()
                if ext not in (".png", ".jpg", ".jpeg"):
                    ext = ".png"
                # FIX BUG 5: Use profile-scoped filename to prevent cross-profile collision
                dest = profile_dir / f"profile_{profile_id}_{img_key}{ext}"
                _copy_if_different(src_path, dest)
                saved_images[img_key] = f"profile_{profile_id}_{img_key}{ext}"

    if saved_images:
        conn = _connection()
        conn.execute(
            "UPDATE partner_profiles SET images=?, updated_at=? WHERE id=?",
            (json.dumps(saved_images), datetime.now().isoformat(), profile_id),
        )
        conn.commit()
        conn.close()

    if documents:
        for category, filepaths in documents.items():
            for fp in filepaths:
                add_profile_attachment(profile_id, category, fp)

    return profile_id

# FIX BUG 4: Added source_role parameter to know which keys to filter
def update_profile(profile_id, data, image_paths=None, documents_to_add=None, source_role=None):
    init_db()
    conn = _connection()
    now = datetime.now().isoformat()

    conn.execute(
        """UPDATE partner_profiles
            SET partner_name=?, partner_short=?, address=?,
                partner_ceo=?, partner_md1=?, partner_md2=?, updated_at=?
            WHERE id=?""",
        (
            data.get("partner_name", ""), data.get("partner_short", ""),
            data.get("address", ""), data.get("partner_ceo", ""),
            data.get("partner_md1", ""), data.get("partner_md2", ""),
            now, profile_id
        )
    )
    conn.commit()
    conn.close()

    if image_paths is not None:
        profile = get_profile(profile_id)
        if profile:
            try:
                saved_images = json.loads(profile.get("images", "{}"))
            except (json.JSONDecodeError, TypeError):
                saved_images = {}

            # FIX BUG 4: Use source_role if provided, else fall back to profile["role"]
            effective_role = source_role if source_role else profile["role"]
            relevant_keys = ROLE_IMAGE_KEYS.get(effective_role, [])
            profile_dir = PROFILES_DIR / profile_id
            profile_dir.mkdir(parents=True, exist_ok=True)

            for img_key in relevant_keys:
                src_path = image_paths.get(img_key)
                if src_path and os.path.exists(src_path):
                    ext = Path(src_path).suffix.lower()
                    if ext not in (".png", ".jpg", ".jpeg"):
                        ext = ".png"
                    # FIX BUG 5: Use profile-scoped filename
                    dest = profile_dir / f"profile_{profile_id}_{img_key}{ext}"
                    _copy_if_different(src_path, dest)
                    saved_images[img_key] = f"profile_{profile_id}_{img_key}{ext}"

            conn = _connection()
            conn.execute(
                "UPDATE partner_profiles SET images=?, updated_at=? WHERE id=?",
                (json.dumps(saved_images), now, profile_id)
            )
            conn.commit()
            conn.close()

    if documents_to_add:
        for category, filepaths in documents_to_add.items():
            for fp in filepaths:
                add_profile_attachment(profile_id, category, fp)

def delete_profile(profile_id):
    init_db()
    conn = _connection()
    conn.execute("DELETE FROM partner_profiles WHERE id=?", (profile_id,))
    conn.commit()
    conn.close()
    profile_dir = PROFILES_DIR / profile_id
    if profile_dir.exists():
        shutil.rmtree(profile_dir, ignore_errors=True)

def get_profile_image_path(profile_id, img_key):
    profile = get_profile(profile_id)
    if not profile:
        return None
    try:
        image_map = json.loads(profile.get("images", "{}"))
    except (json.JSONDecodeError, TypeError):
        return None
    filename = image_map.get(img_key)
    if not filename:
        return None
    path = PROFILES_DIR / profile_id / filename
    return str(path) if path.exists() else None

def load_profile_images_to_assets(profile_id):
    """Return {img_key: path} pointing directly at this profile's stored
    images under PROFILES_DIR/<profile_id>/. No copy into assets/ needed —
    these filenames are already profile-scoped (profile_<id>_<key>.ext), so
    there's no collision risk, and doc_generator just reads whatever path
    it's given. Name kept for compatibility with existing callers.
    """
    profile = get_profile(profile_id)
    if not profile:
        return {}
    try:
        image_map = json.loads(profile.get("images", "{}"))
    except (json.JSONDecodeError, TypeError):
        image_map = {}

    paths = {}
    for img_key, filename in image_map.items():
        src = PROFILES_DIR / profile_id / filename
        if src.exists():
            paths[img_key] = str(src)
    return paths

def get_profile_attachments(profile_id):
    profile = get_profile(profile_id)
    if not profile:
        return _default_attachments_json()
    try:
        raw = profile.get("attachments", "{}") or "{}"
        data = json.loads(raw)
        for cat in ATTACHMENT_CATEGORIES:
            if cat not in data:
                data[cat] = []
        return data
    except (json.JSONDecodeError, TypeError):
        return _default_attachments_json()

def set_profile_attachments(profile_id, attachments_dict):
    init_db()
    conn = _connection()
    conn.execute(
        "UPDATE partner_profiles SET attachments=?, updated_at=? WHERE id=?",
        (json.dumps(attachments_dict), datetime.now().isoformat(), profile_id),
    )
    conn.commit()
    conn.close()

def add_profile_attachment(profile_id, category, source_path, description=""):
    if category not in ATTACHMENT_CATEGORIES or not source_path or not os.path.isfile(source_path):
        return None
    attachments = get_profile_attachments(profile_id)
    att_id = str(uuid.uuid4())[:8]
    src = Path(source_path)
    ext = src.suffix.lower()
    if ext not in (".pdf", ".png", ".jpg", ".jpeg"):
        ext = ".pdf"
    stored_name = f"{att_id}{ext}"
    dest_dir = PROFILES_DIR / profile_id / "attachments" / category
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / stored_name
    shutil.copy2(source_path, dest_path)
    entry = {
        "id": att_id,
        "original_filename": src.name,
        "stored_filename": stored_name,
        "file_size": dest_path.stat().st_size,
        "description": description,
    }
    attachments[category].append(entry)
    set_profile_attachments(profile_id, attachments)
    return entry

def remove_profile_attachment(profile_id, category, att_id):
    attachments = get_profile_attachments(profile_id)
    if category not in attachments:
        return False
    new_list = []
    removed = None
    for entry in attachments[category]:
        if entry.get("id") == att_id:
            removed = entry
            fpath = PROFILES_DIR / profile_id / "attachments" / category / entry.get("stored_filename", "")
            if fpath.exists():
                fpath.unlink()
        else:
            new_list.append(entry)
    if removed is None:
        return False
    attachments[category] = new_list
    set_profile_attachments(profile_id, attachments)
    return True

def get_profile_attachment_path(profile_id, category, att_id):
    attachments = get_profile_attachments(profile_id)
    for entry in attachments.get(category, []):
        if entry.get("id") == att_id:
            fpath = PROFILES_DIR / profile_id / "attachments" / category / entry.get("stored_filename", "")
            return str(fpath) if fpath.exists() else None
    return None

def copy_profile_attachments_to_bid(profile_id, role, bid_attachments_dir):
    attachments = get_profile_attachments(profile_id)
    result = {cat: [] for cat in ATTACHMENT_CATEGORIES}
    role_dir = Path(bid_attachments_dir) / role
    for category, entries in attachments.items():
        cat_dir = role_dir / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        for entry in entries:
            src = PROFILES_DIR / profile_id / "attachments" / category / entry.get("stored_filename", "")
            if src.exists():
                dest = cat_dir / entry["stored_filename"]
                shutil.copy2(src, dest)
                copied_entry = dict(entry)
                copied_entry["bid_path"] = str(dest)
                result[category].append(copied_entry)
    return result

# ------------------------------------------------------------------
# Search helpers
# ------------------------------------------------------------------

def search_profiles(role, query=""):
    """Return profiles, optionally filtered by name."""
    all_profiles = list_profiles()
    if not query or not query.strip():
        return all_profiles
    q = query.strip().lower()
    return [p for p in all_profiles if q in p["name"].lower()]

def find_profile_by_partner_name(role, partner_name):
    """Find a profile by its specific partner_name field."""
    if not partner_name:
        return None
    init_db()
    conn = _connection()
    row = conn.execute(
        "SELECT * FROM partner_profiles WHERE partner_name=? ORDER BY updated_at DESC LIMIT 1",
        (partner_name,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None