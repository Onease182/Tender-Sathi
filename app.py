from __future__ import annotations

import hashlib
import logging
import os
import secrets
import smtplib
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.sessions import SessionMiddleware

from database import AuthToken, Draft, Experience, FinancialJVEntry, FinancialYear, NRBIndex, PartnerProfile, User, get_db, init_db
from doc_generator import BidDocumentGenerator, build_exp1_doc, build_exp2a_doc, build_exp2b_doc, build_fin2_doc
from format_utils import format_percentage
import profiles as profile_store
import drafts as draft_store

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("tender_sathi")
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
app = FastAPI(title="Tender Sathi", description="Multi-tenant tender document preparation")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "change-me-in-production"), max_age=60 * 60 * 24 * 14, https_only=os.getenv("COOKIE_SECURE", "0") == "1", same_site="lax")


class LoginRedirect(Exception):
    pass


@app.exception_handler(LoginRedirect)
async def login_redirect_handler(request: Request, exc: LoginRedirect):
    return redirect("/login", next=request.url.path)


def redirect(path: str, **params):
    query = "&".join(f"{quote(str(key))}={quote(str(value))}" for key, value in params.items() if value is not None)
    return RedirectResponse(path + ("?" + query if query else ""), status_code=303)


def flash(request: Request, message: str, category: str = "info"):
    request.session.setdefault("flashes", []).append({"message": message, "category": category})


def consume_flashes(request: Request):
    return request.session.pop("flashes", [])


def page(request: Request, template: str, user: User | None = None, **context):
    return TEMPLATES.TemplateResponse(template, {"request": request, "user": user, "flashes": consume_flashes(request), **context})


def user_from_request(request: Request, db: Session):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(User, int(user_id))
    if user is None:
        request.session.clear()
    return user


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = user_from_request(request, db)
    if user is None:
        raise LoginRedirect()
    if not user.is_verified:
        raise LoginRedirect()
    return user


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def token_url(request: Request, token: str, kind: str) -> str:
    base = os.getenv("APP_BASE_URL", str(request.base_url).rstrip("/"))
    return f"{base}/{kind}?token={quote(token)}"


def send_email(recipient: str, subject: str, body: str) -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        logger.warning("SMTP_HOST is not configured; email for %s was not sent. Message body:\n%s", recipient, body)
        return False
    message = EmailMessage()
    message["From"] = os.getenv("MAIL_FROM", os.getenv("SMTP_USER", "no-reply@tendersathi.local"))
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=20) as smtp:
            smtp.starttls()
            if os.getenv("SMTP_USER"):
                smtp.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
            smtp.send_message(message)
        return True
    except Exception:
        logger.exception("Could not send email to %s", recipient)
        return False


def create_token(db: Session, user_id: int, kind: str) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(AuthToken(token=token_hash(raw), user_id=user_id, kind=kind, expires_at=datetime.utcnow() + timedelta(hours=24)))
    db.commit()
    return raw


@app.on_event("startup")
def startup():
    init_db()
    if not os.getenv("DATABASE_URL"):
        logger.warning("DATABASE_URL is not configured. Configure PostgreSQL before starting the app.")


@app.get("/", response_class=HTMLResponse)
def landing(request: Request, db: Session = Depends(get_db)):
    return page(request, "landing.html", user=user_from_request(request, db))


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return page(request, "auth/signup.html", title="Create your account")


@app.post("/signup")
async def signup(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    company_name = str(form.get("company_name", "")).strip()
    password = str(form.get("password", ""))
    if not email or not company_name or len(password) < 8:
        flash(request, "Enter a company name, a valid email, and a password of at least 8 characters.", "error")
        return redirect("/signup")
    if db.scalar(select(User).where(User.email == email)):
        flash(request, "An account with that email already exists.", "error")
        return redirect("/login")
    admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    user = User(email=email, company_name=company_name, password_hash=pwd_context.hash(password), is_admin=bool(admin_email and email == admin_email))
    db.add(user)
    db.commit()
    db.refresh(user)
    raw = create_token(db, user.id, "verify")
    sent = send_email(email, "Verify your Tender Sathi account", f"Welcome to Tender Sathi. Verify your account here:\n\n{token_url(request, raw, 'verify-email')}\n\nThis link expires in 24 hours.")
    flash(request, "Your account was created. Check your email to verify it before signing in." if sent else "Your account was created. Email delivery is not configured; ask the administrator to enable SMTP before launch.", "success" if sent else "warning")
    return redirect("/login")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return page(request, "auth/login.html", title="Sign in")


@app.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not pwd_context.verify(str(form.get("password", "")), user.password_hash):
        flash(request, "Email or password was not recognized.", "error")
        return redirect("/login")
    request.session["user_id"] = user.id
    if not user.is_verified:
        flash(request, "Please verify your email before using the dashboard.", "warning")
        return redirect("/verify-needed")
    return redirect("/dashboard")


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect("/")


@app.get("/verify-needed", response_class=HTMLResponse)
def verify_needed(request: Request):
    return page(request, "auth/verify_needed.html", title="Verify your email")


@app.get("/verify-email")
def verify_email(request: Request, token: str, db: Session = Depends(get_db)):
    record = db.scalar(select(AuthToken).where(AuthToken.token == token_hash(token), AuthToken.kind == "verify"))
    if record is None or record.expires_at < datetime.utcnow():
        flash(request, "That verification link is invalid or expired.", "error")
        return redirect("/login")
    user = db.get(User, record.user_id)
    if user:
        user.is_verified = True
        db.delete(record)
        db.commit()
        flash(request, "Email verified. You can now sign in.", "success")
    return redirect("/login")


@app.post("/resend-verification")
def resend_verification(request: Request, db: Session = Depends(get_db)):
    user = user_from_request(request, db)
    if user and not user.is_verified:
        raw = create_token(db, user.id, "verify")
        send_email(user.email, "Verify your Tender Sathi account", f"Verify your account here:\n\n{token_url(request, raw, 'verify-email')}\n")
    flash(request, "If the account exists, a new verification message has been requested.", "info")
    return redirect("/login")


@app.get("/forgot-password", response_class=HTMLResponse)
def forgot_page(request: Request):
    return page(request, "auth/forgot.html", title="Reset password")


@app.post("/forgot-password")
async def forgot_password(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user:
        raw = create_token(db, user.id, "reset")
        send_email(user.email, "Reset your Tender Sathi password", f"Reset your password here:\n\n{token_url(request, raw, 'reset-password')}\n\nThis link expires in 24 hours.")
    flash(request, "If that email is registered, password reset instructions have been sent.", "info")
    return redirect("/login")


@app.get("/reset-password", response_class=HTMLResponse)
def reset_page(request: Request, token: str):
    return page(request, "auth/reset.html", title="Choose a new password", token=token)


@app.post("/reset-password")
async def reset_password(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    token = str(form.get("token", ""))
    record = db.scalar(select(AuthToken).where(AuthToken.token == token_hash(token), AuthToken.kind == "reset"))
    password = str(form.get("password", ""))
    if record is None or record.expires_at < datetime.utcnow() or len(password) < 8:
        flash(request, "The reset link is invalid, expired, or the password is too short.", "error")
        return redirect("/forgot-password")
    user = db.get(User, record.user_id)
    user.password_hash = pwd_context.hash(password)
    db.delete(record)
    db.commit()
    flash(request, "Password updated. You can now sign in.", "success")
    return redirect("/login")


def decimal(value, default=Decimal("0")):
    try:
        return Decimal(str(value or "0").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return default


def fy_sort(value: str):
    try:
        return int(str(value).split("/")[0])
    except (ValueError, IndexError):
        return 0


def financial_rows(db: Session, user_id: int):
    return db.scalars(select(FinancialYear).options(selectinload(FinancialYear.jv_entries)).where(FinancialYear.user_id == user_id).order_by(FinancialYear.updated_at.desc())).all()


def financial_calculation(rows, indices):
    latest = max(indices, key=lambda item: fy_sort(item.fiscal_year), default=None)
    if latest is None:
        return {"missing": [row.fiscal_year for row in rows], "rows": [], "selected": [], "average": Decimal("0"), "current_index": Decimal("0")}
    current_index = Decimal(latest.index_value)
    enriched = []
    for row in rows:
        index_obj = next((item for item in indices if item.fiscal_year == row.fiscal_year), None)
        index = Decimal(index_obj.index_value) if index_obj else Decimal("0")
        factor = current_index / index if index else Decimal("0")
        total = Decimal(row.turnover_amount or 0)
        present = total * factor
        enriched.append({"year": row.fiscal_year, "amount": total, "from_jv": sum((Decimal(item.attributed_amount or 0) for item in row.jv_entries), Decimal("0")), "total": total, "index": index, "factor": factor, "present": present, "object": row})
    recent = sorted(enriched, key=lambda item: fy_sort(item["year"]), reverse=True)[:5]
    selected = sorted(recent, key=lambda item: item["present"], reverse=True)[:3]
    average = sum((item["present"] for item in selected), Decimal("0")) / len(selected) if selected else Decimal("0")
    return {"missing": [item["year"] for item in recent if not item["index"]], "rows": enriched, "selected": selected, "average": average, "current_index": current_index}


def money(value):
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if not user.is_verified:
        return redirect("/verify-needed")
    profiles = profile_store.list_profiles(db, user.id)
    drafts = draft_store.list_drafts(db, user.id)
    raw_draft_id = request.query_params.get("draft_id", "")
    loaded_draft = db.scalar(select(Draft).where(Draft.user_id == user.id, Draft.id == int(raw_draft_id))) if raw_draft_id.isdigit() else None
    draft_fields = loaded_draft.field_data if loaded_draft and isinstance(loaded_draft.field_data, dict) else {}
    years = financial_rows(db, user.id)
    experiences = db.scalars(select(Experience).where(Experience.user_id == user.id).order_by(Experience.updated_at.desc())).all()
    indices = db.scalars(select(NRBIndex).order_by(NRBIndex.fiscal_year.desc())).all()
    return page(request, "dashboard.html", user=user, profiles=profiles, drafts=drafts, draft_fields=draft_fields, financial_years=years, experiences=experiences, indices=indices, calculation=financial_calculation(years, indices), active=request.query_params.get("section", "overview"))


@app.post("/profiles/save")
async def save_profile(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    form = await request.form()
    raw_id = str(form.get("profile_id", "")).strip()
    profile = db.scalar(select(PartnerProfile).where(PartnerProfile.id == int(raw_id), PartnerProfile.user_id == user.id)) if raw_id.isdigit() else None
    values = {"name": str(form.get("name", "Partner profile")).strip() or "Partner profile", "role": str(form.get("role", "lead"))}
    values.update({field: str(form.get(field, "")).strip() for field in ("partner_name", "partner_short", "address", "partner_ceo", "partner_md1", "partner_md2")})
    profile_store.save_profile(db, user.id, values, int(raw_id) if raw_id.isdigit() else None)
    flash(request, "Partner profile saved.", "success")
    return redirect("/dashboard", section="profiles")


@app.post("/profiles/delete/{profile_id}")
def delete_profile(profile_id: int, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if profile_store.delete_profile(db, user.id, profile_id):
        flash(request, "Partner profile deleted.", "success")
    return redirect("/dashboard", section="profiles")


@app.post("/drafts/save")
async def save_draft(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    form = await request.form()
    raw_id = str(form.get("draft_id", "")).strip()
    draft = db.scalar(select(Draft).where(Draft.id == int(raw_id), Draft.user_id == user.id)) if raw_id.isdigit() else None
    name = str(form.get("draft_name", "Untitled bid")).strip() or "Untitled bid"
    field_data = {key: str(value) for key, value in form.multi_items() if key not in {"draft_name", "draft_id"}}
    draft_store.save_draft(db, user.id, name, field_data, int(raw_id) if raw_id.isdigit() else None)
    flash(request, "Bid draft saved.", "success")
    return redirect("/dashboard", section="generate")


@app.post("/drafts/delete/{draft_id}")
def delete_draft(draft_id: int, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if draft_store.delete_draft(db, user.id, draft_id):
        flash(request, "Draft deleted.", "success")
    return redirect("/dashboard", section="generate")


@app.post("/financial/save")
async def save_financial(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    form = await request.form()
    raw_id = str(form.get("year_id", "")).strip()
    row = db.scalar(select(FinancialYear).where(FinancialYear.user_id == user.id, FinancialYear.id == int(raw_id))) if raw_id.isdigit() else None
    if row is None:
        row = FinancialYear(user_id=user.id, fiscal_year=str(form.get("fiscal_year", "")).strip(), turnover_amount=decimal(form.get("turnover_amount")))
        db.add(row)
        db.flush()
    row.fiscal_year = str(form.get("fiscal_year", "")).strip()
    row.turnover_amount = decimal(form.get("turnover_amount"))
    row.jv_entries.clear()
    names, addresses, vats, amounts, shares = (form.getlist(name) for name in ("jv_name", "jv_address", "vat_number", "attributed_amount", "share_percentage"))
    for i, name in enumerate(names):
        values = (name, addresses[i] if i < len(addresses) else "", vats[i] if i < len(vats) else "")
        if any(str(value).strip() for value in values) or decimal(amounts[i] if i < len(amounts) else 0):
            row.jv_entries.append(FinancialJVEntry(jv_name=str(name).strip(), jv_address=str(values[1]).strip(), vat_number=str(values[2]).strip(), attributed_amount=decimal(amounts[i] if i < len(amounts) else 0), share_percentage=decimal(shares[i] if i < len(shares) else 0)))
    db.commit()
    flash(request, "Financial year saved.", "success")
    return redirect("/dashboard", section="financial")


@app.post("/financial/delete/{year_id}")
def delete_financial(year_id: int, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    row = db.scalar(select(FinancialYear).where(FinancialYear.id == year_id, FinancialYear.user_id == user.id))
    if row:
        db.delete(row)
        db.commit()
        flash(request, "Financial year deleted.", "success")
    return redirect("/dashboard", section="financial")


@app.post("/experience/save")
async def save_experience(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    form = await request.form()
    raw_id = str(form.get("experience_id", "")).strip()
    entry = db.scalar(select(Experience).where(Experience.id == int(raw_id), Experience.user_id == user.id)) if raw_id.isdigit() else None
    if entry is None:
        entry = Experience(user_id=user.id)
        db.add(entry)
    text_fields = ("start_month_year", "end_month_year", "contract_id", "contract_name", "employer_name", "employer_address", "employer_phone", "employer_email", "work_description", "role", "award_date", "completion_date")
    for field in text_fields:
        setattr(entry, field, str(form.get(field, "")).strip())
    entry.total_contract_amount = decimal(form.get("total_contract_amount"))
    entry.participation_percentage = decimal(form.get("participation_percentage"), Decimal("100"))
    entry.participation_amount = decimal(form.get("participation_amount")) or entry.total_contract_amount * entry.participation_percentage / 100
    db.commit()
    flash(request, "Experience entry saved.", "success")
    return redirect("/dashboard", section="experience")


@app.post("/experience/delete/{experience_id}")
def delete_experience(experience_id: int, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    entry = db.scalar(select(Experience).where(Experience.id == experience_id, Experience.user_id == user.id))
    if entry:
        db.delete(entry)
        db.commit()
        flash(request, "Experience entry deleted.", "success")
    return redirect("/dashboard", section="experience")


@app.get("/admin/nrb", response_class=HTMLResponse)
def admin_nrb(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if not user.is_admin:
        return redirect("/dashboard")
    indices = db.scalars(select(NRBIndex).order_by(NRBIndex.fiscal_year.desc())).all()
    return page(request, "admin_nrb.html", user=user, indices=indices, active="admin")


@app.post("/admin/nrb")
async def save_nrb(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if not user.is_admin:
        return redirect("/dashboard")
    form = await request.form()
    fiscal_year = str(form.get("fiscal_year", "")).strip()
    row = db.scalar(select(NRBIndex).where(NRBIndex.fiscal_year == fiscal_year))
    if row is None:
        db.add(NRBIndex(fiscal_year=fiscal_year, index_value=decimal(form.get("index_value"))))
    else:
        row.index_value = decimal(form.get("index_value"))
    db.commit()
    flash(request, "NRB index saved.", "success")
    return redirect("/admin/nrb")


@app.post("/admin/nrb/delete/{index_id}")
def delete_nrb(index_id: int, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.is_admin:
        row = db.get(NRBIndex, index_id)
        if row:
            db.delete(row)
            db.commit()
    return redirect("/admin/nrb")


def bid_data(form):
    keys = ("BID_TYPE", "JV_NAME", "JV_ADDRESS", "PROJECT_NAME", "IFB_NUMBER", "BID_DATE", "EMPLOYER_NAME", "EMPLOYER_ADDRESS", "BID_VALIDITY_PERIOD", "AUTHORIZED_PERSON_NAME", "AUTHORIZED_CAPACITY", "LEAD_PARTNER_NAME", "LEAD_PARTNER_SHORT", "LEAD_ADDRESS", "LEAD_PARTNER_CEO", "LEAD_PARTNER_MD1", "LEAD_PARTNER_MD2", "FIRST_PARTNER_NAME", "FIRST_PARTNER_SHORT", "FIRST_ADDRESS", "FIRST_PARTNER_CEO", "FIRST_PARTNER_MD1", "FIRST_PARTNER_MD2", "SECOND_PARTNER_NAME", "SECOND_PARTNER_SHORT", "SECOND_ADDRESS", "SECOND_PARTNER_CEO", "SECOND_PARTNER_MD1", "SECOND_PARTNER_MD2", "L_PER", "F_PER", "S_PER")
    data = {key: str(form.get(key, "")).strip() for key in keys}
    is_single = data["BID_TYPE"] == "Single Bidder"
    if is_single:
        data["JV_NAME"], data["JV_ADDRESS"] = data["LEAD_PARTNER_NAME"], data["LEAD_ADDRESS"]
        data["L_PER"], data["F_PER"], data["S_PER"] = "100%", "", ""
    for key in ("L_PER", "F_PER", "S_PER"):
        if data[key]:
            data[key] = format_percentage(data[key].replace("%", "")) + "%"
    data["AND_CONNECTOR"] = "" if is_single else "And"
    data["HAS_THIRD_PARTNER"] = "True" if data["SECOND_PARTNER_NAME"] else "False"
    data["AUTHORIZED_CAPACITY"] = data["AUTHORIZED_CAPACITY"] or "Authorised person of JV"
    return data


@app.post("/generate/bid")
async def generate_bid(request: Request, user: User = Depends(require_user)):
    form = await request.form()
    data = bid_data(form)
    generator = BidDocumentGenerator(BASE_DIR, create_dirs=False)
    try:
        generator.determine_partner_count(data)
        total = sum(decimal(data.get(key, "").replace("%", "")) for key in ("L_PER", "F_PER", "S_PER"))
        if abs(total - 100) > Decimal("0.01"):
            raise ValueError(f"Partner percentage shares must add up to 100%. Current total: {total:.2f}%")
        content = generator.generate_bytes(data)
    except Exception as exc:
        flash(request, f"Bid generation failed: {exc}", "error")
        return redirect("/dashboard", section="generate")
    filename = "".join(char if char.isalnum() or char in "-_" else "_" for char in (data.get("JV_NAME") or "bid"))[:50].strip("_") or "tender_sathi_bid"
    return StreamingResponse(iter([content]), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": f'attachment; filename="{filename}.docx"'})


@app.post("/generate/fin2")
async def generate_fin2(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    form = await request.form()
    selected_ids = {int(value) for value in form.getlist("financial_year_ids") if str(value).isdigit()}
    rows = [row for row in financial_rows(db, user.id) if row.id in selected_ids] or financial_rows(db, user.id)
    indices = db.scalars(select(NRBIndex).order_by(NRBIndex.fiscal_year.desc())).all()
    calculation = financial_calculation(rows, indices)
    if calculation["missing"]:
        flash(request, "Add NRB index values for every recent financial year before generating FIN-2.", "error")
        return redirect("/dashboard", section="financial")
    selected_rows = [(item["year"], money(item["present"])) for item in calculation["selected"]]
    content = build_fin2_doc(user.company_name, rows, {item.fiscal_year: item.index_value for item in indices}, calculation["current_index"], selected_rows, calculation["average"])
    return StreamingResponse(iter([content]), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": 'attachment; filename="FIN-2_Average_Annual_Turnover.docx"'})


@app.post("/generate/exp1")
async def generate_exp1(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    form = await request.form()
    ids = [int(value) for value in form.getlist("experience_ids") if str(value).isdigit()]
    entries = db.scalars(select(Experience).where(Experience.user_id == user.id, Experience.id.in_(ids))).all() if ids else []
    content = build_exp1_doc(user.company_name, entries)
    return StreamingResponse(iter([content]), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": 'attachment; filename="EXP-1_General_Construction_Experience.docx"'})


@app.post("/generate/exp2a")
async def generate_exp2a(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    form = await request.form()
    value = str(form.get("experience_id", ""))
    entry = db.scalar(select(Experience).where(Experience.user_id == user.id, Experience.id == int(value))) if value.isdigit() else None
    if entry is None:
        flash(request, "Select one experience entry for EXP-2(a).", "error")
        return redirect("/dashboard", section="experience")
    content = build_exp2a_doc(user.company_name, entry, str(form.get("similarity_description", "")).strip())
    return StreamingResponse(iter([content]), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": 'attachment; filename="EXP-2a_Specific_Experience.docx"'})


@app.post("/generate/exp2b")
async def generate_exp2b(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    form = await request.form()
    ids = [int(value) for value in form.getlist("experience_ids") if str(value).isdigit()]
    entries = db.scalars(select(Experience).where(Experience.user_id == user.id, Experience.id.in_(ids))).all() if ids else []
    by_id = {entry.id: entry for entry in entries}
    selected = [(by_id[item_id], str(form.get(f"production_description_{item_id}", "")).strip()) for item_id in ids if item_id in by_id]
    content = build_exp2b_doc(user.company_name, selected)
    return StreamingResponse(iter([content]), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": 'attachment; filename="EXP-2b_Key_Activities.docx"'})
