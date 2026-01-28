# -*- coding: utf-8 -*-
import os, json
import math
import requests

def _sanitize(obj):
    """Converte NaN/Inf para None (JSON-safe) e sanitiza recursivamente."""
    if obj is None:
        return None

    # floats problemáticos
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj

    # pandas às vezes vem como numpy types
    try:
        import numpy as np
        if isinstance(obj, (np.floating,)):
            v = float(obj)
            if math.isnan(v) or math.isinf(v):
                return None
            return v
        if isinstance(obj, (np.integer,)):
            return int(obj)
    except Exception:
        pass

    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]

    return obj


def save_run(payload: dict, df_res):
    base = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not base or not key:
        raise RuntimeError("Faltam SUPABASE_URL e SUPABASE_SERVICE_KEY nas variáveis de ambiente.")

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    payload2 = _sanitize(payload)  # ✅ aqui

    r = requests.post(
        f"{base}/rest/v1/runs",
        headers=headers,
        json=payload2,           # ✅ usa o payload limpo
        timeout=30,
    )
    r.raise_for_status()
    return r.json()[0]
