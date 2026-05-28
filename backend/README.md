# Aristeus Backend

FastAPI + SQLite + Alembic. See [../PLAN.md](../PLAN.md) for the overall design.

## Local setup (Windows / PowerShell)

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
# edit .env

# create initial migration (covers the HealthPing table)
alembic revision --autogenerate -m "init"
alembic upgrade head

# run the dev server
uvicorn app.main:app --reload --port 8000
```

Visit:
- API:    http://localhost:8000/api/health
- Docs:   http://localhost:8000/api/docs

## Layout

```
app/
  main.py        FastAPI app
  config.py      pydantic-settings
  db.py          SQLAlchemy engine + Base
  models.py      ORM models
alembic/         migrations
```
