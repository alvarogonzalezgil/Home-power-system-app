"""Shared httpx TLS verify configuration (truststore / corporate proxy)."""

from __future__ import annotations

import os
import ssl


def build_default_verify() -> bool | str | ssl.SSLContext:
    """
    Build the `verify` value for httpx, in priority order:
      1. FOXESS_VERIFY_SSL=false  -> disable verification (dev only)
      2. FOXESS_CA_BUNDLE=<path>  -> use that PEM bundle
      3. truststore (if installed) -> use the OS trust store
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
