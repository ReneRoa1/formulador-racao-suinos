# -*- coding: utf-8 -*-
import pandas as pd


def load_planilha(arquivo):
    """
    Lê a planilha enviada pelo usuário e devolve:
      df_food: tabela de alimentos padronizada
      df_req: tabela de exigências padronizada
    """
    df_food = pd.read_excel(arquivo, sheet_name="Alimentos")
    df_req = pd.read_excel(arquivo, sheet_name="Exigencias")

    # Corrige nome de coluna que às vezes vem com espaço
    if "Alimentos " in df_food.columns and "Alimentos" not in df_food.columns:
        df_food = df_food.rename(columns={"Alimentos ": "Alimentos"})

    # Padroniza nomes (sem você precisar mexer no Excel)
    ren_food = {
        "EM (Suínos)": "EM",
        "P (Digestível)": "Pdig",
        "Custo, R$/kg": "Preco",
        "Met + Cist": "MetCis",
    }
    for k, v in ren_food.items():
        if k in df_food.columns:
            df_food = df_food.rename(columns={k: v})

    ren_req = {
        "EM, kcal/kg": "EM",
        "PB, %": "PB",
        "P (Digestível), %": "Pdig",
        "Ca, %": "Ca",
        "Na, %": "Na",
        "Lisina,  %": "Lisina",
        "Met + Cist, %": "MetCis",
        "Treonina, %": "Treonina",
        "Triptofano, %": "Triptofano",
    }
    for k, v in ren_req.items():
        if k in df_req.columns:
            df_req = df_req.rename(columns={k: v})

    # Remove linhas vazias na Exigencias
    df_req = df_req[df_req["Fase"].notna()].copy()
    df_req["Fase"] = df_req["Fase"].astype(str)

    # Converte colunas numéricas
    num_cols_food = ["PB","EM","Pdig","Ca","Na","Lisina","MetCis","Treonina","Triptofano","FB","EE","Preco"]
    for c in num_cols_food:
        if c in df_food.columns:
            df_food[c] = pd.to_numeric(df_food[c], errors="coerce")

    num_cols_req = ["PB","EM","Pdig","Ca","Na","Lisina","MetCis","Treonina","Triptofano"]
    for c in num_cols_req:
        if c in df_req.columns:
            df_req[c] = pd.to_numeric(df_req[c], errors="coerce")

    return df_food, df_req


def build_ui_table(df_food):
    """
    Cria a tabela base para a UI (Streamlit data_editor),
    adicionando colunas Usar, Min_% e Max_%.
    """
    base_cols = ["Alimentos","Preco","PB","EM","Pdig","Ca","Na","Lisina","MetCis","Treonina","Triptofano","FB","EE"]
    base = df_food[base_cols].copy()

    n = len(base)
    edit = pd.DataFrame({
        "Usar": [True] * n,
        "Min_%": [0.0] * n,
        "Max_%": [100.0] * n,
    })

    return pd.concat([edit.reset_index(drop=True), base.reset_index(drop=True)], axis=1)

