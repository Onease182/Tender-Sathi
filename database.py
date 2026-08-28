from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from typing import Generator

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    company_name: Mapped[str] = mapped_column(String(255))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    partner_profiles: Mapped[list[PartnerProfile]] = relationship(back_populates="user", cascade="all, delete-orphan")
    drafts: Mapped[list[Draft]] = relationship(back_populates="user", cascade="all, delete-orphan")
    financial_years: Mapped[list[FinancialYear]] = relationship(back_populates="user", cascade="all, delete-orphan")
    experiences: Mapped[list[Experience]] = relationship(back_populates="user", cascade="all, delete-orphan")


class PartnerProfile(Base):
    __tablename__ = "partner_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="lead")
    partner_name: Mapped[str] = mapped_column(Text, default="")
    partner_short: Mapped[str] = mapped_column(String(100), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    partner_ceo: Mapped[str] = mapped_column(String(255), default="")
    partner_md1: Mapped[str] = mapped_column(String(255), default="")
    partner_md2: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user: Mapped[User] = relationship(back_populates="partner_profiles")


class Draft(Base):
    __tablename__ = "drafts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    field_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user: Mapped[User] = relationship(back_populates="drafts")


class FinancialYear(Base):
    __tablename__ = "financial_years"
    __table_args__ = (UniqueConstraint("user_id", "fiscal_year", name="uq_financial_year_user_year"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    fiscal_year: Mapped[str] = mapped_column(String(20))
    turnover_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user: Mapped[User] = relationship(back_populates="financial_years")
    jv_entries: Mapped[list[FinancialJVEntry]] = relationship(back_populates="financial_year", cascade="all, delete-orphan")


class FinancialJVEntry(Base):
    __tablename__ = "financial_jv_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    financial_year_id: Mapped[int] = mapped_column(ForeignKey("financial_years.id", ondelete="CASCADE"), index=True)
    jv_name: Mapped[str] = mapped_column(String(255), default="")
    jv_address: Mapped[str] = mapped_column(Text, default="")
    vat_number: Mapped[str] = mapped_column(String(100), default="")
    attributed_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    share_percentage: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=0)
    financial_year: Mapped[FinancialYear] = relationship(back_populates="jv_entries")


class Experience(Base):
    __tablename__ = "experiences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    start_month_year: Mapped[str] = mapped_column(String(30), default="")
    end_month_year: Mapped[str] = mapped_column(String(30), default="")
    contract_id: Mapped[str] = mapped_column(String(255), default="")
    contract_name: Mapped[str] = mapped_column(Text, default="")
    employer_name: Mapped[str] = mapped_column(String(255), default="")
    employer_address: Mapped[str] = mapped_column(Text, default="")
    employer_phone: Mapped[str] = mapped_column(String(100), default="")
    employer_email: Mapped[str] = mapped_column(String(320), default="")
    work_description: Mapped[str] = mapped_column(Text, default="")
    role: Mapped[str] = mapped_column(String(40), default="Contractor")
    award_date: Mapped[str] = mapped_column(String(30), default="")
    completion_date: Mapped[str] = mapped_column(String(30), default="")
    total_contract_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    participation_percentage: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=100)
    participation_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    item_quantities: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user: Mapped[User] = relationship(back_populates="experiences")


class NRBIndex(Base):
    __tablename__ = "nrb_indices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fiscal_year: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    index_value: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False) if engine else None


def get_db() -> Generator:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured. Set it to a PostgreSQL connection string.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_optional_db() -> Generator:
    """Yield a session when PostgreSQL is configured, otherwise yield None.

    Public pages use this dependency so a fresh checkout can show setup
    guidance instead of returning a database-configuration stack trace.
    """
    if SessionLocal is None:
        yield None
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    if engine is None:
        return
    Base.metadata.create_all(bind=engine)
    # create_all() does not alter existing tables. Keep this migration
    # idempotent so upgraded installations do not fail when SQLAlchemy selects
    # the newly added JSONB field before the manual migration is applied.
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE experiences ADD COLUMN IF NOT EXISTS item_quantities JSONB NOT NULL DEFAULT '[]'::jsonb"))
