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
from solver import extract_requirements, solve_lp, calc_dieta, build_results_table
from pulp import LpStatus, value

st.title("Formulador de Racao (Suinos) - Web")


arquivo = st.file_uploader("Envie sua planilha .xlsx (abas: 'Alimentos' e 'Exigencias')", type=["xlsx"])
if not arquivo:
    st.info("Envie a planilha para começar.")
    st.stop()

df_food, df_req = load_planilha(arquivo)

col1, col2 = st.columns([2, 1])
with col1:
    fase = st.selectbox("Escolha a fase (suínos)", df_req["Fase"].tolist())
with col2:
    st.caption("Energia usada: **EM (Suínos)**")

req_min = extract_requirements(df_req, fase)

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

    # nutrientes
    st.subheader("Nutrientes da dieta (obtido vs exigido)")
    dieta = calc_dieta(df_sel, x)

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


    # -------- payload (AGORA sim, depois de linhas existir) --------
    payload = {
        "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fase": fase,
        "custo_R_kg": round(custo, 6),
        "custo_R_ton": round(custo * 1000, 2),
        "fb_max": fb_lim if fb_lim is not None else None,
        "ee_max": ee_lim if ee_lim is not None else None,
        "ingredientes": df_res.to_dict(orient="records"),
        "nutrientes": df_nut.to_dict(orient="records"),
        "ingredientes_config": edited[["Alimentos","Usar","Min_%","Max_%","Preco"]].to_dict(orient="records"),
        "relatorio": {
        "granja": granja,
        "produtor": produtor,
        "nutricionista": nutricionista,
        "numero_formula": numero_formula,
        "lote_obs": lote_obs,
        "observacoes": observacoes,
},

    }

    st.session_state["last_payload"] = payload
    st.session_state["last_df_res"] = df_res

st.divider()
st.subheader("Salvar / Relatório")

c1, c2, c3 = st.columns(3)

if "last_payload" not in st.session_state:
    st.info("Faça uma formulação para habilitar salvar e gerar relatório.")
else:
    payload_last = st.session_state["last_payload"]
    df_last = st.session_state["last_df_res"]

    with c1:
        if st.button("Salvar no histórico"):
            meta = save_run(payload_last, df_last)
            st.session_state["last_saved_id"] = meta["id"]
            st.rerun()

    with c2:
        html = build_report_html(payload_last)
        st.download_button(
            "Baixar relatório (HTML)",
            data=html.encode("utf-8"),
            file_name="relatorio_formulacao.html",
            mime="text/html",
        )

    with c3:
        try:
            pdf_bytes = make_pdf_report(payload_last)
            st.download_button(
                "Baixar PDF",
                data=pdf_bytes,
                file_name="relatorio_formulacao.pdf",
                mime="application/pdf",
            )
        except Exception:
            st.caption("PDF: instale reportlab (python -m pip install reportlab)")

if "last_saved_id" in st.session_state:
    st.success(f"Salvo no histórico! ID: {st.session_state['last_saved_id']}")



# ================= HISTÓRICO =================
st.divider()
st.header("Histórico (salvos no computador)")

hist = list_runs()

if hist.empty:
    st.info("Nenhuma formulação salva ainda.")
else:
    st.dataframe(hist, use_container_width=True, hide_index=True)

    run_id = st.selectbox("Escolha um ID para reabrir", hist["id"].tolist())

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
