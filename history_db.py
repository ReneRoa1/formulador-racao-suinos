# -*- coding: utf-8 -*-
import os
import math
import requests
import pandas as pd
import uuid
from datetime import datetime


def _cfg():
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not base or not key:
        raise RuntimeError("Faltam SUPABASE_URL e SUPABASE_SERVICE_KEY nas variáveis de ambiente.")

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    return base, headers


def _sanitize(obj):
    if obj is None:
        return None
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    try:
        import numpy as np
        if isinstance(obj, np.floating):
            v = float(obj)
            if math.isnan(v) or math.isinf(v):
                return None
            return v
        if isinstance(obj, np.integer):
            return int(obj)
    except Exception:
        pass

    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


from datetime import datetime

def save_run(payload: dict, df_res=None) -> dict:
    base, headers = _cfg()
    payload2 = _sanitize(payload)

    # pega custo de onde estiver (ajuste se seu payload usa outro nome)
    custo_r_kg = payload2.get("custo_R_kg")
    if custo_r_kg is None:
        custo_r_kg = payload2.get("custo_R$_kg")  # fallback se ainda existir no app

    row = {
    "id": str(uuid.uuid4()),  # <- evita NULL
    "data_hora": payload2.get("data_hora") or datetime.now().isoformat(),
    "fase": payload2.get("fase"),
    "custo_R_kg": custo_r_kg,
    "payload": payload2,
    }

    r = requests.post(
        f"{base}/rest/v1/runs",
        headers=headers,
        json=row,
        timeout=30,
    )

    if not r.ok:
        raise RuntimeError(f"Supabase insert falhou ({r.status_code}). Resposta: {r.text}")

    data = r.json()
    return data[0] if isinstance(data, list) and data else data




def list_runs() -> pd.DataFrame:
    base, headers = _cfg()

    r = requests.get(
        f"{base}/rest/v1/runs",
        headers=headers,
        params={
            "select": "id,data_hora,fase,custo_R_kg",
            "order": "data_hora.desc",
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json() or []
    return pd.DataFrame(data, columns=["id", "data_hora", "fase", "custo_R_kg"])


def load_run(run_id: str) -> dict:
    base, headers = _cfg()

    r = requests.get(
        f"{base}/rest/v1/runs",
        headers=headers,
        params={
            "id": f"eq.{run_id}",
            "select": "*",
            "limit": 1,
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json() or []
    return data[0] if data else {}
