# -*- coding: utf-8 -*-
import os
import math
import requests
import pandas as pd


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


def save_run(payload: dict, df_res=None) -> dict:
    base, headers = _cfg()
    payload2 = _sanitize(payload)

    r = requests.post(
        f"{base}/rest/v1/runs",
        headers=headers,
        json=payload2,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return data[0] if isinstance(data, list) and data else data


def list_runs() -> pd.DataFrame:
    base, headers = _cfg()

    r = requests.get(
        f"{base}/rest/v1/runs",
        headers=headers,
        params={
            "select": "id,data_hora,fase,custo_R$_kg",
            "order": "data_hora.desc",
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json() or []
    return pd.DataFrame(data, columns=["id", "data_hora", "fase", "custo_R$_kg"])


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
