# -*- coding: utf-8 -*-
import streamlit as st

st.set_page_config(page_title="Formulador de Ração - Suínos", layout="wide")

import pandas as pd
from datetime import datetime
import streamlit.components.v1 as components

from history_db import save_run, list_runs, load_run
from reporting import build_report_html, make_pdf_report
from io_excel import load_planilha, build_ui_table
from solver import solve_lp, calc_dieta, build_results_table, get_shadow_prices
from pulp import value

from auth_ui import auth_gate
from supabase_client import supabase_authed

from catalog_db import (
    import_foods_from_df, import_requirements_from_df,
    foods_to_df_for_solver, requirements_to_df_for_ui
)

# =========================================================
# AUTH + SUPABASE
# =========================================================
user_id = auth_gate()

session = st.session_state.get("session")
access_token = session.access_token if session else None

if not access_token:
    st.error("Sessão inválida. Faça login novamente.")
    st.stop()

sb_user = supabase_authed(access_token)

menu = st.sidebar.radio("Menu", ["Formular ração", "📚 Cadastros (meus dados)"])
st.success(f"✅ Logado! user_id={user_id}")

# =========================================================
# HELPERS
# =========================================================
def _nut_get(nutr: dict, key: str) -> float:
    if isinstance(nutr, dict) and nutr.get(key) is not None:
        try:
            return float(nutr.get(key))
        except Exception:
            return 0.0
    return 0.0

def _get_req(req_min: dict, key: str) -> float:
    if isinstance(req_min, dict) and key in req_min and req_min[key] is not None:
        try:
            return float(req_min[key])
        except Exception:
            return 0.0
    return 0.0


# =========================================================
# CADASTROS (FOODS + REQUIREMENTS)
# =========================================================
def render_cadastros(sb_user, user_id):
    st.stop()
    st.title("📚 Cadastros (meus dados)")

    tab_foods, tab_reqs = st.tabs(["🍽️ Alimentos", "📌 Exigências"])

    # =====================================================
    # TAB 1: ALIMENTOS
    # =====================================================
    with tab_foods:
        st.subheader("🍽️ Meus Alimentos")

        st.markdown("### ➕ Adicionar alimento")
        with st.form("form_add_food", clear_on_submit=True):
            nome = st.text_input("Nome do alimento", placeholder="Ex.: Milho")
            categoria = st.text_input("Categoria (opcional)", placeholder="Ex.: Energético / Proteico / Aditivo")
            preco = st.number_input("Preço (R$/kg)", min_value=0.0, value=0.0, step=0.01)

            st.caption("Nutrientes (preencha com 0 se não souber)")
            c1, c2, c3 = st.columns(3)
            with c1:
                PB = st.number_input("PB (%)", min_value=0.0, value=0.0, step=0.01, key="food_PB")
                EM = st.number_input("EM", min_value=0.0, value=0.0, step=0.01, key="food_EM")
                Ca = st.number_input("Ca (%)", min_value=0.0, value=0.0, step=0.01, key="food_Ca")
                Na = st.number_input("Na (%)", min_value=0.0, value=0.0, step=0.01, key="food_Na")
            with c2:
                Lisina = st.number_input("Lisina (%)", min_value=0.0, value=0.0, step=0.01, key="food_Lisina")
                MetCis = st.number_input("MetCis (%)", min_value=0.0, value=0.0, step=0.01, key="food_MetCis")
                Treonina = st.number_input("Treonina (%)", min_value=0.0, value=0.0, step=0.01, key="food_Treonina")
                Triptofano = st.number_input("Triptofano (%)", min_value=0.0, value=0.0, step=0.01, key="food_Triptofano")
            with c3:
                Pdig = st.number_input("Pdig (%)", min_value=0.0, value=0.0, step=0.01, key="food_Pdig")
                FB = st.number_input("FB (%)", min_value=0.0, value=0.0, step=0.01, key="food_FB")
                EE = st.number_input("EE (%)", min_value=0.0, value=0.0, step=0.01, key="food_EE")

            submitted_food = st.form_submit_button("Adicionar")

        if submitted_food:
            if not nome.strip():
                st.error("Informe o nome do alimento.")
            else:
                payload = {
                    "user_id": user_id,
                    "nome": nome.strip(),
                    "categoria": categoria.strip() if categoria.strip() else None,
                    "preco": float(preco),
                    "nutrientes": {
                        "PB": float(PB), "EM": float(EM), "Pdig": float(Pdig),
                        "Ca": float(Ca), "Na": float(Na),
                        "Lisina": float(Lisina), "MetCis": float(MetCis),
                        "Treonina": float(Treonina), "Triptofano": float(Triptofano),
                        "FB": float(FB), "EE": float(EE),
                    }
                }
                try:
                    sb_user.table("foods").insert(payload).execute()
                    st.success("Alimento adicionado ✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao inserir alimento: {e}")

        st.markdown("### 📋 Lista de alimentos")

        foods_rows = (
            sb_user.table("foods")
            .select("id,nome,categoria,preco,nutrientes,updated_at")
            .eq("user_id", user_id)
            .order("nome")
            .execute()
            .data
        )
        df_food = pd.DataFrame(foods_rows or [])

        if df_food.empty:
            st.info("Você ainda não cadastrou alimentos.")
        else:
            df_food = df_food[df_food["id"].notna()].copy()
            df_food["id"] = df_food["id"].astype(str)
            df_food["nome"] = df_food["nome"].astype(str)

            st.dataframe(
                df_food[["nome", "categoria", "preco", "updated_at"]],
                use_container_width=True,
                hide_index=True
            )

            st.markdown("### ✏️ Editar alimento")

            food_id_to_label = dict(zip(df_food["id"], df_food["nome"]))

            def on_food_change():
                st.session_state["food_edit_changed"] = True

            food_id = st.selectbox(
                "Selecione um alimento para editar",
                options=list(food_id_to_label.keys()),
                format_func=lambda rid: food_id_to_label.get(rid, rid),
                key="sel_edit_food",
                on_change=on_food_change,
            )

            row = df_food[df_food["id"] == str(food_id)].iloc[0]
            nutr = row["nutrientes"] if isinstance(row["nutrientes"], dict) else {}

            if st.session_state.get("food_edit_prev") != food_id or st.session_state.get("food_edit_changed", False):
                st.session_state["food_edit_prev"] = food_id
                st.session_state["food_edit_changed"] = False

                st.session_state["edit_food_nome"] = str(row.get("nome") or "")
                st.session_state["edit_food_cat"] = str(row.get("categoria") or "")
                st.session_state["edit_food_preco"] = float(row.get("preco") or 0.0)

                st.session_state["edit_food_PB"] = _nut_get(nutr, "PB")
                st.session_state["edit_food_EM"] = _nut_get(nutr, "EM")
                st.session_state["edit_food_Ca"] = _nut_get(nutr, "Ca")
                st.session_state["edit_food_Na"] = _nut_get(nutr, "Na")
                st.session_state["edit_food_Lisina"] = _nut_get(nutr, "Lisina")
                st.session_state["edit_food_MetCis"] = _nut_get(nutr, "MetCis")
                st.session_state["edit_food_Treonina"] = _nut_get(nutr, "Treonina")
                st.session_state["edit_food_Triptofano"] = _nut_get(nutr, "Triptofano")
                st.session_state["edit_food_Pdig"] = _nut_get(nutr, "Pdig")
                st.session_state["edit_food_FB"] = _nut_get(nutr, "FB")
                st.session_state["edit_food_EE"] = _nut_get(nutr, "EE")

            with st.form("form_edit_food"):
                st.text_input("Nome do alimento", key="edit_food_nome")
                st.text_input("Categoria (opcional)", key="edit_food_cat")
                st.number_input("Preço (R$/kg)", min_value=0.0, step=0.01, key="edit_food_preco")

                st.caption("Nutrientes")
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.number_input("PB (%)", step=0.01, key="edit_food_PB")
                    st.number_input("EM", step=0.01, key="edit_food_EM")
                    st.number_input("Ca (%)", step=0.01, key="edit_food_Ca")
                    st.number_input("Na (%)", step=0.01, key="edit_food_Na")
                with c2:
                    st.number_input("Lisina (%)", step=0.01, key="edit_food_Lisina")
                    st.number_input("MetCis (%)", step=0.01, key="edit_food_MetCis")
                    st.number_input("Treonina (%)", step=0.01, key="edit_food_Treonina")
                    st.number_input("Triptofano (%)", step=0.01, key="edit_food_Triptofano")
                with c3:
                    st.number_input("Pdig (%)", step=0.01, key="edit_food_Pdig")
                    st.number_input("FB (%)", step=0.01, key="edit_food_FB")
                    st.number_input("EE (%)", step=0.01, key="edit_food_EE")

                colA, colB = st.columns(2)
                with colA:
                    btn_save_food = st.form_submit_button("Salvar alterações ✅")
                with colB:
                    btn_delete_food = st.form_submit_button("Excluir alimento 🗑️")

            if btn_save_food:
                nome_e = (st.session_state.get("edit_food_nome") or "").strip()
                if not nome_e:
                    st.error("Nome não pode ficar vazio.")
                else:
                    payload_upd = {
                        "nome": nome_e,
                        "categoria": (st.session_state.get("edit_food_cat") or "").strip() or None,
                        "preco": float(st.session_state.get("edit_food_preco") or 0.0),
                        "nutrientes": {
                            "PB": float(st.session_state.get("edit_food_PB") or 0.0),
                            "EM": float(st.session_state.get("edit_food_EM") or 0.0),
                            "Pdig": float(st.session_state.get("edit_food_Pdig") or 0.0),
                            "Ca": float(st.session_state.get("edit_food_Ca") or 0.0),
                            "Na": float(st.session_state.get("edit_food_Na") or 0.0),
                            "Lisina": float(st.session_state.get("edit_food_Lisina") or 0.0),
                            "MetCis": float(st.session_state.get("edit_food_MetCis") or 0.0),
                            "Treonina": float(st.session_state.get("edit_food_Treonina") or 0.0),
                            "Triptofano": float(st.session_state.get("edit_food_Triptofano") or 0.0),
                            "FB": float(st.session_state.get("edit_food_FB") or 0.0),
                            "EE": float(st.session_state.get("edit_food_EE") or 0.0),
                        }
                    }
                    sb_user.table("foods").update(payload_upd).eq("id", food_id).execute()
                    st.success("Alimento atualizado ✅")
                    st.rerun()

            if btn_delete_food:
                sb_user.table("foods").delete().eq("id", food_id).execute()
                st.success("Alimento excluído ✅")
                st.rerun()

    # =====================================================
    # TAB 2: EXIGÊNCIAS
    # =====================================================
    with tab_reqs:
        st.subheader("📌 Minhas Exigências")

        st.markdown("### ➕ Adicionar exigência")
        with st.form("form_add_req", clear_on_submit=True):
            exigencia_new = st.text_input("Nome do grupo (exigencia)", placeholder="Ex.: Rostagno / NRC / Empresa X")
            fase_new = st.text_input("Fase", placeholder="Ex.: Crescimento 30-50kg")

            c1, c2, c3 = st.columns(3)
            with c1:
                PB = st.number_input("PB mínima (%)", 0.0, step=0.01, key="add_PB")
                EM = st.number_input("EM mínima", 0.0, step=0.01, key="add_EM")
                Pdig = st.number_input("Pdig mínima (%)", 0.0, step=0.01, key="add_Pdig")
            with c2:
                Ca = st.number_input("Ca mínima (%)", 0.0, step=0.01, key="add_Ca")
                Na = st.number_input("Na mínima (%)", 0.0, step=0.01, key="add_Na")
                Lisina = st.number_input("Lisina mínima (%)", 0.0, step=0.01, key="add_Lisina")
            with c3:
                MetCis = st.number_input("MetCis mínima (%)", 0.0, step=0.01, key="add_MetCis")
                Treonina = st.number_input("Treonina mínima (%)", 0.0, step=0.01, key="add_Treonina")
                Triptofano = st.number_input("Triptofano mínima (%)", 0.0, step=0.01, key="add_Triptofano")

            submitted_add = st.form_submit_button("Adicionar exigência")

        if submitted_add:
            if not exigencia_new.strip() or not fase_new.strip():
                st.error("Preencha exigencia e fase.")
            else:
                payload = {
                    "user_id": user_id,
                    "exigencia": exigencia_new.strip(),
                    "fase": fase_new.strip(),
                    "req_min": {
                        "PB": float(PB), "EM": float(EM), "Pdig": float(Pdig),
                        "Ca": float(Ca), "Na": float(Na),
                        "Lisina": float(Lisina), "MetCis": float(MetCis),
                        "Treonina": float(Treonina), "Triptofano": float(Triptofano),
                    },
                }
                sb_user.table("requirements").insert(payload).execute()
                st.success("Exigência adicionada ✅")
                st.rerun()

        st.markdown("### 📋 Lista de exigências")

        req_rows = (
            sb_user.table("requirements")
            .select("id,exigencia,fase,req_min,updated_at")
            .eq("user_id", user_id)
            .order("exigencia")
            .execute()
            .data
        )
        df_req = pd.DataFrame(req_rows or [])

        if df_req.empty:
            st.info("Você ainda não cadastrou exigências.")
        else:
            df_req = df_req[df_req["id"].notna()].copy()
            df_req["id"] = df_req["id"].astype(str)
            df_req["exigencia"] = df_req["exigencia"].astype(str)
            df_req["fase"] = df_req["fase"].astype(str)

            st.markdown("### ✏️ Editar exigência")

            req_id_to_label = dict(zip(df_req["id"], df_req["exigencia"] + " | " + df_req["fase"]))

            def on_req_change():
                st.session_state["req_edit_changed"] = True

            req_id = st.selectbox(
                "Selecione para editar",
                options=list(req_id_to_label.keys()),
                format_func=lambda rid: req_id_to_label.get(rid, rid),
                key="sel_edit_req",
                on_change=on_req_change,
            )

            row = df_req[df_req["id"] == str(req_id)].iloc[0]
            req_min = row["req_min"] if isinstance(row["req_min"], dict) else {}

            if st.session_state.get("req_edit_prev") != req_id or st.session_state.get("req_edit_changed", False):
                st.session_state["req_edit_prev"] = req_id
                st.session_state["req_edit_changed"] = False

                st.session_state["edit_exigencia"] = str(row.get("exigencia") or "")
                st.session_state["edit_fase"] = str(row.get("fase") or "")

                st.session_state["edit_PB"] = _get_req(req_min, "PB")
                st.session_state["edit_EM"] = _get_req(req_min, "EM")
                st.session_state["edit_Pdig"] = _get_req(req_min, "Pdig")
                st.session_state["edit_Ca"] = _get_req(req_min, "Ca")
                st.session_state["edit_Na"] = _get_req(req_min, "Na")
                st.session_state["edit_Lisina"] = _get_req(req_min, "Lisina")
                st.session_state["edit_MetCis"] = _get_req(req_min, "MetCis")
                st.session_state["edit_Treonina"] = _get_req(req_min, "Treonina")
                st.session_state["edit_Triptofano"] = _get_req(req_min, "Triptofano")

            with st.form("form_edit_req"):
                st.text_input("Exigencia", key="edit_exigencia")
                st.text_input("Fase", key="edit_fase")

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.number_input("PB mínima (%)", step=0.01, key="edit_PB")
                    st.number_input("EM mínima", step=0.01, key="edit_EM")
                    st.number_input("Pdig mínima (%)", step=0.01, key="edit_Pdig")
                with c2:
                    st.number_input("Ca mínima (%)", step=0.01, key="edit_Ca")
                    st.number_input("Na mínima (%)", step=0.01, key="edit_Na")
                    st.number_input("Lisina mínima (%)", step=0.01, key="edit_Lisina")
                with c3:
                    st.number_input("MetCis mínima (%)", step=0.01, key="edit_MetCis")
                    st.number_input("Treonina mínima (%)", step=0.01, key="edit_Treonina")
                    st.number_input("Triptofano mínima (%)", step=0.01, key="edit_Triptofano")

                colA, colB = st.columns(2)
                with colA:
                    btn_save = st.form_submit_button("Salvar alterações ✅")
                with colB:
                    btn_delete = st.form_submit_button("Excluir exigência 🗑️")

            if btn_save:
                if not (st.session_state.get("edit_exigencia") or "").strip() or not (st.session_state.get("edit_fase") or "").strip():
                    st.error("Exigencia e fase não podem ficar vazias.")
                else:
                    payload_upd = {
                        "exigencia": (st.session_state.get("edit_exigencia") or "").strip(),
                        "fase": (st.session_state.get("edit_fase") or "").strip(),
                        "req_min": {
                            "PB": float(st.session_state.get("edit_PB") or 0.0),
                            "EM": float(st.session_state.get("edit_EM") or 0.0),
                            "Pdig": float(st.session_state.get("edit_Pdig") or 0.0),
                            "Ca": float(st.session_state.get("edit_Ca") or 0.0),
                            "Na": float(st.session_state.get("edit_Na") or 0.0),
                            "Lisina": float(st.session_state.get("edit_Lisina") or 0.0),
                            "MetCis": float(st.session_state.get("edit_MetCis") or 0.0),
                            "Treonina": float(st.session_state.get("edit_Treonina") or 0.0),
                            "Triptofano": float(st.session_state.get("edit_Triptofano") or 0.0),
                        }
                    }
                    sb_user.table("requirements").update(payload_upd).eq("id", req_id).execute()
                    st.success("Exigência atualizada ✅")
                    st.rerun()

            if btn_delete:
                sb_user.table("requirements").delete().eq("id", req_id).execute()
                st.success("Exigência excluída ✅")
                st.rerun()

# =========================================================
# ROUTER (MENU) ✅
# =========================================================
if menu == "📚 Cadastros (meus dados)":
    render_cadastros(sb_user, user_id)
    st.stop()
# =========================================================
# SEÇÃO FORMULAR (se chegou aqui, menu == "Formular ração")
# =========================================================
st.title("Formulador de Racao (Suinos) - Web")

usar_banco = st.toggle("Usar dados do banco (Supabase)", value=True)

df_food = pd.DataFrame()
df_req = pd.DataFrame()

if usar_banco:
    try:
        foods_rows = (
            sb_user.table("foods")
            .select("*")
            .eq("user_id", user_id)
            .order("nome")
            .execute()
            .data
        )

        req_rows = (
            sb_user.table("requirements")
            .select("*")
            .eq("user_id", user_id)
            .order("exigencia")
            .execute()
            .data
        )

        df_food_db = pd.DataFrame(foods_rows)
        df_req_db  = pd.DataFrame(req_rows)

        if not df_food_db.empty and not df_req_db.empty:
            df_food = foods_to_df_for_solver(df_food_db)
            df_req  = requirements_to_df_for_ui(df_req_db)
            st.success("Dados carregados do banco com sucesso ✅")
        else:
            st.warning("Banco vazio. Envie a planilha para importar e começar.")
            usar_banco = False

    except Exception as e:
        st.warning(f"Não consegui ler do banco agora: {e}")
        usar_banco = False



if not usar_banco:
    arquivo = st.file_uploader(
        "Envie sua planilha .xlsx (abas: 'Alimentos' e 'Exigencias')",
        type=["xlsx"],
        key="uploader_planilha"
    )

    # Só mostra o botão quando a planilha existir
    if arquivo is not None:
        # carrega a planilha
        df_food, df_req = load_planilha(arquivo)

        # botão fica LOGO ABAIXO do upload
        if st.button("Importar planilha para o banco (Supabase)", key="btn_importar_banco"):
            n1 = import_foods_from_df(df_food)
            n2 = import_requirements_from_df(df_req)
            st.success(f"Importado para o banco ✅ Foods: {n1} | Requirements: {n2}")
            st.rerun()
    else:
        st.info("Envie a planilha para começar.")
        st.stop()


col1, col2 = st.columns([2, 1])

if df_req.empty or "Exigencia" not in df_req.columns or "Fase" not in df_req.columns:
    st.error("Exigências não carregadas corretamente. Verifique banco/planilha.")
    st.stop()

# 🔹 Preenche a coluna Exigencia para baixo (planilha vem em blocos)
df_req = df_req.copy()
df_req["Exigencia"] = df_req["Exigencia"].ffill()

with col1:
    # 1️⃣ Escolher o grupo de exigência
    exigencias = df_req["Exigencia"].dropna().unique().tolist()
    exigencia_escolhida = st.selectbox("Escolha o tipo de exigência", exigencias)

    # 2️⃣ Mostrar apenas fases desse grupo
    fases_filtradas = (
        df_req[df_req["Exigencia"] == exigencia_escolhida]["Fase"]
        .dropna()
        .unique()
        .tolist()
    )

    fase = st.selectbox("Escolha a fase (suínos)", fases_filtradas)

with col2:
    st.caption("Energia usada: **EM (Suínos)**")

def get_req_row(df_req: pd.DataFrame, exigencia: str, fase: str) -> dict:
    row = df_req[(df_req["Exigencia"] == exigencia) & (df_req["Fase"] == fase)]
    if row.empty:
        raise ValueError("Exigência não encontrada para essa combinação.")
    return row.iloc[0].to_dict()


# 🔹 Agora a exigência é buscada por Exigencia + Fase
req_min = get_req_row(df_req, exigencia_escolhida, fase)




st.subheader("1) Selecione ingredientes + defina Min%/Max%")
tabela = build_ui_table(df_food)

edited = st.data_editor(
    tabela,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Usar": st.column_config.CheckboxColumn("Usar"),
        "Min_%": st.column_config.NumberColumn("Min_%", min_value=0.0, max_value=100.0, step=0.001, format="%.3f"),
        "Max_%": st.column_config.NumberColumn("Max_%", min_value=0.0, max_value=100.0, step=0.001, format="%.3f"),
        "Preco": st.column_config.NumberColumn("Preco (R$/kg)", step=0.01, format="%.2f"),
    },
)

st.subheader("2) Limites opcionais")
c3, c4 = st.columns(2)
with c3:
    fb_max = st.number_input("FB máximo (%) [opcional]", min_value=0.0, max_value=30.0, value=0.0, step=0.1)
    usar_fb_max = st.checkbox("Aplicar FB máximo", value=False)
with c4:
    ee_max = st.number_input("EE máximo (%) [opcional]", min_value=0.0, max_value=30.0, value=0.0, step=0.1)
    usar_ee_max = st.checkbox("Aplicar EE máximo", value=False)

fb_lim = fb_max if usar_fb_max else None
ee_lim = ee_max if usar_ee_max else None
st.subheader("Dados do Relatório")

r1, r2, r3 = st.columns(3)
with r1:
    granja = st.text_input("Granja / Empresa", value="Minha Granja")
with r2:
    produtor = st.text_input("Produtor / Responsável", value="")
with r3:
    nutricionista = st.text_input("Nutricionista / Técnico", value="")

r4, r5 = st.columns([1, 2])
with r4:
    numero_formula = st.text_input("Nº da fórmula (opcional)", value="")
with r5:
    lote_obs = st.text_input("Lote / Observação curta (opcional)", value="")

observacoes = st.text_area("Observações (opcional)", value="", height=90)

codigo_formula = numero_formula.strip()
if not codigo_formula:
    codigo_formula = datetime.now().strftime("FORM-%Y%m%d-%H%M%S")


st.subheader("3) Formular")
if st.button("Formular (mínimo custo)"):
    df_sel = edited[edited["Usar"] == True].copy()

    if df_sel.empty:
        st.error("Selecione pelo menos 1 ingrediente.")
        st.stop()

    if (df_sel["Min_%"] > df_sel["Max_%"]).any():
        st.error("Existe ingrediente com Min_% maior que Max_%. Corrija.")
        st.stop()

    if df_sel["Max_%"].sum() < 100:
        st.error("Soma dos Max_% < 100. Não dá para fechar 100% da dieta.")
        st.stop()

    if df_sel["Min_%"].sum() > 100:
        st.error("Soma dos Min_% > 100. Não dá para fechar 100% da dieta.")
        st.stop()

    prob, x, status = solve_lp(df_sel, req_min, fb_max=fb_lim, ee_max=ee_lim)

    st.write("**Status:**", status)
    if status != "Optimal":
        st.error("Inviável: não existe solução com esses ingredientes/limites/exigências.")
        st.stop()

    # resultados
    df_res = build_results_table(df_sel, x)
    custo = float(value(prob.objective))

    st.success(f"Custo (R$/kg): {custo:.4f}  |  Custo (R$/ton): {custo*1000:.2f}")
    st.subheader("Inclusão de ingredientes")
    st.dataframe(df_res, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("📊 Análise de Sensibilidade — Preço-Sombra")

    df_shadow = get_shadow_prices(prob)
    st.dataframe(df_shadow, use_container_width=True)
    # nutrientes
    st.subheader("Nutrientes da dieta (obtido vs exigido)")
    dieta = calc_dieta(df_sel, x)

    from solver import get_reduced_costs_manual

    st.subheader("📉 Análise de Sensibilidade — Reduced Cost (ingredientes)")
    df_rc = get_reduced_costs_manual(prob, df_sel, x, req_min, fb_max=fb_lim, ee_max=ee_lim)
    st.dataframe(df_rc, use_container_width=True, hide_index=True)

    eps = 1e-6
    linhas = []
    for nut, obt in dieta.items():
        exg = req_min.get(nut, None)
        atende = "-"
        if exg is not None:
            atende = "OK" if (float(obt) + eps >= float(exg)) else "NAO"
        linhas.append({
            "Nutriente": nut,
            "Obtido": round(float(obt), 4),
            "Exigido_min": None if exg is None else round(float(exg), 4),
            "Atende?": atende
        })

    # acrescenta checagem de máximos opcionais
    if fb_lim is not None:
        ok = (dieta.get("FB", 0.0) <= fb_lim + eps)
        linhas.append({"Nutriente":"FB_max","Obtido":round(float(dieta.get("FB",0.0)),4),
                       "Exigido_min":round(float(fb_lim),4),"Atende?":("OK" if ok else "NAO")})
    if ee_lim is not None:
        ok = (dieta.get("EE", 0.0) <= ee_lim + eps)
        linhas.append({"Nutriente":"EE_max","Obtido":round(float(dieta.get("EE",0.0)),4),
                       "Exigido_min":round(float(ee_lim),4),"Atende?":("OK" if ok else "NAO")})

    df_nut = pd.DataFrame(linhas)
    df_nut = df_nut.where(pd.notnull(df_nut), None)  # ✅ troca NaN por None
    st.write("DEBUG exigencia_escolhida:", exigencia_escolhida)


      # -------- ( payload ) --------
    payload = {
        "codigo": codigo_formula,  
        "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "exigencia": exigencia_escolhida,
        "fase": fase,
        "custo_R_kg": round(custo, 6),
        "custo_R_ton": round(custo * 1000, 2),

        "fb_max": fb_lim if fb_lim is not None else None,
        "ee_max": ee_lim if ee_lim is not None else None,

        # dieta final
        "ingredientes": df_res.to_dict(orient="records"),
        "nutrientes": df_nut.to_dict(orient="records"),

        # config usada
        "ingredientes_config": edited[["Alimentos", "Usar", "Min_%", "Max_%", "Preco"]].to_dict(orient="records"),

        # dados de identificação do relatório
        "relatorio": {
            "granja": granja,
            "produtor": produtor,
            "nutricionista": nutricionista,
            "numero_formula": numero_formula,
            "lote_obs": lote_obs,
            "observacoes": observacoes,

        },

        # exigências mínimas usadas
        "exigencias_min": req_min,
    }

    # ✅ habilita salvar/relatório depois de formular
    st.session_state["last_payload"] = payload
    st.session_state["last_df_res"] = df_res
    st.success("Formulação pronta! Agora você pode salvar no histórico e baixar o relatório abaixo.")


    st.divider()
st.subheader("Salvar / Relatório")

if "last_payload" not in st.session_state or "last_df_res" not in st.session_state:
    st.info("Faça uma formulação para habilitar salvar e gerar relatório.")
else:
    payload_last = st.session_state["last_payload"]
    df_last = st.session_state["last_df_res"]

    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("Salvar no histórico", key="btn_salvar_historico"):
            meta = save_run(payload_last, df_last)
            st.session_state["last_saved_id"] = meta.get("id", "")
            st.success(f"Salvo no histórico! ID: {st.session_state['last_saved_id']}")
            st.rerun()

    with c2:
        html = build_report_html(payload_last)
        st.download_button(
            "Baixar relatório (HTML)",
            data=html.encode("utf-8"),
            file_name="relatorio_formulacao.html",
            mime="text/html",
            key="btn_baixar_html",
        )

    with c3:
        try:
            pdf_bytes = make_pdf_report(payload_last)
            st.download_button(
                "Baixar PDF",
                data=pdf_bytes,
                file_name="relatorio_formulacao.pdf",
                mime="application/pdf",
                key="btn_baixar_pdf",
            )
        except Exception:
            st.caption("PDF: instale reportlab (python -m pip install reportlab)")



st.divider()
st.header("Histórico")

hist = list_runs()

if hist.empty:
    st.info("Nenhuma formulação salva ainda.")
else:
    # ✅ cria um "código visível" (prioridade: coluna codigo > payload.codigo > id curto)
    def _codigo_vis(row):
        # 1) coluna codigo (se existir)
        cod = row.get("codigo", None)
        if cod:
            return str(cod)

        # 2) tenta ler de dentro do payload (se payload veio no list_runs)
        payload = row.get("payload", None)
        if isinstance(payload, dict):
            cod2 = payload.get("codigo")
            if cod2:
                return str(cod2)

        # 3) fallback: id curto
        return str(row["id"])[:8]

    # se list_runs não trouxe payload, funciona igual (vai cair no id curto)
    hist = hist.copy()
    hist["codigo_vis"] = hist.apply(_codigo_vis, axis=1)

    # ✅ tabela bonita (sem coluna payload gigante)
    cols_show = ["codigo_vis", "data_hora", "fase", "custo_R_kg"]
    st.dataframe(hist[cols_show], use_container_width=True, hide_index=True)

    # ✅ selectbox: por baixo usa id, mas mostra codigo + data
    id_to_label = {
        row["id"]: f"{row['codigo_vis']}  |  {row['data_hora']}  |  {row['fase']}"
        for _, row in hist.iterrows()
    }

    run_id = st.selectbox(
        "Escolha uma formulação para reabrir",
        options=hist["id"].tolist(),
        format_func=lambda rid: id_to_label.get(rid, rid),
    )

    if st.button("Reabrir relatório"):
        run = load_run(run_id)
        html = build_report_html(run)
        components.html(html, height=900, scrolling=True)


        st.download_button(
            "Baixar relatório reaberto (HTML)",
            data=html.encode("utf-8"),
            file_name=f"relatorio_{run_id}.html",
            mime="text/html",

        )
with st.expander("Diagnóstico (opcional)"):
    from pathlib import Path
    from history import HIST_DIR

    st.caption(f"📁 Pasta do histórico: {HIST_DIR}")
    st.caption(f"Arquivos .json encontrados: {len(list(Path(HIST_DIR).glob('*.json')))}")
