# Tender Sathi

Tender Sathi is a multi-tenant FastAPI web application for Nepali construction companies preparing government tender documents. It preserves the existing placeholder-based Word bid generator while replacing the PySide6 desktop UI with server-rendered Jinja2 pages.

## What changed

The application now uses **FastAPI, Jinja2, vanilla JavaScript, PostgreSQL, SQLAlchemy, and python-docx**. Each company account has isolated partner profiles, saved bid drafts, financial history, JV turnover entries, and construction experience records. Shared NRB index reference values are maintained by an administrator.

Financial History calculates the latest-index escalation factor at generation time, selects the three highest escalated amounts from the most recent five fiscal years, and shows the resulting average in a dynamic FIN-2 Word document. Experience entries can be selected independently for EXP-1, one EXP-2(a) qualifying contract, and one or more EXP-2(b) key-activity blocks. Similarity and production-rate descriptions are intentionally entered fresh for every generation and are never stored against the reusable experience entry.

The web version deliberately does **not** include signature or stamp images, supporting-document uploads, PDF export, PDF splitting, or PDF preview. Generated Word documents are assembled in memory and streamed directly to the browser.

## Local setup

Use Python 3.11 or newer and a PostgreSQL database. SQLite is not supported by the web application because concurrent tenant access requires PostgreSQL.

```bash
git clone https://github.com/Onease182/Tender-Sathi.git
cd Tender-Sathi
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/tender_sathi'
export SECRET_KEY='replace-with-a-long-random-secret'
export APP_BASE_URL='http://localhost:8000'
uvicorn app:app --reload
```

### Windows

In Command Prompt, `.venv\\Scripts\\activate` only works after the virtual environment has been created. From the repository folder, use the included `run_windows.bat` helper, or run the commands below:

```bat
cd /d E:\\Apps\\git\\Tender-Sathi-main\\Tender-Sathi-main
py -3 -m venv .venv
.venv\\Scripts\\python.exe -m pip install --upgrade pip
.venv\\Scripts\\python.exe -m pip install -r requirements.txt
.venv\\Scripts\\python.exe -m uvicorn app:app --reload
```

If `py` is unavailable, replace it with `python`. The helper uses the virtual-environment interpreter directly, so activation is not required. Do not use a globally installed Uvicorn, because it may import a different Python environment that does not contain FastAPI.

### Local admin preview

For local software review when SMTP signup verification is not yet configured, the app includes a **development-only** admin shortcut. It is disabled by default, only accepts requests from `127.0.0.1`/`::1`, and still requires PostgreSQL:

```bat
set APP_ENV=development
set DEV_ADMIN_ACCESS=1
set DEV_ADMIN_PASSWORD=choose-a-local-password-at-least-8-characters
set DEV_ADMIN_EMAIL=admin@localhost.test
set DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/tender_sathi
run_windows.bat
```

Open `http://127.0.0.1:8000/dev-admin` and click **Continue to admin workspace**. This creates or updates the configured local admin as verified and signs it in without sending an email. Do not enable `DEV_ADMIN_ACCESS` on a public deployment, and do not use this shortcut as a production authentication mechanism.

The SQLAlchemy startup hook creates the tables for a new local database. For an explicit SQL migration, apply `migrations/001_initial.sql` with `psql`:

```bash
psql "$DATABASE_URL" -f migrations/001_initial.sql
```

## Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Yes | PostgreSQL connection string. `postgres://` and `postgresql://` URLs are normalized automatically. |
| `SECRET_KEY` | Yes in production | Session signing secret. Do not use the development fallback in production. |
| `APP_BASE_URL` | Yes in production | Public HTTPS base URL used in verification and reset links. |
| `ADMIN_EMAIL` | Recommended | Email that receives admin access when it signs up. |
| `SMTP_HOST` | Yes for email delivery | Transactional SMTP host. If absent, links are logged and email is not sent; configure this before launch. |
| `SMTP_PORT` | Usually `587` | SMTP port. |
| `SMTP_USER` / `SMTP_PASSWORD` | Depends on provider | SMTP credentials. |
| `MAIL_FROM` | Recommended | Verified sender address. |
| `COOKIE_SECURE` | `1` in production | Enables HTTPS-only session cookies. |

The implementation intentionally does not guess an email provider or credentials. Supply a standard transactional SMTP service before enabling public signup and password recovery.

## Deployment

The repository includes both `Procfile` and `render.yaml`. On Render, create the service from the blueprint and fill the `APP_BASE_URL`, `ADMIN_EMAIL`, and SMTP variables. The blueprint provisions a managed PostgreSQL database and runs:

```text
uvicorn app:app --host 0.0.0.0 --port $PORT
```

Railway can deploy from the same repository using the `Procfile`, with a PostgreSQL service attached and the same environment variables configured in the project settings. Automatic HTTPS should be enabled by the hosting provider.

## Template note

The repository contains the original master Word templates. The web generator keeps their text placeholders and partner-count behavior. For EXP-1, the distinct **Year** column is interpreted as the four-digit year extracted from the completion date, falling back to the ending month/year when needed; the reference prompt did not define this field more precisely. The reference Form FIN-2 and EXP PDFs were not present in the repository available for this implementation, so the new dynamic Word builders use a clean table-based approximation of the required fields. If the underlying reference/template files are supplied, the table styling and exact page geometry can be refined without changing the data model or route behavior.
