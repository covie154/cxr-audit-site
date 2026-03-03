# 🫁 PRIMER-LLM — Django Deployment

## Project Overview

Medical imaging AI audit system that compares Lunit INSIGHT CXR predictions against radiologist ground truth reports. Uses LLMs to grade radiology reports on an R1–R5 severity scale, then generates accuracy metrics, false negative/positive identification, time analysis, and statistical reports.

This repo contains the production Django + FastAPI deployment, orchestrated via Docker Compose behind an Nginx HTTPS reverse proxy.

## Architecture

Three-tier Docker Compose stack:

```
Nginx (HTTPS :443) → Django/Gunicorn (:8000) → FastAPI/Uvicorn (:1221) → Ollama LLM (:11434)
```

| Service | Directory | Technology | Role |
|---------|-----------|------------|------|
| **nginx** | `nginx/` | Nginx Alpine | HTTPS termination, HTTP→HTTPS redirect, proxy to Django |
| **django** | `django-app/` | Django 6 + Gunicorn + WhiteNoise | Web UI (upload, viewer, reports, manual GT) |
| **api** | `cxr-audit-api/` | FastAPI + Uvicorn | File processing pipeline, LLM grading engine |
| **ollama** | External host | Ollama (OpenAI-compatible) | LLM inference (e.g. `qwen3:32b-q4_K_M`) |

## Directory Structure

```
django/
├── docker-compose.yml          # Orchestrates nginx + django + api
├── .env.example                # Environment variable template
├── .env                        # Local environment config (git-ignored)
├── README.md                   # User-facing documentation
├── TODO.md                     # Pending tasks
├── nginx/
│   ├── nginx.conf              # Reverse proxy + TLS config
│   └── generate-certs.sh       # Self-signed cert generator for dev
├── django-app/                 # Django web application
│   ├── Dockerfile
│   ├── entrypoint.sh           # Migrations, collectstatic, superuser, then gunicorn
│   ├── requirements.txt        # Python deps (Django, pandas, scikit-learn, openai, etc.)
│   ├── manage.py
│   ├── lunit_audit/            # Django project settings
│   │   ├── settings.py         # Config (all from env vars), SQLite DB, WhiteNoise
│   │   ├── urls.py             # Root URL routing
│   │   └── wsgi.py
│   ├── upload/                 # App: file upload + processing
│   │   ├── models.py           # CXRStudy (primary model), ProcessingTask
│   │   ├── views.py            # Upload UI, proxy to FastAPI, background polling
│   │   ├── urls.py             # /upload/*, /upload/api/*
│   │   ├── admin.py
│   │   ├── context_processors.py
│   │   └── utils/              # open_protected_xlsx, process_carpl helpers
│   ├── viewer/                 # App: database browser (admin-only)
│   │   ├── views.py            # Paginated table, inline edit, CSV export, bulk delete
│   │   └── urls.py             # /view/*
│   ├── report/                 # App: analytics dashboard
│   │   ├── views.py            # Metrics, confusion matrix, ROC-AUC, trends, email, PDF
│   │   └── urls.py             # /report/*
│   ├── gt/                     # App: manual ground truth audit
│   │   ├── views.py            # Stratified sampling, CSV download/upload of manual labels
│   │   └── urls.py             # /gt/*
│   ├── templates/              # Base template + registration (login)
│   └── static/                 # Global CSS, favicon
└── cxr-audit-api/              # FastAPI analysis backend
    ├── Dockerfile
    ├── api_requirements.txt    # FastAPI, pandas, scikit-learn, openai, json-repair, etc.
    ├── combined_server.py      # FastAPI app (--api-only mode in Docker)
    ├── class_process_carpl.py  # ProcessCarpl: data merge, binarisation, LLM orchestration
    ├── open_protected_xlsx.py  # Password-protected Excel reader
    ├── cxr_audit/              # LLM grading engine
    │   ├── lib_audit_cxr_v2.py # CXRClassifier: semi-algo, LLM, hybrid grading
    │   ├── grade_batch_async.py# BatchCXRProcessor: concurrent LLM grading
    │   ├── prompts.py          # All LLM prompts (R1–R5 rubric)
    │   ├── supplement.py       # Supplemental findings extraction
    │   ├── helpers.py          # Utility functions
    │   └── llm_iter.py         # Iterative LLM refinement
    ├── padchest_op.json        # Medical findings dictionary
    ├── padchest_tubes_lines.json
    └── diagnoses.json          # Diagnosis mappings
```

## Django Apps

### `upload` — File Upload & Processing (`/upload/`)
- Main entry point; all users land here
- Accepts CARPL CSV + GE/RIS Excel files
- Proxies file uploads to the FastAPI backend via `analyze-auto-sort`
- Background daemon thread polls FastAPI for task status and auto-saves results to SQLite
- Login required for all views

### `viewer` — Database Browser (`/view/`)
- **Admin-only** — paginated, sortable, searchable table of `CXRStudy` records
- Inline editing, detail modal, bulk delete, CSV export
- Filters by workplace, GT, Lunit binary, LLM grade, date range

### `report` — Analytics Dashboard (`/report/`)
- Generates reports from DB records filtered by date range
- Metrics: accuracy, sensitivity, specificity, PPV, NPV, ROC-AUC
- Confusion matrix, false negatives/positives lists
- Weekly trend charts with 95% CI
- Time analysis (median, P25/P75 turnaround times)
- Email report and PDF download

### `gt` — Manual Ground Truth (`/gt/`)
- Download stratified random sample of CXR reports for manual cross-checking
- 50/50 split between priority workplaces (TPY, HOU, KHA, AMK) and others
- Upload labelled CSV back to fill `gt_manual` field
- Default sample: 2% (~150 per ~7,000 reports)

## Data Models

### `CXRStudy` (primary key: `accession_no` as `BigIntegerField`)
- Patient info, study details, Lunit AI scores (12 pathology scores 0–100)
- Ground truth fields: `gt_manual` (manual), `gt_llm` (LLM), `lunit_binarised`
- LLM grade (1–5), supplemental LLM findings per pathology
- Time analysis fields (seconds)
- Indexed on: `workplace`, `procedure_start_date`, `gt_llm`, `lunit_binarised`, `processing_batch_id`

### `ProcessingTask` (primary key: `task_id` UUID string)
- Tracks background processing tasks (queued → processing → completed/failed)
- Stores progress, results (txt_report, csv_data), false negatives JSON

## Key Patterns

### Grading System (Binary Conversion)
- R1–R2 → Binary 0 (Normal)
- R3–R5 → Binary 1 (Abnormal/Actionable)
- `gt_llm = 1 if llm_grade > 2 else 0`

### Background Task Processing
Upload views spawn a daemon thread (`_background_poll_and_save`) that polls the FastAPI `/status/{task_id}` endpoint every 3 seconds. When the task completes, results are fetched from `/results/{task_id}` and saved to the Django DB — surviving page navigation.

### Access Control
- All views require `@login_required`
- Viewer app additionally requires admin: `user.is_superuser` or membership in the `admins` group
- Django admin panel at `/admin/`
- Superuser auto-created on first Docker start from `DJANGO_SUPERUSER_*` env vars

### Thresholds
Site-specific Lunit score thresholds for binarisation. Default: 10 for most pathologies, 15 for nodule. `YIS` site overrides nodule to 5.

## Development Commands

### Docker (Production)
```bash
# First time: copy and configure environment
cp .env.example .env
# Edit .env with real values

# Generate self-signed TLS certs for dev
cd nginx && bash generate-certs.sh && cd ..

# Build and start all services
docker-compose up --build

# Access at https://localhost
```

### Local Development (Django only)
```bash
cd django-app
pip install -r requirements.txt
pip install gunicorn whitenoise

# Set environment variables or use defaults (DEBUG=True)
export DJANGO_DEBUG=True
export DJANGO_SECRET_KEY=dev-secret-key

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
# Access at http://localhost:8000
```

### Local Development (API only)
```bash
cd cxr-audit-api
pip install -r api_requirements.txt
python combined_server.py --api-only
# API at http://localhost:1221
```

### Run tests
```bash
cd django-app
python manage.py test
```

## Environment Variables

All configuration is via environment variables (see `.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `DJANGO_SECRET_KEY` | insecure fallback | Django secret key |
| `DJANGO_DEBUG` | `False` | Debug mode |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Allowed hostnames |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://localhost` | CSRF trusted origins |
| `DJANGO_SUPERUSER_USERNAME/PASSWORD/EMAIL` | — | Auto-created on first start |
| `CXR_API_IP` | `localhost` / `api` in Docker | FastAPI service hostname |
| `CXR_API_PORT` | `1221` | FastAPI service port |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434/v1` | Ollama LLM endpoint |
| `OLLAMA_MODEL` | `qwen3:32b-q4_K_M` | LLM model name |
| `OLLAMA_MAX_WORKERS` | `8` | Concurrent LLM workers |
| `GUNICORN_WORKERS` | `3` | Gunicorn worker count |
| `GUNICORN_TIMEOUT` | `120` | Gunicorn request timeout |
| `EMAIL_HOST` / `EMAIL_HOST_USER` / etc. | Gmail defaults | SMTP for report emailing |

## URL Map

| Path | App | Auth | Description |
|------|-----|------|-------------|
| `/` | — | — | Redirects to `/upload/` |
| `/login/` | auth | — | Login page |
| `/logout/` | auth | — | Logout |
| `/admin/` | Django admin | superuser | Admin panel |
| `/upload/` | upload | login | File upload interface |
| `/upload/tasks/` | upload | login | Task history list |
| `/upload/import/` | upload | login | Import historical CSV data |
| `/upload/api/*` | upload | login | AJAX endpoints (proxy to FastAPI) |
| `/view/` | viewer | admin | Database browser |
| `/view/study/<id>/` | viewer | admin | Study detail |
| `/view/export/` | viewer | admin | CSV export |
| `/report/` | report | login | Analytics dashboard |
| `/report/generate/` | report | login | Generate report for date range |
| `/report/email-report/` | report | login | Email report |
| `/gt/` | gt | login | Manual GT audit page |
| `/gt/api/download-reports` | gt | login | Download sample for manual grading |
| `/gt/api/apply-gt` | gt | login | Upload manual labels |

## Conventions

- Accession numbers are `BigIntegerField` primary keys
- Column naming: `gt_manual` (manual ground truth), `gt_llm` (LLM ground truth), `lunit_binarised` (Lunit binary prediction)
- Files ending in `-DESKTOP-*` are backup/conflict copies — ignore them
- Database: SQLite at `django-app/db/db.sqlite3` (volume-mounted in Docker)
- Static files served by WhiteNoise (no separate static file server needed)
- All datetime fields use UTC (`USE_TZ = True`)
