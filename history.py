# -*- coding: utf-8 -*-
import json
import os
from datetime import datetime
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
HIST_DIR = BASE_DIR / "data" / "history"
HIST_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(text: str) -> str:
    # deixa nome de arquivo seguro
    keep = []
    for ch in str(text):
        if ch.isalnum() or ch in ("-", "_"):
            keep.append(ch)
        elif ch in (" ", "/", "\\", "|", ":", ";", ","):
            keep.append("_")
    return "".join(keep).strip("_")[:80] or "sem_nome"


def save_run(payload: dict, df_res: pd.DataFrame) -> dict:
    """
    Salva:
      - JSON com tudo (reabrir)
      - CSV com inclusão (consulta rápida)
    Retorna metadados (id, caminhos)
    """
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    fase = payload.get("fase", "sem_fase")
    run_name = f"{run_id}__{_safe_filename(fase)}"

    json_path = HIST_DIR / f"{run_name}.json"
    csv_path = HIST_DIR / f"{run_name}.csv"

    # salva JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # salva CSV
    df_res.to_csv(csv_path, index=False, encoding="utf-8")

    return {
        "id": run_name,
        "json_path": str(json_path),
        "csv_path": str(csv_path),
    }


def list_runs() -> pd.DataFrame:
    """
    Lista os históricos (lendo metadados básicos do JSON).
    """
    rows = []
    for p in sorted(HIST_DIR.glob("*.json"), reverse=True):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            rows.append({
                "id": p.stem,
                "data_hora": data.get("data_hora"),
                "fase": data.get("fase"),
                "custo_R$_kg": data.get("custo_R$_kg"),
            })
        except Exception:
            # se algum json estiver quebrado, ignora
            continue

    if not rows:
        return pd.DataFrame(columns=["id", "data_hora", "fase", "custo_R$_kg"])
    return pd.DataFrame(rows)


def load_run(run_id: str) -> dict:
    json_path = HIST_DIR / f"{run_id}.json"
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)

