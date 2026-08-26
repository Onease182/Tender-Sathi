"""PostgreSQL-backed partner-profile service for the web application.

The former SQLite/image-upload implementation is intentionally replaced with
text-only, account-scoped operations.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import PartnerProfile


def list_profiles(db: Session, user_id: int):
    return db.scalars(select(PartnerProfile).where(PartnerProfile.user_id == user_id).order_by(PartnerProfile.updated_at.desc())).all()


def get_profile(db: Session, user_id: int, profile_id: int):
    return db.scalar(select(PartnerProfile).where(PartnerProfile.id == profile_id, PartnerProfile.user_id == user_id))


def save_profile(db: Session, user_id: int, values: dict, profile_id: int | None = None):
    profile = get_profile(db, user_id, profile_id) if profile_id else None
    if profile is None:
        profile = PartnerProfile(user_id=user_id, name=values.get("name", "Partner profile"))
        db.add(profile)
    for field in ("name", "role", "partner_name", "partner_short", "address", "partner_ceo", "partner_md1", "partner_md2"):
        if field in values:
            setattr(profile, field, values[field])
    db.commit()
    db.refresh(profile)
    return profile


def delete_profile(db: Session, user_id: int, profile_id: int) -> bool:
    profile = get_profile(db, user_id, profile_id)
    if profile is None:
        return False
    db.delete(profile)
    db.commit()
    return True
