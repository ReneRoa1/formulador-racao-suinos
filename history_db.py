# -*- coding: utf-8 -*-
import os
import pandas as pd
import requests
from datetime import datetime

def _cfg():
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("Faltam SUPABASE_URL e SUPABASE_SERVICE_KEY nas variáveis de ambiente.")
    base = url.rstrip("/") + "/rest/v1"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    return base, headers

def save_run(payload: dict, df_res: pd.DataFrame) -> dict:
    base, headers = _cfg()

    run_id = payload.get("id") or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    payload = dict(payload)
    payload["id"] = run_id

    row = {
        "id": run_id,
        "data_hora": payload.get("data_hora"),
        "fase": payload.get("fase"),
        "custo_rs_kg": payload.get("custo_R$_kg"),
        "payload": payload,
    }

    r = requests.post(
        f"{base}/runs",
        headers={**headers, "Prefer": "resolution=merge-duplicates"},
        json=row,
        timeout=30,
    )
    if r.status_code not in (200, 201, 204):
        raise RuntimeError(f"Erro ao salvar no Supabase: {r.status_code} - {r.text}")

    return {"id": run_id}

def list_runs() -> pd.DataFrame:
    base, headers = _cfg()
    r = requests.get(
        f"{base}/runs?select=id,data_hora,fase,custo_rs_kg,created_at&order=created_at.desc&limit=200",
        headers=headers,
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Erro ao listar no Supabase: {r.status_code} - {r.text}")

    data = r.json() or []
    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame(columns=["id", "data_hora", "fase", "custo_rs_kg", "created_at"])
    return df

def load_run(run_id: str) -> dict:
    base, headers = _cfg()
    r = requests.get(
        f"{base}/runs?select=payload&id=eq.{run_id}",
        headers=headers,
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Erro ao carregar no Supabase: {r.status_code} - {r.text}")

    data = r.json()
    if not data:
        raise FileNotFoundError(f"ID não encontrado: {run_id}")
    return data[0]["payload"]
