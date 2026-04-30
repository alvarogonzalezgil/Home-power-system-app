# Home power system

Monorepo: **Angular** frontend and **Python + FastAPI** backend for a home energy dashboard.

## Features

- **Theoretical max clear-sky PV** from a **full calendar date** (year–month–day) using the PVEducation-style model ([backend/app/services/solar_calculator.py](backend/app/services/solar_calculator.py)).
- **FoxESS measured PV** (`pvPower` history) overlaid on the same chart for comparison — requires a **Personal Access Token** in the environment variable **`FOXESS_PAT`** (see [FoxESS Open API](https://www.foxesscloud.com/public/i18n/en/OpenApiDocument.html)).
- **System settings** (location, array geometry, optional inverter serial, etc.) persisted as JSON via `/api/system/config`.

## Quick start

### Backend

Set your FoxESS PAT in the same shell you use to start the API (required for actual PV data; theoretical-only still works if unset for `/api/pv/day`):

**Windows PowerShell**

```powershell
$env:FOXESS_PAT = "<your-PAT-from-FoxESS-cloud>"
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Linux / macOS**

```bash
export FOXESS_PAT="<your-PAT>"
cd backend
python -m venv .venv
source .venv/bin/activate
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

Opens the dev server at **<http://localhost:4200>** — ensure the backend is on **port 8000** or change `apiBase` in [frontend/src/environments/environment.development.ts](frontend/src/environments/environment.development.ts).

## Main API routes

| Route | Purpose |
|-------|---------|
| `GET /api/pv/day?year=&month=&day=` | Theoretical clear-sky curve (W) |
| `GET /api/foxess/pv/day?date=YYYY-MM-DD` | FoxESS `pvPower` for that day (W), resampled to match sample step |
| `GET/PUT /api/system/config` | Persisted settings |

## Tests (backend)

```bash
cd backend
python -m pytest
```

## Project layout

| Path | Purpose |
|------|--------|
| [backend/app/main.py](backend/app/main.py) | FastAPI app, CORS for `localhost:4200` |
| [backend/app/services/solar_calculator.py](backend/app/services/solar_calculator.py) | Clear-sky PV model |
| [backend/app/integrations/foxess/client.py](backend/app/integrations/foxess/client.py) | Signed FoxESS Cloud REST client |
| [backend/app/services/foxess_service.py](backend/app/services/foxess_service.py) | SN resolution + history resampling |
| [frontend/src/app/features/pv-dashboard/](frontend/src/app/features/pv-dashboard/) | Date picker + Plotly overlay chart |
| [frontend/src/app/features/settings/](frontend/src/app/features/settings/) | Settings form |

## References

- [PVEducation](https://www.pveducation.org/) — photovoltaics theory (e.g. chapter 2).
- [FoxESS Open API](https://www.foxesscloud.com/public/i18n/en/OpenApiDocument.html).
