"""FoxESS Cloud Open API client (private token / PAT auth)."""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any

import httpx

from app.integrations.http_verify import build_default_verify

# FoxESS Open API request domain (per official docs).
# Override via env var FOXESS_DOMAIN if FoxESS ever points you at a regional host.
DEFAULT_DOMAIN = "https://www.foxesscloud.com"


def get_domain() -> str:
    return (os.environ.get("FOXESS_DOMAIN") or DEFAULT_DOMAIN).rstrip("/")


def _build_verify() -> bool | str | ssl.SSLContext:
    """
    Build the `verify` value for httpx, in priority order:
      1. FOXESS_VERIFY_SSL=false  -> disable verification (dev only)
      2. FOXESS_CA_BUNDLE=<path>  -> use that PEM bundle
      3. truststore (if installed) -> use the OS trust store (recommended on
         corporate networks where TLS-intercepting proxies inject a root CA
         that is already trusted by the OS but not by certifi)
      4. fall back to httpx default (certifi bundle)
    """
    flag = (os.environ.get("FOXESS_VERIFY_SSL") or "").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False

    bundle = (os.environ.get("FOXESS_CA_BUNDLE") or "").strip()
    if bundle:
        return bundle

    try:
        import truststore  # type: ignore[import-not-found]

        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        return ctx
    except Exception:
        return True


class FoxessAuthError(RuntimeError):
    """Missing token or auth setup failure."""


class FoxessApiError(RuntimeError):
    """FoxESS returned errno != 0 or HTTP/network error."""


class FoxessClient:
    """Signed POST requests per https://www.foxesscloud.com Open API."""

    def __init__(self, token: str | None = None) -> None:
        self.token = (token or os.environ.get("FOXESS_PAT", "") or "").strip()
        if not self.token:
            raise FoxessAuthError("FOXESS_PAT environment variable is not set")

    def _headers(self, path: str) -> dict[str, str]:
        ts = str(round(time.time() * 1000))
        # FoxESS Open API requires the LITERAL 4 characters \r\n between fields,
        # not real CRLF. Their docs use a Python *raw* f-string fr'{path}\r\n...'
        # — which evaluates to backslash-r-backslash-n. Real CRLF causes errno
        # 40256 ("request header parameters are missing") at the gateway.
        sig_src = f"{path}\\r\\n{self.token}\\r\\n{ts}"
        signature = hashlib.md5(sig_src.encode("utf-8")).hexdigest()
        return {
            "token": self.token,
            "timestamp": ts,
            "signature": signature,
            "lang": "en",
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (compatible; HomePowerSystem/1.0; "
                "+https://github.com/)"
            ),
        }

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{get_domain()}{path}"
        timeout = httpx.Timeout(25.0)
        try:
            with httpx.Client(timeout=timeout, verify=build_default_verify()) as client:
                r = client.post(url, json=body, headers=self._headers(path))
        except httpx.ConnectError as e:
            msg = str(e)
            if "CERTIFICATE_VERIFY_FAILED" in msg or "self signed certificate" in msg:
                raise FoxessApiError(
                    f"TLS verification failed connecting to {url}: {msg}. "
                    "If you are behind a corporate proxy, install the "
                    "'truststore' package (already in requirements) so the OS "
                    "trust store is used, or set FOXESS_CA_BUNDLE=<path-to.pem>, "
                    "or set FOXESS_VERIFY_SSL=false (dev only)."
                ) from e
            raise FoxessApiError(f"Connection error to {url}: {msg}") from e
        except httpx.RequestError as e:
            raise FoxessApiError(f"Network error to {url}: {e}") from e
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise FoxessApiError(
                f"HTTP {r.status_code} from {url}: {r.text[:500]}"
            ) from e
        try:
            data = r.json()
        except ValueError as e:
            raise FoxessApiError(f"Invalid JSON from {url}: {r.text[:200]}") from e
        errno = data.get("errno", 0)
        if errno != 0:
            msg = data.get("msg", data.get("message", str(data)))
            raise FoxessApiError(f"FoxESS errno={errno} ({url}): {msg}")
        return data

    def list_devices(self) -> list[dict[str, Any]]:
        raw = self.post(
            "/op/v0/device/list",
            {"currentPage": 1, "pageSize": 100},
        )
        result = raw.get("result") or {}
        return list(result.get("data") or [])

    def history_query(
        self,
        sn: str,
        variables: list[str],
        begin_ms: int,
        end_ms: int,
    ) -> list[dict[str, Any]]:
        raw = self.post(
            "/op/v0/device/history/query",
            {
                "sn": sn,
                "variables": variables,
                "begin": begin_ms,
                "end": end_ms,
            },
        )
        return list(raw.get("result") or [])
