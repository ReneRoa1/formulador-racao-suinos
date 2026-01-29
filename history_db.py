# -*- coding: utf-8 -*-
import math
import os
from datetime import datetime

import pandas as pd
import requests


def _cfg():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")

    if not url or not key:
        raise RuntimeError(
            "Missing SUPABASE_URL and/or SUPABASE_KEY (or SUPABASE_ANON_KEY) environment variables."
        )

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    return url, headers


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


def save_run(payload: dict, df_res=None):
        try:
        base, headers = _cfg()
    except RuntimeError:
        from history import save_run as local_save_run

        return local_save_run(payload, df_res)

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
    try:
        base, headers = _cfg()
    except RuntimeError:
        from history import list_runs as local_list_runs

        return local_list_runs()

    r = requests.get(
        f"{base}/rest/v1/runs?select=id,data_hora,fase,custo_R_kg&order=data_hora.desc",
        headers=headers,
        timeout=30,
    )

    if not r.ok:
        raise RuntimeError(f"Supabase list failed: {r.status_code} - {r.text}")

    rows = r.json()
    if not rows:
        return pd.DataFrame(columns=["id", "data_hora", "fase", "custo_R$_kg"])

    df = pd.DataFrame(rows)
    df = df.rename(columns={"custo_R_kg": "custo_R$_kg"})
    return df[["id", "data_hora", "fase", "custo_R$_kg"]]


def load_run(run_id: str) -> dict:
    try:
        base, headers = _cfg()
    except RuntimeError:
        from history import load_run as local_load_run

        return local_load_run(run_id)

    r = requests.get(
        f"{base}/rest/v1/runs?select=payload&id=eq.{run_id}&limit=1",
        headers=headers,
        timeout=30,
    )

    if not r.ok:
        raise RuntimeError(f"Supabase load failed: {r.status_code} - {r.text}")

    rows = r.json()
    if not rows:
        raise ValueError(f"Run not found: {run_id}")

    payload = rows[0].get("payload")
    if payload is None:
        return rows[0]

    return payload
