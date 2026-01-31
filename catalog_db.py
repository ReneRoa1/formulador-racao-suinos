import os
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
        "Prefer": "return=representation",
    }
    return base, headers

def _sanitize(obj):
    import math
    import numpy as np
    import pandas as pd
    from datetime import datetime, date

    if obj is None:
        return None
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
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


def import_foods_from_df(df_food: pd.DataFrame) -> int:
    """
    Espera a aba Alimentos com colunas:
    - Alimentos (nome)
    - Preco (R$/kg) (ou Preco)
    - demais colunas = nutrientes
    """
    base, headers = _cfg()
    df = df_food.copy()

    # Normaliza nomes de colunas mais comuns
    if "Alimentos" not in df.columns:
        raise ValueError("Coluna 'Alimentos' nao encontrada na aba Alimentos.")
    if "Preco" not in df.columns:
        # tenta achar algo parecido
        cand = [c for c in df.columns if "preco" in c.lower()]
        if cand:
            df = df.rename(columns={cand[0]: "Preco"})
        else:
            raise ValueError("Coluna de preco nao encontrada (ex: 'Preco').")

    nut_cols = [c for c in df.columns if c not in ["Alimentos", "Preco", "Categoria", "categoria"]]

    rows = []
    for _, r in df.iterrows():
        nome = str(r["Alimentos"]).strip()
        if not nome or nome.lower() == "nan":
            continue

        categoria = None
        if "Categoria" in df.columns:
            categoria = r.get("Categoria")
        elif "categoria" in df.columns:
            categoria = r.get("categoria")

        nutrientes = {c: r.get(c) for c in nut_cols}
        payload = {
            "nome": nome,
            "categoria": None if pd.isna(categoria) else str(categoria),
            "preco": None if pd.isna(r.get("Preco")) else float(r.get("Preco")),
            "nutrientes": nutrientes,
        }
        rows.append(_sanitize(payload))

    # upsert por nome
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
    Espera a aba Exigencias com colunas:
    - Exigencia (grupo)
    - Fase
    - demais colunas = nutrientes minimos
    """
    base, headers = _cfg()
    df = df_req.copy()

    if "Exigencia" not in df.columns:
        raise ValueError("Coluna 'Exigencia' nao encontrada na aba Exigencias.")
    if "Fase" not in df.columns:
        raise ValueError("Coluna 'Fase' nao encontrada na aba Exigencias.")

    # Preenche blocos
    df["Exigencia"] = df["Exigencia"].ffill()

    nut_cols = [c for c in df.columns if c not in ["Exigencia", "Fase"]]

    rows = []
    for _, r in df.iterrows():
        ex = r.get("Exigencia")
        fase = r.get("Fase")
        if pd.isna(ex) or pd.isna(fase):
            continue

        req_min = {c: r.get(c) for c in nut_cols}

        payload = {
            "exigencia": str(ex).strip(),
            "fase": str(fase).strip(),
            "req_min": req_min,
        }
        rows.append(_sanitize(payload))

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
        params={"select": "nome,categoria,preco,nutrientes,updated_at", "order": "nome.asc"},
        timeout=30,
    )
    r.raise_for_status()
    return pd.DataFrame(r.json() or [])


def fetch_requirements() -> pd.DataFrame:
    base, headers = _cfg()
    r = requests.get(
        f"{base}/rest/v1/requirements",
        headers=headers,
        params={"select": "exigencia,fase,req_min,updated_at", "order": "exigencia.asc,fase.asc"},
        timeout=30,
    )
    r.raise_for_status()
    return pd.DataFrame(r.json() or [])
