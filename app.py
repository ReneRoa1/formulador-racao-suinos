# -*- coding: utf-8 -*-
import streamlit as st

st.set_page_config(page_title="Formulador de Racao - Suinos", layout="wide")

# AGORA vêm os outros imports
import pandas as pd
from datetime import datetime
import streamlit.components.v1 as components
from history_db import save_run, list_runs, load_run
from reporting import build_report_html, make_pdf_report
from io_excel import load_planilha, build_ui_table
from solver import extract_requirements, solve_lp, calc_dieta, build_results_table, get_shadow_prices
from pulp import LpStatus, value

from auth_ui import auth_gate
user_id = auth_gate()

menu = st.sidebar.radio("Menu", ["Formular ração", "📚 Cadastros (meus dados)"])

from catalog_db import (
    fetch_foods, fetch_requirements,
    import_foods_from_df, import_requirements_from_df,
    foods_to_df_for_solver, requirements_to_df_for_ui
)

st.success(f"✅ Logado! user_id={user_id}")

# =========================================================
# SEÇÃO CADASTROS
# =========================================================
if menu == "📚 Cadastros (meus dados)":
    st.title("📚 Cadastros (meus dados)")

    from supabase_client import supabase_authed
    access_token = st.session_state.get("access_token")

    if not access_token:
        st.error("Sessão inválida. Faça login novamente.")
        st.stop()

    sb_user = supabase_authed(access_token)

    # =====================================================
    # CRUD ALIMENTOS (FORMULÁRIO)
    # =====================================================
    import json

    st.subheader("🍽️ Meus Alimentos")

    # ---------- FORM ----------
    st.markdown("### ➕ Adicionar alimento")

    with st.form("form_add_food", clear_on_submit=True):
        nome = st.text_input("Nome do alimento")
        categoria = st.text_input("Categoria")
        preco = st.number_input("Preço (R$/kg)", min_value=0.0, step=0.01)

        PB = st.number_input("PB (%)", 0.0)
        EM = st.number_input("EM", 0.0)
        Pdig = st.number_input("Pdig (%)", 0.0)
        Ca = st.number_input("Ca (%)", 0.0)
        Na = st.number_input("Na (%)", 0.0)
        Lisina = st.number_input("Lisina (%)", 0.0)
        MetCis = st.number_input("MetCis (%)", 0.0)
        Treonina = st.number_input("Treonina (%)", 0.0)
        Triptofano = st.number_input("Triptofano (%)", 0.0)
        FB = st.number_input("FB (%)", 0.0)
        EE = st.number_input("EE (%)", 0.0)

        submitted = st.form_submit_button("Adicionar")

    if submitted and nome.strip():
        payload = {
            "user_id": user_id,
            "nome": nome.strip(),
            "categoria": categoria.strip() or None,
            "preco": float(preco),
            "nutrientes": {
                "PB": PB, "EM": EM, "Pdig": Pdig, "Ca": Ca, "Na": Na,
                "Lisina": Lisina, "MetCis": MetCis, "Treonina": Treonina,
                "Triptofano": Triptofano, "FB": FB, "EE": EE
            }
        }
        sb_user.table("foods").insert(payload).execute()
        st.success("Alimento adicionado ✅")
        st.rerun()

    # ---------- LISTAGEM ----------
    rows = sb_user.table("foods").select("*").eq("user_id", user_id).order("nome").execute().data
    df = pd.DataFrame(rows)
    st.dataframe(df[["nome","categoria","preco"]], use_container_width=True)

    # ---------- DELETE ----------
    if not df.empty:
        food_id = st.selectbox("Excluir alimento", df["id"], format_func=lambda x: df[df["id"]==x]["nome"].iloc[0])
        if st.button("Excluir"):
            sb_user.table("foods").delete().eq("id", food_id).execute()
            st.rerun()

    # 🚨 ISSO É O MAIS IMPORTANTE
    st.stop()


# =========================================================
# SEÇÃO FORMULAR (se chegou aqui, menu == "Formular ração")
# =========================================================
st.title("Formulador de Racao (Suinos) - Web")

from supabase_client import supabase_authed

access_token = st.session_state.get("access_token")
if not access_token:
    st.error("Sessão inválida. Faça login novamente.")
    st.stop()

sb_user = supabase_authed(access_token)

usar_banco = st.toggle("Usar dados do banco (Supabase)", value=True)

df_food_db = fetch_foods(sb_user, user_id)
df_req_db  = fetch_requirements(sb_user, user_id)


from supabase_client import supabase_authed
access_token = st.session_state.get("access_token")
if not access_token:
    st.error("Sessão inválida. Faça login novamente.")
    st.stop()

sb_user = supabase_authed(access_token)

if usar_banco:
    try:
        foods_rows = (
    sb_user.table("foods")
    .select("*")
    .eq("user_id", user_id)
    .execute()
    .data
)
        req_rows = (
    sb_user.table("requirements")
    .select("*")
    .eq("user_id", user_id)
    .execute()
    .data
)

        df_food_db = pd.DataFrame(foods_rows)
        df_req_db = pd.DataFrame(req_rows)


        if not df_food_db.empty and not df_req_db.empty:
            df_food = foods_to_df_for_solver(df_food_db)
            df_req = requirements_to_df_for_ui(df_req_db)
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


      # -------- payload (AGORA sim, depois de linhas existir) --------
    payload = {
        "codigo": codigo_formula,  
        "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "exigencia": exigencia_escolhida,  # <-- ESSENCIAL
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
