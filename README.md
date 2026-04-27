# Home power system (iteration 1)

Monorepo: **Angular** frontend and **Python + FastAPI** backend for a home energy dashboard.

## Features (this iteration)

- **Theoretical max clear-sky PV** curve for a chosen **month and day** (no year; reference year 2025 in the backend for day-of-year).
- **System settings** (location, array geometry, efficiency) persisted as JSON and loaded by the API.
- **No** device integrations yet (FoxESS, MyEnergi, Octopus) — only placeholder packages under `backend/app/integrations/`.

## Quick start

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API docs: <http://localhost:8000/docs>  
- Override config path: set env `HOME_POWER_CONFIG_PATH` to a JSON file path (same shape as [backend/app/data/system_config.json](backend/app/data/system_config.json)).

### Frontend

In another terminal:

```bash
cd frontend
npm install
npm start
```

Opens the dev server at **<http://localhost:4200>** (proxies not used — ensure the backend is on **port 8000** or change `apiBase` in [frontend/src/environments/environment.development.ts](frontend/src/environments/environment.development.ts)).

## Tests (backend)

```bash
cd backend
python -m pytest
```

## Project layout

| Path | Purpose |
|------|--------|
| [backend/app/main.py](backend/app/main.py) | FastAPI app, CORS for `localhost:4200` |
| [backend/app/services/solar_calculator.py](backend/app/services/solar_calculator.py) | PVEducation ch.2–style clear-sky model |
| [backend/app/api/](backend/app/api/) | `/api/pv/day`, `/api/system/config` |
| [frontend/src/app/features/pv-dashboard/](frontend/src/app/features/pv-dashboard/) | Date selector + Plotly chart |
| [frontend/src/app/features/settings/](frontend/src/app/features/settings/) | Settings form |

## References

- [PVEducation](https://www.pveducation.org/) — photovoltaics theory (e.g. chapter 2: solar position and irradiance).
