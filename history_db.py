# -*- coding: utf-8 -*-
import os
import math
import requests
import pandas as pd


def _sanitize(obj):
    """Converte NaN/Inf para None (JSON-safe) e sanitiza recursivamente."""
    if obj is None:
        return None

    # floats problemáticos
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj

    # numpy types (quando aparecer)
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
    """
    Lê variáveis de ambiente e monta (base, headers) para Supabase REST.
    Aceita SUPABASE_URL ou Supabase_URL (caso você tenha criado com outro nome no Render).
    """
    base = os.environ.get("SUPABASE_URL") or os.environ.get("Supabase_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_ANON_KEY")

    if not base or not key:
        raise RuntimeError(
            "Faltam SUPABASE_URL (ou Supabase_URL) e SUPABASE_SERVICE_KEY "
            "(ou SUPABASE_ANON_KEY) nas variáveis de ambiente."
        )

    # garante sem barra no final
    base = base.rstrip("/")

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

    r = requests.post(
        f"{base}/rest/v1/runs",
        headers=headers,
        json=payload2,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return data[0] if isinstance(data, list) and data else data


def list_runs():
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
    data = r.json()

    return pd.DataFrame(
        data or [],
        columns=["id", "data_hora", "fase", "custo_R_kg"]  # ✅ igual ao banco
    )



def load_run(run_id: str) -> dict:
    base, headers = _cfg()

    r = requests.get(
        f"{base}/rest/v1/runs",
        headers=headers,
        params={
            "select": "*",
            "id": f"eq.{run_id}",
            "limit": 1,
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return data[0] if data else {}
