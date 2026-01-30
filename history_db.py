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
    """Converte qualquer coisa para JSON-safe."""

    import math
    import numpy as np
    import pandas as pd
    from datetime import datetime, date

    if obj is None:
        return None

    # pandas Timestamp
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()

    # datetime/date
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()

    # floats problemáticos
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj

    # numpy numbers
    if isinstance(obj, (np.floating, np.integer)):
        return _sanitize(obj.item())

    # dict
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}

    # list/tuple
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]

    return obj




def save_run(payload: dict, df_res=None) -> dict:
    base, headers = _cfg()
    payload2 = _sanitize(payload)

    # pega custo de onde estiver (fallback)
    custo_r_kg = payload2.get("custo_R_kg")
    if custo_r_kg is None:
        custo_r_kg = payload2.get("custo_R$_kg")

    row = {
        "id": str(uuid.uuid4()),  # evita NULL
        "codigo": payload2.get("codigo"),
        "data_hora": payload2.get("data_hora"),
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
            "select": "id,codigo,data_hora,fase,custo_R_kg,payload",
            "order": "id.desc",  # <<< MUDOU AQUI
        },
        timeout=30,
    )

    
    r.raise_for_status()
    data = r.json() or []

    # Se você não quer mostrar payload na tabela, dá pra omitir na view depois.
    return pd.DataFrame(data)



def load_run(run_id: str) -> dict:
    base, headers = _cfg()

    r = requests.get(
        f"{base}/rest/v1/runs",
        headers=headers,
        params={
            "select": "id,codigo,data_hora,fase,custo_R_kg,payload",
            "id": f"eq.{run_id}",
            "limit": "1",
        },
        timeout=30,
    )
    r.raise_for_status()

    rows = r.json() or []
    if not rows:
        raise RuntimeError(f"ID {run_id} não encontrado no Supabase.")

    row = rows[0]
    payload = row.get("payload") or {}

    payload["id"] = row.get("id")
    payload["codigo"] = row.get("codigo")
    payload["data_hora"] = row.get("data_hora")
    payload["fase"] = row.get("fase")
    payload["custo_R_kg"] = row.get("custo_R_kg")

    return payload



def get_run(run_id: str) -> dict | None:
    base, headers = _cfg()

    r = requests.get(
        f"{base}/rest/v1/runs",
        headers=headers,
        params={
            "select": "id,data_hora,fase,custo_r_kg,payload",
            "id": f"eq.{run_id}",
            "limit": "1",
        },
        timeout=30,
    )
    r.raise_for_status()
    rows = r.json() or []
    return rows[0] if rows else None
