# -*- coding: utf-8 -*-
import os
import math
import requests
import pandas as pd

def _cfg():
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not base or not key:
        raise RuntimeError("Missing SUPABASE_URL and SUPABASE_SERVICE_KEY env vars.")


    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    return base, headers


def _sanitize(obj):
    """Converte qualquer coisa para JSON-safe (inclui Timestamp/NaN)."""
    import numpy as np
    from datetime import datetime, date

    if obj is None:
        return None

    try:
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
    except Exception:
        pass

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj

    if isinstance(obj, (np.floating, np.integer)):
        return _sanitize(obj.item())

    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]

    return obj


def _row_to_nutrients(row: pd.Series, exclude: set[str]) -> dict:
    d = {}
    for k, v in row.items():
        if k in exclude:
            continue
        v2 = _sanitize(v)
        if v2 is None:
            continue
        d[str(k)] = v2
    return d


def import_foods_from_df(df_food: pd.DataFrame) -> int:
    """
    Espera df_food com colunas tipo:
    - 'Alimentos' (nome)
    - 'Preco' (R$/kg)
    - demais colunas = nutrientes
    """
    base, headers = _cfg()

    df = df_food.copy()

    # tenta achar nomes padrão do seu app
    nome_col = "Alimentos" if "Alimentos" in df.columns else ("Ingrediente" if "Ingrediente" in df.columns else None)
    preco_col = "Preco" if "Preco" in df.columns else ("Preco_R$/kg" if "Preco_R$/kg" in df.columns else None)
    categoria_col = "Categoria" if "Categoria" in df.columns else None

    if not nome_col:
        raise ValueError("Não encontrei coluna de nome do alimento (Alimentos/Ingrediente).")

    rows = []
    for _, r in df.iterrows():
        nome = str(r.get(nome_col, "")).strip()
        if not nome:
            continue

        preco = r.get(preco_col) if preco_col else None
        cat = str(r.get(categoria_col, "")).strip() if categoria_col else None

        nutrientes = _row_to_nutrients(r, exclude={nome_col} | ({preco_col} if preco_col else set()) | ({categoria_col} if categoria_col else set()))

        payload = {
            "nome": nome,
            "categoria": cat if cat else None,
            "preco": _sanitize(preco),
            "nutrientes": nutrientes,
        }
        rows.append(payload)

    if not rows:
        return 0

    # upsert via PostgREST
    r = requests.post(
        f"{base}/rest/v1/foods?on_conflict=nome",
        headers=headers,
        json=rows,
        timeout=60,
    )
    r.raise_for_status()
    return len(rows)


def import_requirements_from_df(df_req: pd.DataFrame) -> int:
    """
    Espera df_req com colunas:
    - 'Exigencia' (grupo)
    - 'Fase' (fase)
    - demais colunas = requerimentos mínimos (nutrientes)
    """
    base, headers = _cfg()

    df = df_req.copy()
    if "Exigencia" not in df.columns or "Fase" not in df.columns:
        raise ValueError("Aba Exigencias precisa ter colunas 'Exigencia' e 'Fase'.")

    df["Exigencia"] = df["Exigencia"].ffill()

    rows = []
    for _, r in df.iterrows():
        exg = str(r.get("Exigencia", "")).strip()
        fase = str(r.get("Fase", "")).strip()
        if not exg or not fase:
            continue

        req_min = _row_to_nutrients(r, exclude={"Exigencia", "Fase"})
        payload = {"exigencia": exg, "fase": fase, "req_min": req_min}
        rows.append(payload)

    if not rows:
        return 0

    r = requests.post(
        f"{base}/rest/v1/requirements?on_conflict=exigencia,fase",
        headers=headers,
        json=rows,
        timeout=60,
    )
    r.raise_for_status()
    return len(rows)


def fetch_foods() -> pd.DataFrame:
    base, headers = _cfg()
    r = requests.get(
        f"{base}/rest/v1/foods",
        headers=headers,
        params={"select": "nome,categoria,preco,nutrientes", "order": "nome.asc"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json() or []
    return pd.DataFrame(data)


def fetch_requirements() -> pd.DataFrame:
    base, headers = _cfg()
    r = requests.get(
        f"{base}/rest/v1/requirements",
        headers=headers,
        params={"select": "exigencia,fase,req_min", "order": "exigencia.asc,fase.asc"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json() or []
    return pd.DataFrame(data)


def foods_to_df_for_solver(df_foods: pd.DataFrame) -> pd.DataFrame:
    """
    Converte formato do banco -> formato que seu solver usa (colunas planas).
    """
    if df_foods.empty:
        return pd.DataFrame()

    rows = []
    for _, r in df_foods.iterrows():
        nut = r.get("nutrientes") or {}
        row = {"Alimentos": r.get("nome"), "Preco": r.get("preco")}
        row.update(nut)
        rows.append(row)
    return pd.DataFrame(rows)


def requirements_to_df_for_ui(df_req_db: pd.DataFrame) -> pd.DataFrame:
    """
    Banco -> DataFrame com colunas Exigencia/Fase + nutrientes (planos).
    """
    if df_req_db.empty:
        return pd.DataFrame()

    rows = []
    for _, r in df_req_db.iterrows():
        req = r.get("req_min") or {}
        row = {"Exigencia": r.get("exigencia"), "Fase": r.get("fase")}
        row.update(req)
        rows.append(row)
    return pd.DataFrame(rows)

