"""PostgreSQL-backed saved-bid draft service for the web application."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Draft


def list_drafts(db: Session, user_id: int):
    return db.scalars(select(Draft).where(Draft.user_id == user_id).order_by(Draft.updated_at.desc())).all()


def get_draft(db: Session, user_id: int, draft_id: int):
    return db.scalar(select(Draft).where(Draft.id == draft_id, Draft.user_id == user_id))


def save_draft(db: Session, user_id: int, name: str, field_data: dict, draft_id: int | None = None):
    draft = get_draft(db, user_id, draft_id) if draft_id else None
    if draft is None:
        draft = Draft(user_id=user_id, name=name or "Untitled bid", field_data=field_data or {})
        db.add(draft)
    else:
        draft.name = name or "Untitled bid"
        draft.field_data = field_data or {}
    db.commit()
    db.refresh(draft)
    return draft


def delete_draft(db: Session, user_id: int, draft_id: int) -> bool:
    draft = get_draft(db, user_id, draft_id)
    if draft is None:
        return False
    db.delete(draft)
    db.commit()
    return True
