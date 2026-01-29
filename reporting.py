# -*- coding: utf-8 -*-
from io import BytesIO
import pandas as pd


def build_report_html(payload: dict) -> str:
    """
    Gera HTML simples e limpo para impressão (o navegador salva em PDF).
    """

    rel = payload.get("relatorio", {}) or {}
    granja = rel.get("granja", "")
    produtor = rel.get("produtor", "")
    nutricionista = rel.get("nutricionista", "")
    numero_formula = rel.get("numero_formula", "")
    lote_obs = rel.get("lote_obs", "")
    observacoes = rel.get("observacoes", "")

    exigencia = payload.get("exigencia", "")
    fase = payload.get("fase", "")
    data_hora = payload.get("data_hora", "")

    # custo: usa novo padrão, mas aceita o antigo se existir
    custo_kg = payload.get("custo_R_kg", payload.get("custo_R$_kg", ""))
    custo_ton = payload.get("custo_R_ton", payload.get("custo_R$_ton", ""))

    def _fmt_num(v, ndigits: int) -> str:
        try:
            if v is None or v == "":
                return ""
            return f"{float(v):.{ndigits}f}"
        except Exception:
            return str(v)

    custo_kg_txt = _fmt_num(custo_kg, 4)
    custo_ton_txt = _fmt_num(custo_ton, 2)

    fb_max = payload.get("fb_max")
    ee_max = payload.get("ee_max")

    df_res = pd.DataFrame(payload.get("ingredientes", []))
    df_nut = pd.DataFrame(payload.get("nutrientes", []))

    # --- Monta texto de limites opcionais ---
    extras = []
    if fb_max is not None:
        extras.append(f"FB máx: {fb_max}")
    if ee_max is not None:
        extras.append(f"EE máx: {ee_max}")
    extras_txt = " | ".join(extras) if extras else "-"

    # --- Converte DataFrames para HTML com ajustes visuais ---
    def df_to_html(df: pd.DataFrame) -> str:
        if df is None or df.empty:
            return "<p><em>Sem dados.</em></p>"
        return df.to_html(index=False, border=0, classes="tabela")

    # --- Nutrientes: aplica cor no "Atende?" ---
    df_nut_html = df_to_html(df_nut)
    df_nut_html = df_nut_html.replace(">OK<", '><span class="ok">OK</span><')
    df_nut_html = df_nut_html.replace(">NAO<", '><span class="nao">NAO</span><')

    # language=HTML
    html = f"""
<html>
<head>
  <meta charset="utf-8"/>
  <style>
    body {{
      font-family: Arial, sans-serif;
      background-color: #0e1117;
      color: #e6e6e6;
      padding: 30px;
    }}

    h1, h2, h3 {{
      color: #ffffff;
      margin: 0 0 10px 0;
    }}

    .meta {{
      margin-bottom: 16px;
      color: #d6d6d6;
      line-height: 1.5;
    }}

    .grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }}

    .card {{
      background-color: #1a1f2b;
      padding: 15px;
      border-radius: 12px;
      box-shadow: 0px 0px 10px rgba(0,0,0,0.45);
      margin-bottom: 20px;
    }}

    table.tabela {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 10px;
    }}

    table.tabela th {{
      background-color: #2a2f3a;
      color: #ffffff;
      padding: 8px;
      text-align: left;
      font-size: 13px;
    }}

    table.tabela td {{
      padding: 8px;
      border-bottom: 1px solid #333;
      color: #e6e6e6;
      font-size: 13px;
      vertical-align: top;
    }}

    .ok {{
      color: #00ff88;
      font-weight: bold;
    }}

    .nao {{
      color: #ff4d4d;
      font-weight: bold;
    }}

    .rodape {{
      margin-top: 24px;
      color: #9aa0a6;
      font-size: 12px;
    }}

    /* Para impressão (opcional) */
    @media print {{
      body {{
        background-color: #ffffff;
        color: #000000;
      }}
      .card {{
        background-color: #ffffff;
        box-shadow: none;
        border: 1px solid #ddd;
      }}
      table.tabela th {{
        background-color: #f2f2f2;
        color: #000;
      }}
      table.tabela td {{
        color: #000;
      }}
      .rodape {{
        color: #333;
      }}
    }}
  </style>
</head>
<body>
  <h1>Relatório de Formulação (Suínos)</h1>

  <div class="card">
    <h3>Identificação</h3>
    <div class="meta">
      <div><b>Granja/Empresa:</b> {granja}</div>
      <div><b>Produtor/Responsável:</b> {produtor}</div>
      <div><b>Nutricionista/Técnico:</b> {nutricionista}</div>
      <div><b>Nº da fórmula:</b> {numero_formula}</div>
      <div><b>Lote/Obs:</b> {lote_obs}</div>
    </div>
    {"<p style='margin-top:10px; white-space: pre-wrap;'><b>Observações:</b><br>" + observacoes + "</p>" if observacoes else ""}
  </div>

  <div class="meta">
    <div><b>Data/Hora:</b> {data_hora}</div>
    <div><b>Exigência:</b> {exigencia}</div>
    <div><b>Fase:</b> {fase}</div>
    <div><b>Custo:</b> R$ {custo_kg_txt}/kg &nbsp; | &nbsp; R$ {custo_ton_txt}/ton</div>
    <div><b>Limites opcionais:</b> {extras_txt}</div>
  </div>

  <div class="grid">
    <div class="card">
      <h3>Inclusão de ingredientes</h3>
      {df_to_html(df_res)}
    </div>

    <div class="card">
      <h3>Nutrientes (obtido vs exigido)</h3>
      {df_nut_html}
    </div>
  </div>

  <p class="rodape">
    Dica: use o botão de imprimir do navegador (Ctrl+P) para salvar em PDF.
  </p>
</body>
</html>
"""
    return html


def make_pdf_report(payload: dict) -> bytes:
    """
    PDF automático (opcional) usando reportlab.
    Se não tiver instalado: python -m pip install reportlab
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    def _fmt(v, nd):
        try:
            if v is None or v == "":
                return ""
            return f"{float(v):.{nd}f}"
        except Exception:
            return str(v)

    y = height - 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "Relatório de Formulação (Suínos)")
    y -= 24

    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Data/Hora: {payload.get('data_hora','')}")
    y -= 14
    c.drawString(40, y, f"Exigência: {payload.get('exigencia','')}")
    y -= 14
    c.drawString(40, y, f"Fase: {payload.get('fase','')}")
    y -= 14

    custo_kg = payload.get("custo_R_kg", payload.get("custo_R$_kg", ""))
    custo_ton = payload.get("custo_R_ton", payload.get("custo_R$_ton", ""))
    c.drawString(40, y, f"Custo: R$ {_fmt(custo_kg,4)}/kg | R$ {_fmt(custo_ton,2)}/ton")
    y -= 20

    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Ingredientes (Inclusão %):")
    y -= 14
    c.setFont("Helvetica", 9)

    ingredientes = payload.get("ingredientes", [])
    for row in ingredientes[:40]:
        nome = row.get("Ingrediente", "")
        inc = row.get("Inclusao_%", "")
        preco = row.get("Preco_R$/kg", "")
        line = f"{nome}: {inc}% | Preço: R$ {preco}/kg"
        c.drawString(40, y, line)
        y -= 12
        if y < 60:
            c.showPage()
            y = height - 40
            c.setFont("Helvetica", 9)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()
