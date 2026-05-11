# -*- coding: utf-8 -*-
import streamlit as st

st.set_page_config(page_title="Formulador de Ração - Suínos", layout="wide")

import pandas as pd
from datetime import datetime
import streamlit.components.v1 as components

from history_db import save_run, list_runs, load_run
from reporting import build_report_html, make_pdf_report
from io_excel import load_planilha, build_ui_table
from solver import (
    solve_lp, solve_lp_relaxado, calc_dieta, build_results_table,
    get_shadow_prices, get_reduced_costs_manual,
)
from pulp import value

from auth_ui import auth_gate
from supabase_client import supabase_authed

from catalog_db import (
    import_foods_from_df, import_requirements_from_df,
    foods_to_df_for_solver, requirements_to_df_for_ui,
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


# =========================================================
# ESTADO GLOBAL DE NAVEGAÇÃO
# =========================================================
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "home"

if "form_step" not in st.session_state:
    st.session_state["form_step"] = 1

if "form_data" not in st.session_state:
    st.session_state["form_data"] = {}


def go_to(page: str):
    st.session_state["current_page"] = page


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


def _fetch_foods_df():
    rows = (
        sb_user.table("foods")
        .select("*")
        .eq("user_id", user_id)
        .order("nome")
        .execute()
        .data
    )
    return pd.DataFrame(rows or [])


def _fetch_reqs_df():
    rows = (
        sb_user.table("requirements")
        .select("*")
        .eq("user_id", user_id)
        .order("exigencia")
        .execute()
        .data
    )
    return pd.DataFrame(rows or [])


# =========================================================
# SIDEBAR (NAVEGAÇÃO)
# =========================================================
def render_sidebar():
    st.sidebar.markdown("## 🌽 Formulador")
    st.sidebar.caption("Suínos — mínimo custo")
    st.sidebar.divider()

    pages = [
        ("home",       "🏠 Início"),
        ("formular",   "🧪 Formular Ração"),
        ("cadastros",  "📚 Cadastros"),
        ("historico",  "📂 Histórico"),
        ("importar",   "⬆️ Importar Planilha"),
    ]

    for key, label in pages:
        is_active = st.session_state["current_page"] == key
        btn_label = ("➤ " + label) if is_active else label
        if st.sidebar.button(btn_label, key=f"nav_{key}", use_container_width=True):
            if key == "formular":
                st.session_state["form_step"] = 1
            go_to(key)
            st.rerun()

    st.sidebar.divider()
    st.sidebar.caption(f"👤 {st.session_state.get('user').email if st.session_state.get('user') else ''}")


# =========================================================
# HOME
# =========================================================
def render_home():
    st.title("🌽 Formulador de Ração — Suínos")
    st.caption("Mínimo custo · Análise de sensibilidade · Relatório HTML/PDF")

    # contadores rápidos
    try:
        n_foods = len(_fetch_foods_df())
    except Exception:
        n_foods = 0
    try:
        n_reqs = len(_fetch_reqs_df())
    except Exception:
        n_reqs = 0
    try:
        n_runs = len(list_runs())
    except Exception:
        n_runs = 0

    m1, m2, m3 = st.columns(3)
    m1.metric("🍽️ Alimentos cadastrados", n_foods)
    m2.metric("📌 Exigências cadastradas", n_reqs)
    m3.metric("📂 Formulações salvas", n_runs)

    st.divider()
    st.subheader("O que você quer fazer?")

    c1, c2 = st.columns(2)

    with c1:
        with st.container(border=True):
            st.markdown("### 🧪 Formular Ração")
            st.caption(
                "Wizard guiado: escolha categoria + fase, depois alimentos, "
                "depois dados do relatório, e por fim calcule o custo mínimo."
            )
            if st.button("Começar formulação", key="home_to_form", use_container_width=True):
                st.session_state["form_step"] = 1
                go_to("formular")
                st.rerun()

        with st.container(border=True):
            st.markdown("### 📂 Histórico")
            st.caption("Reabrir formulações já salvas e baixar o relatório.")
            if st.button("Abrir histórico", key="home_to_hist", use_container_width=True):
                go_to("historico")
                st.rerun()

    with c2:
        with st.container(border=True):
            st.markdown("### 📚 Cadastros")
            st.caption("Gerencie seus alimentos e exigências (mínimos por fase).")
            if st.button("Abrir cadastros", key="home_to_cad", use_container_width=True):
                go_to("cadastros")
                st.rerun()

        with st.container(border=True):
            st.markdown("### ⬆️ Importar Planilha")
            st.caption(
                "Envie um `.xlsx` com as abas **Alimentos** e **Exigencias** "
                "para popular seu banco de uma vez."
            )
            if st.button("Importar planilha", key="home_to_imp", use_container_width=True):
                go_to("importar")
                st.rerun()


# =========================================================
# CADASTROS
# =========================================================
def render_cadastros():
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
                    },
                }
                try:
                    sb_user.table("foods").insert(payload).execute()
                    st.success("Alimento adicionado ✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao inserir alimento: {e}")

        st.markdown("### 📋 Lista de alimentos")

        df_food = _fetch_foods_df()

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
                        },
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

        df_req = _fetch_reqs_df()

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
                        },
                    }
                    sb_user.table("requirements").update(payload_upd).eq("id", req_id).execute()
                    st.success("Exigência atualizada ✅")
                    st.rerun()

            if btn_delete:
                sb_user.table("requirements").delete().eq("id", req_id).execute()
                st.success("Exigência excluída ✅")
                st.rerun()


# =========================================================
# IMPORTAR PLANILHA
# =========================================================
def render_importar():
    st.title("⬆️ Importar Planilha")
    st.caption(
        "Envie um arquivo `.xlsx` com as abas **Alimentos** e **Exigencias** "
        "para popular o banco de uma só vez."
    )

    arquivo = st.file_uploader(
        "Envie sua planilha .xlsx",
        type=["xlsx"],
        key="uploader_planilha_page",
    )

    if arquivo is None:
        st.info("Aguardando upload da planilha…")
        return

    try:
        df_food, df_req = load_planilha(arquivo)
    except Exception as e:
        st.error(f"Não consegui ler a planilha: {e}")
        return

    st.success("Planilha lida com sucesso. Confira abaixo antes de importar.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Alimentos**")
        st.dataframe(df_food, use_container_width=True, hide_index=True)
    with c2:
        st.markdown("**Exigências**")
        st.dataframe(df_req, use_container_width=True, hide_index=True)

    if st.button("Importar para o banco (Supabase)", type="primary", key="btn_importar_banco_page"):
        try:
            n1 = import_foods_from_df(df_food)
            n2 = import_requirements_from_df(df_req)
            st.success(f"Importado para o banco ✅ Foods: {n1} | Requirements: {n2}")
        except Exception as e:
            st.error(f"Falha na importação: {e}")


# =========================================================
# HISTÓRICO
# =========================================================
def render_historico():
    st.title("📂 Histórico de Formulações")

    try:
        hist = list_runs()
    except Exception as e:
        st.error(f"Não consegui ler o histórico: {e}")
        return

    if hist.empty:
        st.info("Nenhuma formulação salva ainda.")
        return

    def _codigo_vis(row):
        cod = row.get("codigo", None)
        if cod:
            return str(cod)
        payload = row.get("payload", None)
        if isinstance(payload, dict):
            cod2 = payload.get("codigo")
            if cod2:
                return str(cod2)
        return str(row["id"])[:8]

    hist = hist.copy()
    hist["codigo_vis"] = hist.apply(_codigo_vis, axis=1)

    cols_show = ["codigo_vis", "data_hora", "fase", "custo_R_kg"]
    st.dataframe(hist[cols_show], use_container_width=True, hide_index=True)

    id_to_label = {
        row["id"]: f"{row['codigo_vis']}  |  {row['data_hora']}  |  {row['fase']}"
        for _, row in hist.iterrows()
    }

    run_id = st.selectbox(
        "Escolha uma formulação para reabrir",
        options=hist["id"].tolist(),
        format_func=lambda rid: id_to_label.get(rid, rid),
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Reabrir relatório", key="btn_reabrir_hist"):
            run = load_run(run_id)
            html = build_report_html(run)
            components.html(html, height=900, scrolling=True)
            st.download_button(
                "Baixar relatório reaberto (HTML)",
                data=html.encode("utf-8"),
                file_name=f"relatorio_{run_id}.html",
                mime="text/html",
                key=f"dl_html_{run_id}",
            )

    with c2:
        try:
            from pathlib import Path
            from history import HIST_DIR
            with st.expander("Diagnóstico (opcional)"):
                st.caption(f"📁 Pasta do histórico: {HIST_DIR}")
                st.caption(f"Arquivos .json encontrados: {len(list(Path(HIST_DIR).glob('*.json')))}")
        except Exception:
            pass


# =========================================================
# FORMULAR (WIZARD DE 4 ETAPAS)
# =========================================================
def _load_data_for_form():
    """Carrega df_food e df_req do banco; retorna (df_food, df_req, ok)."""
    df_food = pd.DataFrame()
    df_req = pd.DataFrame()

    try:
        df_food_db = _fetch_foods_df()
        df_req_db = _fetch_reqs_df()

        if not df_food_db.empty and not df_req_db.empty:
            df_food = foods_to_df_for_solver(df_food_db)
            df_req = requirements_to_df_for_ui(df_req_db)
            return df_food, df_req, True
    except Exception as e:
        st.error(f"Não consegui ler do banco: {e}")
        return df_food, df_req, False

    return df_food, df_req, False


def _step_header(current: int):
    """Mostra um indicador visual das 4 etapas."""
    steps = [
        (1, "Categoria + Fase"),
        (2, "Alimentos"),
        (3, "Dados do Relatório"),
        (4, "Calcular"),
    ]
    cols = st.columns(len(steps))
    for col, (n, label) in zip(cols, steps):
        marker = "🟢" if n < current else ("🔵" if n == current else "⚪")
        col.markdown(f"{marker} **Etapa {n}** — {label}")
    st.divider()


def render_form_step1(df_req: pd.DataFrame):
    st.subheader("Etapa 1 — Categoria animal + Fase")
    st.caption(
        "Escolha a categoria (fonte da exigência: Rostagno, NRC, etc.) e a fase. "
        "Os mínimos da fase aparecem logo abaixo."
    )

    df_req = df_req.copy()
    df_req["Exigencia"] = df_req["Exigencia"].ffill()

    exigencias = df_req["Exigencia"].dropna().unique().tolist()
    if not exigencias:
        st.error("Nenhuma exigência cadastrada. Cadastre em **Cadastros** ou **Importar Planilha**.")
        return

    fd = st.session_state["form_data"]
    default_ex = fd.get("exigencia") if fd.get("exigencia") in exigencias else exigencias[0]

    c1, c2 = st.columns(2)
    with c1:
        exigencia_escolhida = st.selectbox(
            "Categoria (Exigência)",
            exigencias,
            index=exigencias.index(default_ex),
            key="step1_exigencia",
        )
    with c2:
        fases_filtradas = (
            df_req[df_req["Exigencia"] == exigencia_escolhida]["Fase"]
            .dropna().unique().tolist()
        )
        if not fases_filtradas:
            st.error("Não há fases para essa categoria.")
            return
        default_fase = fd.get("fase") if fd.get("fase") in fases_filtradas else fases_filtradas[0]
        fase = st.selectbox(
            "Fase",
            fases_filtradas,
            index=fases_filtradas.index(default_fase),
            key="step1_fase",
        )

    # busca req_min para a combinação
    linha = df_req[(df_req["Exigencia"] == exigencia_escolhida) & (df_req["Fase"] == fase)]
    if linha.empty:
        st.error("Exigência não encontrada para essa combinação.")
        return
    req_min = linha.iloc[0].to_dict()

    # exibe exigências em tabela editável
    st.markdown("#### 📌 Mínimos exigidos para a fase selecionada")
    st.caption("Você pode ajustar os valores diretamente na tabela antes de avançar.")
    nutrientes_chaves = ["PB", "EM", "Pdig", "Ca", "Na", "Lisina", "MetCis", "Treonina", "Triptofano"]
    rotulos = {
        "PB": "PB (%)",
        "EM": "EM (kcal/kg)",
        "Pdig": "P digestível (%)",
        "Ca": "Ca (%)",
        "Na": "Na (%)",
        "Lisina": "Lisina (%)",
        "MetCis": "Met+Cis (%)",
        "Treonina": "Treonina (%)",
        "Triptofano": "Triptofano (%)",
    }

    saved_req = fd.get("req_min") if (
        fd.get("exigencia") == exigencia_escolhida and fd.get("fase") == fase
    ) else None

    linhas_min = []
    for k in nutrientes_chaves:
        if saved_req is not None and k in saved_req and saved_req[k] is not None:
            valor = float(saved_req[k])
        else:
            v = req_min.get(k, None)
            valor = 0.0 if (v is None or (isinstance(v, float) and pd.isna(v))) else float(v)
        linhas_min.append({"Nutriente": rotulos[k], "Mínimo": valor})

    df_min_edit = pd.DataFrame(linhas_min)

    edited_min = st.data_editor(
        df_min_edit,
        use_container_width=True,
        hide_index=True,
        disabled=["Nutriente"],
        column_config={
            "Nutriente": st.column_config.TextColumn("Nutriente"),
            "Mínimo": st.column_config.NumberColumn(
                "Mínimo", min_value=0.0, step=0.001, format="%.3f"
            ),
        },
        key=f"step1_req_editor__{exigencia_escolhida}__{fase}",
    )

    # navegação
    st.divider()
    nav_l, nav_r = st.columns([1, 1])
    with nav_r:
        if st.button("Avançar →", type="primary", use_container_width=True, key="step1_next"):
            rotulo_to_chave = {v: k for k, v in rotulos.items()}
            req_min_editado = {}
            for _, row in edited_min.iterrows():
                chave = rotulo_to_chave.get(str(row["Nutriente"]))
                if chave is None:
                    continue
                v = row["Mínimo"]
                req_min_editado[chave] = (
                    None if (v is None or (isinstance(v, float) and pd.isna(v))) else float(v)
                )

            st.session_state["form_data"]["exigencia"] = exigencia_escolhida
            st.session_state["form_data"]["fase"] = fase
            st.session_state["form_data"]["req_min"] = req_min_editado
            st.session_state["form_step"] = 2
            st.rerun()


def render_form_step2(df_food: pd.DataFrame):
    st.subheader("Etapa 2 — Alimentos e limites")
    st.caption("Selecione os ingredientes, defina Min%/Max% e (opcionalmente) limites de FB/EE.")

    if df_food.empty:
        st.error("Nenhum alimento cadastrado. Vá em **Cadastros** ou **Importar Planilha**.")
        return

    fd = st.session_state["form_data"]
    saved_edited = fd.get("edited")

    if saved_edited is not None and not saved_edited.empty:
        # Re-popula a tabela com edição prévia, mas garante novos alimentos do banco
        tabela = build_ui_table(df_food)
        # Faz merge pelo nome
        tabela = tabela.merge(
            saved_edited[["Alimentos", "Usar", "Min_%", "Max_%"]].rename(
                columns={"Usar": "Usar_p", "Min_%": "Min_p", "Max_%": "Max_p"}
            ),
            on="Alimentos",
            how="left",
        )
        tabela["Usar"] = tabela["Usar_p"].where(tabela["Usar_p"].notna(), tabela["Usar"])
        tabela["Min_%"] = tabela["Min_p"].where(tabela["Min_p"].notna(), tabela["Min_%"])
        tabela["Max_%"] = tabela["Max_p"].where(tabela["Max_p"].notna(), tabela["Max_%"])
        tabela = tabela.drop(columns=["Usar_p", "Min_p", "Max_p"])
    else:
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
        key="step2_editor",
    )

    st.markdown("#### Limites opcionais")
    c1, c2 = st.columns(2)
    with c1:
        fb_max = st.number_input(
            "FB máximo (%) [opcional]",
            min_value=0.0, max_value=30.0,
            value=float(fd.get("fb_max") or 0.0),
            step=0.1,
            key="step2_fb_max",
        )
        usar_fb_max = st.checkbox("Aplicar FB máximo", value=bool(fd.get("usar_fb_max", False)), key="step2_use_fb")
    with c2:
        ee_max = st.number_input(
            "EE máximo (%) [opcional]",
            min_value=0.0, max_value=30.0,
            value=float(fd.get("ee_max") or 0.0),
            step=0.1,
            key="step2_ee_max",
        )
        usar_ee_max = st.checkbox("Aplicar EE máximo", value=bool(fd.get("usar_ee_max", False)), key="step2_use_ee")

    st.divider()
    nav_l, _, nav_r = st.columns([1, 2, 1])
    with nav_l:
        if st.button("← Voltar", use_container_width=True, key="step2_back"):
            st.session_state["form_step"] = 1
            st.rerun()
    with nav_r:
        if st.button("Avançar →", type="primary", use_container_width=True, key="step2_next"):
            df_sel = edited[edited["Usar"] == True].copy()
            if df_sel.empty:
                st.error("Selecione pelo menos 1 ingrediente.")
                return
            if (df_sel["Min_%"] > df_sel["Max_%"]).any():
                st.error("Existe ingrediente com Min_% maior que Max_%. Corrija.")
                return
            if df_sel["Max_%"].sum() < 100:
                st.error("Soma dos Max_% < 100. Não dá para fechar 100% da dieta.")
                return
            if df_sel["Min_%"].sum() > 100:
                st.error("Soma dos Min_% > 100. Não dá para fechar 100% da dieta.")
                return

            fd["edited"] = edited.copy()
            fd["fb_max"] = float(fb_max)
            fd["ee_max"] = float(ee_max)
            fd["usar_fb_max"] = bool(usar_fb_max)
            fd["usar_ee_max"] = bool(usar_ee_max)
            fd["fb_lim"] = float(fb_max) if usar_fb_max else None
            fd["ee_lim"] = float(ee_max) if usar_ee_max else None

            st.session_state["form_step"] = 3
            st.rerun()


def render_form_step3():
    st.subheader("Etapa 3 — Dados do Relatório")
    st.caption("Preenchimento opcional para personalizar o relatório.")

    fd = st.session_state["form_data"]

    r1, r2, r3 = st.columns(3)
    with r1:
        granja = st.text_input("Granja / Empresa", value=fd.get("granja", "Minha Granja"), key="step3_granja")
    with r2:
        produtor = st.text_input("Produtor / Responsável", value=fd.get("produtor", ""), key="step3_produtor")
    with r3:
        nutricionista = st.text_input("Nutricionista / Técnico", value=fd.get("nutricionista", ""), key="step3_nutri")

    r4, r5 = st.columns([1, 2])
    with r4:
        numero_formula = st.text_input("Nº da fórmula (opcional)", value=fd.get("numero_formula", ""), key="step3_numero")
    with r5:
        lote_obs = st.text_input("Lote / Observação curta (opcional)", value=fd.get("lote_obs", ""), key="step3_lote")

    observacoes = st.text_area("Observações (opcional)", value=fd.get("observacoes", ""), height=90, key="step3_obs")

    st.divider()
    nav_l, _, nav_r = st.columns([1, 2, 1])
    with nav_l:
        if st.button("← Voltar", use_container_width=True, key="step3_back"):
            st.session_state["form_step"] = 2
            st.rerun()
    with nav_r:
        if st.button("Avançar →", type="primary", use_container_width=True, key="step3_next"):
            fd["granja"] = granja
            fd["produtor"] = produtor
            fd["nutricionista"] = nutricionista
            fd["numero_formula"] = numero_formula
            fd["lote_obs"] = lote_obs
            fd["observacoes"] = observacoes
            st.session_state["form_step"] = 4
            st.rerun()


def _executar_calculo():
    """Roda o solver com os dados do form_data e popula last_payload/last_df_res."""
    fd = st.session_state["form_data"]
    edited = fd["edited"]
    req_min = fd["req_min"]
    fb_lim = fd.get("fb_lim")
    ee_lim = fd.get("ee_lim")

    df_sel = edited[edited["Usar"] == True].copy()

    prob, x, status = solve_lp(df_sel, req_min, fb_max=fb_lim, ee_max=ee_lim)
    relaxado = False

    if status != "Optimal":
        # Fallback: refaz com slacks para mostrar a melhor dieta possível
        # e indicar quais exigências ficaram fora.
        prob, x, status, _slacks = solve_lp_relaxado(
            df_sel, req_min, fb_max=fb_lim, ee_max=ee_lim
        )
        relaxado = True
        if status != "Optimal":
            return False, status, None, None, None, None, None

    df_res = build_results_table(df_sel, x)
    dieta = calc_dieta(df_sel, x)

    # Custo real da dieta (sem penalidades de slack do relaxado)
    custo = sum(
        (value(x[n]) or 0.0)
        * float(df_sel.loc[df_sel["Alimentos"] == n, "Preco"].iloc[0])
        for n in x
    ) / 100.0

    if relaxado:
        df_shadow = pd.DataFrame()
        df_rc = pd.DataFrame()
    else:
        df_shadow = get_shadow_prices(prob)
        df_rc = get_reduced_costs_manual(prob, df_sel, x, req_min, fb_max=fb_lim, ee_max=ee_lim)

    eps = 1e-6
    linhas = []
    for nut, obt in dieta.items():
        exg = req_min.get(nut, None)
        atende = "-"
        falta = None
        if exg is not None:
            atende = "OK" if (float(obt) + eps >= float(exg)) else "NAO"
            falta = max(0.0, float(exg) - float(obt))
        linhas.append({
            "Nutriente": nut,
            "Obtido": round(float(obt), 4),
            "Exigido_min": None if exg is None else round(float(exg), 4),
            "Falta": None if falta is None else round(float(falta), 4),
            "Atende?": atende,
        })

    if fb_lim is not None:
        excesso = max(0.0, float(dieta.get("FB", 0.0)) - float(fb_lim))
        ok = excesso <= eps
        linhas.append({
            "Nutriente": "FB_max",
            "Obtido": round(float(dieta.get("FB", 0.0)), 4),
            "Exigido_min": round(float(fb_lim), 4),
            "Falta": round(float(excesso), 4),
            "Atende?": ("OK" if ok else "NAO"),
        })
    if ee_lim is not None:
        excesso = max(0.0, float(dieta.get("EE", 0.0)) - float(ee_lim))
        ok = excesso <= eps
        linhas.append({
            "Nutriente": "EE_max",
            "Obtido": round(float(dieta.get("EE", 0.0)), 4),
            "Exigido_min": round(float(ee_lim), 4),
            "Falta": round(float(excesso), 4),
            "Atende?": ("OK" if ok else "NAO"),
        })

    df_nut = pd.DataFrame(linhas)
    df_nut = df_nut.where(pd.notnull(df_nut), None)

    codigo_formula = (fd.get("numero_formula") or "").strip()
    if not codigo_formula:
        codigo_formula = datetime.now().strftime("FORM-%Y%m%d-%H%M%S")

    payload = {
        "codigo": codigo_formula,
        "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "exigencia": fd.get("exigencia", ""),
        "fase": fd.get("fase", ""),
        "custo_R_kg": round(custo, 6),
        "custo_R_ton": round(custo * 1000, 2),
        "relaxado": bool(relaxado),

        "fb_max": fb_lim if fb_lim is not None else None,
        "ee_max": ee_lim if ee_lim is not None else None,

        "ingredientes": df_res.to_dict(orient="records"),
        "nutrientes": df_nut.to_dict(orient="records"),

        "ingredientes_config": edited[["Alimentos", "Usar", "Min_%", "Max_%", "Preco"]].to_dict(orient="records"),

        "relatorio": {
            "granja": fd.get("granja", ""),
            "produtor": fd.get("produtor", ""),
            "nutricionista": fd.get("nutricionista", ""),
            "numero_formula": fd.get("numero_formula", ""),
            "lote_obs": fd.get("lote_obs", ""),
            "observacoes": fd.get("observacoes", ""),
        },
        "exigencias_min": req_min,
    }

    st.session_state["last_payload"] = payload
    st.session_state["last_df_res"] = df_res
    st.session_state["last_df_shadow"] = df_shadow
    st.session_state["last_df_rc"] = df_rc
    st.session_state["last_df_nut"] = df_nut
    st.session_state["last_custo"] = custo

    return True, status, payload, df_res, df_shadow, df_rc, df_nut


def render_form_step4():
    st.subheader("Etapa 4 — Calcular")

    fd = st.session_state["form_data"]
    with st.container(border=True):
        st.markdown("**Resumo da formulação**")
        c1, c2 = st.columns(2)
        c1.write(f"**Categoria:** {fd.get('exigencia', '—')}")
        c2.write(f"**Fase:** {fd.get('fase', '—')}")
        c3, c4 = st.columns(2)
        c3.write(f"**FB máx:** {fd.get('fb_lim') if fd.get('fb_lim') is not None else '—'}")
        c4.write(f"**EE máx:** {fd.get('ee_lim') if fd.get('ee_lim') is not None else '—'}")
        n_ing = 0
        if fd.get("edited") is not None:
            n_ing = int((fd["edited"]["Usar"] == True).sum())
        st.write(f"**Ingredientes selecionados:** {n_ing}")

    st.divider()
    nav_l, _, nav_r = st.columns([1, 2, 1])
    with nav_l:
        if st.button("← Voltar", use_container_width=True, key="step4_back"):
            st.session_state["form_step"] = 3
            st.rerun()
    with nav_r:
        if st.button("⚡ Calcular agora", type="primary", use_container_width=True, key="step4_run"):
            ok, status, payload_calc, *_ = _executar_calculo()
            if not ok:
                st.error(
                    "Inviável estruturalmente: verifique a soma dos Min_%/Max_% dos "
                    f"ingredientes (precisa permitir fechar 100%). Status: {status}"
                )
            elif payload_calc and payload_calc.get("relaxado"):
                st.warning(
                    "⚠️ Não foi possível atender **todas** as exigências com os "
                    "ingredientes/limites informados. A dieta abaixo é a melhor "
                    "aproximação possível — veja a aba **Atendimento de Exigências** "
                    "para identificar o que ficou faltando."
                )
            else:
                st.success("Formulação pronta! Veja os resultados abaixo.")

    # Se já há resultado calculado, mostra abas de resultados
    if "last_payload" in st.session_state and "last_df_res" in st.session_state:
        st.divider()
        render_resultados()


def render_resultados():
    payload = st.session_state["last_payload"]
    df_res = st.session_state["last_df_res"]
    df_shadow = st.session_state.get("last_df_shadow")
    df_rc = st.session_state.get("last_df_rc")
    df_nut = st.session_state.get("last_df_nut")
    custo = st.session_state.get("last_custo", payload.get("custo_R_kg", 0))

    st.header("📊 Resultados")

    if payload.get("relaxado"):
        st.warning(
            "⚠️ **Exigências não atendidas integralmente.** Não havia combinação "
            "de ingredientes capaz de cumprir todos os mínimos com os limites "
            "informados. Esta é a **melhor dieta aproximada** — confira a aba "
            "**Atendimento de Exigências** (coluna **Falta**) para ver o que "
            "ficou abaixo do exigido."
        )

    m1, m2, m3 = st.columns(3)
    m1.metric("Custo (R$/kg)", f"{float(custo):.4f}")
    m2.metric("Custo (R$/ton)", f"{float(custo)*1000:.2f}")
    m3.metric("Código", payload.get("codigo", "—"))

    tab_resumo, tab_exig, tab_sens, tab_save = st.tabs([
        "📋 Resumo",
        "✅ Atendimento de Exigências",
        "📊 Análise de Sensibilidade",
        "💾 Salvar / Baixar",
    ])

    with tab_resumo:
        st.subheader("Inclusão de ingredientes")
        st.dataframe(df_res, use_container_width=True, hide_index=True)
        st.caption(
            f"Categoria: **{payload.get('exigencia','—')}**  ·  "
            f"Fase: **{payload.get('fase','—')}**"
        )

    with tab_exig:
        st.subheader("Nutrientes da dieta (obtido vs exigido)")
        if df_nut is not None and not df_nut.empty:
            st.dataframe(df_nut, use_container_width=True, hide_index=True)
            faltam = df_nut[df_nut["Atende?"] == "NAO"]
            if faltam.empty:
                st.success("Todas as exigências foram atendidas ✅")
            else:
                st.warning(
                    "Não atendido em: " + ", ".join(faltam["Nutriente"].astype(str).tolist())
                )
        else:
            st.info("Sem dados de nutrientes.")

    with tab_sens:
        if payload.get("relaxado"):
            st.info(
                "Análise de sensibilidade não está disponível quando a "
                "formulação foi resolvida no modo relaxado (com folgas). "
                "Ajuste ingredientes/limites para obter uma dieta totalmente "
                "viável e essa aba volta a ser preenchida."
            )
        else:
            st.subheader("Preço-Sombra (restrições)")
            if df_shadow is not None and not df_shadow.empty:
                st.dataframe(df_shadow, use_container_width=True)
            else:
                st.info("Sem dados de preço-sombra.")

            st.subheader("Reduced Cost (ingredientes)")
            if df_rc is not None and not df_rc.empty:
                st.dataframe(df_rc, use_container_width=True, hide_index=True)
            else:
                st.info("Sem dados de reduced cost.")

    with tab_save:
        st.subheader("Salvar no histórico e baixar relatório")
        c1, c2, c3 = st.columns(3)

        with c1:
            if st.button("💾 Salvar no histórico", key="btn_salvar_historico", use_container_width=True):
                try:
                    meta = save_run(payload, df_res)
                    st.session_state["last_saved_id"] = meta.get("id", "")
                    st.success(f"Salvo no histórico! ID: {st.session_state['last_saved_id']}")
                except Exception as e:
                    st.error(f"Falha ao salvar: {e}")

        with c2:
            html = build_report_html(payload)
            st.download_button(
                "📄 Baixar HTML",
                data=html.encode("utf-8"),
                file_name="relatorio_formulacao.html",
                mime="text/html",
                key="btn_baixar_html",
                use_container_width=True,
            )

        with c3:
            try:
                pdf_bytes = make_pdf_report(payload)
                st.download_button(
                    "🧾 Baixar PDF",
                    data=pdf_bytes,
                    file_name="relatorio_formulacao.pdf",
                    mime="application/pdf",
                    key="btn_baixar_pdf",
                    use_container_width=True,
                )
            except Exception:
                st.caption("PDF: instale `reportlab` (python -m pip install reportlab)")

        with st.expander("👀 Pré-visualizar relatório (HTML)"):
            components.html(html, height=700, scrolling=True)


def render_formular():
    st.title("🧪 Formular Ração")
    _step_header(st.session_state["form_step"])

    df_food, df_req, ok = _load_data_for_form()
    if not ok:
        st.warning(
            "Você ainda não tem dados no banco. Vá em **Importar Planilha** "
            "ou cadastre alimentos/exigências em **Cadastros**."
        )
        return

    if df_req.empty or "Exigencia" not in df_req.columns or "Fase" not in df_req.columns:
        st.error("Exigências não carregadas corretamente. Verifique banco/planilha.")
        return

    step = st.session_state["form_step"]
    if step == 1:
        render_form_step1(df_req)
    elif step == 2:
        render_form_step2(df_food)
    elif step == 3:
        render_form_step3()
    elif step == 4:
        render_form_step4()


# =========================================================
# ROUTER
# =========================================================
render_sidebar()

page = st.session_state["current_page"]
if page == "home":
    render_home()
elif page == "formular":
    render_formular()
elif page == "cadastros":
    render_cadastros()
elif page == "historico":
    render_historico()
elif page == "importar":
    render_importar()
else:
    render_home()
