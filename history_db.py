# -*- coding: utf-8 -*-
import os
import math
import requests
import pandas as pd
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
@@ -49,25 +50,82 @@ def save_run(payload: dict, df_res=None):
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


def list_runs() -> pd.DataFrame:
    base, headers = _cfg()
    params = {
        "select": "id,data_hora,fase,custo_R_kg",
        "order": "data_hora.desc",
    }
    r = requests.get(
        f"{base}/rest/v1/runs",
        headers=headers,
        params=params,
        timeout=30,
    )

    if not r.ok:
        raise RuntimeError(f"Supabase list failed: {r.status_code} - {r.text}")

    rows = []
    for item in r.json():
        rows.append(
            {
                "id": item.get("id"),
                "data_hora": item.get("data_hora"),
                "fase": item.get("fase"),
                "custo_R$_kg": item.get("custo_R_kg"),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["id", "data_hora", "fase", "custo_R$_kg"])
    return pd.DataFrame(rows)


def load_run(run_id: str) -> dict:
    base, headers = _cfg()
    params = {
        "select": "payload",
        "id": f"eq.{run_id}",
        "limit": 1,
    }
    r = requests.get(
        f"{base}/rest/v1/runs",
        headers=headers,
        params=params,
        timeout=30,
    )

    if not r.ok:
        raise RuntimeError(f"Supabase load failed: {r.status_code} - {r.text}")

    data = r.json()
    if not data:
        raise RuntimeError(f"Run id not found: {run_id}")

    payload = data[0].get("payload")
    return payload if payload is not None else data[0]
