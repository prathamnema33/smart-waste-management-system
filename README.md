# Smart Waste Management System

A full-stack waste-management application with a FastAPI backend and a Next.js
frontend. The system supports citizen and operations workflows, collection
monitoring, team management, alerts, and analytics for municipal waste services.

## Technology

- **Frontend:** Next.js, React, TypeScript, Leaflet, and Recharts
- **Backend:** FastAPI, SQLAlchemy, and PostgreSQL
- **Analytics:** Python ETL and EDA workflows with CSV exports and charts

## Project structure

```text
backend/    FastAPI application, database migrations, and analytics workflows
frontend/   Next.js web application
```

## Prerequisites

- Python 3.10 or later
- Node.js and npm
- PostgreSQL

## Run locally

### Backend

From the repository root, create and activate a Python virtual environment, then
install the backend dependencies:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Configure the database connection using the environment variables expected by
the backend. Set a unique signing key in the same terminal before starting the
API. For local development, generate one with:

```powershell
$env:SECRET_KEY = (python -c "import secrets; print(secrets.token_urlsafe(32))")
```

Do not commit credentials or local environment files. Apply the database
migrations in `backend/migrations` as required for your database, then start the
API:

```powershell
python -m uvicorn main:app --reload
```

The API is available at `http://127.0.0.1:8000`.

### Frontend

In another terminal:

```powershell
cd frontend
npm install
Copy-Item .env.local.example .env.local
npm run dev
```

The frontend is available at `http://localhost:3000`. Set
`NEXT_PUBLIC_API_URL` in `frontend/.env.local` if the backend is running at a
different address.

## Analytics

The backend README documents the ETL, EDA, development-data seeding, and
analytics-readiness test workflows. See
[`backend/analytics/README.md`](backend/analytics/README.md) for analytics
outputs and reporting guidance.

## Development

Run the frontend lint command from `frontend`:

```powershell
npm run lint
```

Backend setup details, database migrations, monitoring, and tests are described
in [`backend/README.md`](backend/README.md).

## Security and configuration

Keep database credentials, tokens, and local `.env` files out of version
control. The checked-in `frontend/.env.local.example` contains only the local
API URL placeholder; configure real secrets through your deployment platform.
