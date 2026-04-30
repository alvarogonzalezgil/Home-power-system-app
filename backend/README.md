# Backend (FastAPI)

## Setup

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## FoxESS Personal Access Token

The integration reads **`FOXESS_PAT`** from the environment (your API key from the FoxESS cloud personal center).

**Easiest (recommended):** copy [`backend/.env.example`](.env.example) to **`backend/.env`**, set:

```env
FOXESS_PAT=paste-your-token-here
```

The app loads `.env` automatically on startup (via `python-dotenv`). `.env` is gitignored.

Alternatively set the variable in the shell **before** starting uvicorn:

```powershell
$env:FOXESS_PAT = "<your-PAT>"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

If `FOXESS_PAT` is missing, `GET /api/foxess/pv/day` returns **503**; `GET /api/pv/day` (theoretical only) still works.

### TLS / corporate proxy

FoxESS is reached over HTTPS at **`https://www.foxesscloud.com`**. Behind a TLS-intercepting corporate proxy, the chain ends in a private root CA that Python's bundled `certifi` does not know about, producing:

```
httpx.ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] self signed certificate in certificate chain
```

The backend handles this in three layers (first match wins):

1. **`FOXESS_VERIFY_SSL=false`** — disable verification (dev only, do not use in production).
2. **`FOXESS_CA_BUNDLE=<path-to.pem>`** — verify against your corporate root CA bundle.
3. **OS trust store** via the [`truststore`](https://github.com/sethmlarson/truststore) package (in `requirements.txt`). On Windows this picks up corporate roots already trusted by the OS — usually no extra config needed once the CA is installed there.

You can also override the host with **`FOXESS_DOMAIN`** if FoxESS ever directs you to a regional URL.

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

Optional fields:

- `inverter_sn` — FoxESS inverter serial; omit or leave empty to auto-detect the first `hasPV` device on first FoxESS call (cached back into this file).
- `foxess_power_unit` — `"kW"` or `"W"` for raw `pvPower` from history (default `"kW"`).
