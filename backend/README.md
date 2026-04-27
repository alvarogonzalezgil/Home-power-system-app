# Backend (FastAPI)

## Setup

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run (development)

```bash
# From the `backend` directory:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>

## Tests

```bash
python -m pytest
```

## Configuration

`app/data/system_config.json` is the persisted system profile (read/write via `GET/PUT /api/system/config`). Override file path: `HOME_POWER_CONFIG_PATH`.

