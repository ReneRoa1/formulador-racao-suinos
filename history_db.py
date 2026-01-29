# -*- coding: utf-8 -*-
import os
import math
import requests
from datetime import datetime

def _sanitize(obj):
    if obj is None:
        return None
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj

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

def _cfg():
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
    return base, headers

def save_run(payload: dict, df_res=None):
    base, headers = _cfg()
    payload2 = _sanitize(payload)

    # id simples (string) pra bater com a tabela que sugeri
    run_id = payload2.get("id") or datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    row = {
        "id": run_id,
        "data_hora": payload2.get("data_hora"),
        "fase": payload2.get("fase"),
        "custo_R_kg": payload2.get("custo_R_kg"),
        "payload": payload2,  # ✅ guarda tudo aqui
    }

    r = requests.post(
        f"{base}/rest/v1/runs",
        headers=headers,
        json=row,
        timeout=30,
    )

    if not r.ok:
        # isso vai te dizer o motivo EXATO do 400
        raise RuntimeError(f"Supabase insert failed: {r.status_code} - {r.text}")

    return r.json()[0]
