# -*- coding: utf-8 -*-
import pandas as pd
from pulp import LpProblem, LpMinimize, LpVariable, lpSum, LpStatus, value
import pulp



NUTRIENTS_MIN = ["PB","EM","Pdig","Ca","Na","Lisina","MetCis","Treonina","Triptofano"]


def extract_requirements(df_req: pd.DataFrame, fase: str) -> dict:
    """
    Pega os mínimos de nutrientes para a fase selecionada.
    Retorna dict: {nutriente: minimo}
    """
    linha = df_req[df_req["Fase"] == str(fase)]
    if linha.empty:
        raise ValueError(f"Fase '{fase}' não encontrada na aba Exigencias.")
    row = linha.iloc[0].to_dict()

    req = {}
    for nut in NUTRIENTS_MIN:
        req[nut] = row.get(nut, None)
    return req


def solve_lp(df_food_sel: pd.DataFrame, req_min: dict, fb_max=None, ee_max=None):
    """
    Resolve a formulação por custo mínimo.
    df_food_sel precisa ter:
      Alimentos, Preco, Min_%, Max_% e nutrientes.
    """
    prob = LpProblem("Formulacao_suinos", LpMinimize)

    # Variáveis: inclusão (%) por ingrediente
    x = {}
    for _, row in df_food_sel.iterrows():
        nome = str(row["Alimentos"])
        min_inc = float(row["Min_%"])
        max_inc = float(row["Max_%"])
        x[nome] = LpVariable(nome, lowBound=min_inc, upBound=max_inc)

    # Soma 100%
    prob += lpSum(x[n] for n in x) == 100, "Soma_100"

    def nutr(nome, col):
        return float(df_food_sel.loc[df_food_sel["Alimentos"] == nome, col].iloc[0])

    # Mínimos
    for nut, minimo in req_min.items():
        if minimo is None:
            continue
        if nut not in df_food_sel.columns:
            continue
        prob += lpSum(x[n] * nutr(n, nut) for n in x) / 100 >= float(minimo), f"{nut}_min"

    # Máximos opcionais
    if fb_max is not None and "FB" in df_food_sel.columns:
        prob += lpSum(x[n] * nutr(n, "FB") for n in x) / 100 <= float(fb_max), "FB_max"

    if ee_max is not None and "EE" in df_food_sel.columns:
        prob += lpSum(x[n] * nutr(n, "EE") for n in x) / 100 <= float(ee_max), "EE_max"

    # Objetivo: custo mínimo
    prob += lpSum(x[n] * nutr(n, "Preco") for n in x) / 100

    import pulp

    solver = pulp.HiGHS(msg=False)
    prob.solve(solver)






    status = pulp.LpStatus[prob.status]
    return prob, x, status





def calc_dieta(df_food_sel: pd.DataFrame, x: dict) -> dict:
    """
    Calcula nutrientes finais obtidos.
    """
    nutrients = [c for c in ["PB","EM","Pdig","Ca","Na","Lisina","MetCis","Treonina","Triptofano","FB","EE"]
                 if c in df_food_sel.columns]

    result = {}
    for nut in nutrients:
        total = 0.0
        for nome in x:
            inc = value(x[nome]) or 0.0
            val = float(df_food_sel.loc[df_food_sel["Alimentos"] == nome, nut].iloc[0])
            total += inc * val
        result[nut] = total / 100
    return result


def build_results_table(df_food_sel: pd.DataFrame, x: dict) -> pd.DataFrame:
    """
    Tabela de inclusão + preço.
    """
    rows = []
    for nome in x:
        inc = value(x[nome]) or 0.0
        if inc > 1e-6:
            preco = float(df_food_sel.loc[df_food_sel["Alimentos"] == nome, "Preco"].iloc[0])
            rows.append({"Ingrediente": nome, "Inclusao_%": round(inc, 4), "Preco_R$/kg": preco})
    return pd.DataFrame(rows).sort_values("Inclusao_%", ascending=False)

def get_shadow_prices(prob):
    """
    Extrai preço-sombra e folga das restrições.
    """
    rows = []
    for cname, c in prob.constraints.items():
        rows.append({
            "Restricao": cname,
            "Preco_Sombra": getattr(c, "pi", None),
            "Folga": getattr(c, "slack", None),
            "Ativa": abs(getattr(c, "slack", 0)) < 1e-6
        })
    return pd.DataFrame(rows)

def get_reduced_costs(prob, x_vars):
    rows = []
    for name, var in x_vars.items():
        rows.append({
            "Ingrediente": name,
            "Inclusao_%": var.varValue,
            "Custo_Reduzido": getattr(var, "dj", None)  # <-- aqui!
        })
    return pd.DataFrame(rows)

def get_reduced_costs_manual(prob, df_food_sel: pd.DataFrame, x_vars: dict, req_min: dict, fb_max=None, ee_max=None):
    """
    Reduced cost calculado via duals (constraint.pi).
    Funciona mesmo quando PuLP não preenche var.dj.
    """
    # duals disponíveis
    dual = {name: getattr(c, "pi", 0.0) for name, c in prob.constraints.items()}

    # helper coeficiente do nutriente no ingrediente
    def nutr(nome, col):
        return float(df_food_sel.loc[df_food_sel["Alimentos"] == nome, col].iloc[0])

    rows = []

    for nome, var in x_vars.items():
        # c_j no seu objetivo: (Preco)/100
        c_j = nutr(nome, "Preco") / 100.0

        # soma pi_i * a_ij
        s = 0.0

        # Soma_100: sum x == 100  -> coef = 1
        s += dual.get("Soma_100", 0.0) * 1.0

        # mínimos: sum(x*nut)/100 >= minimo -> coef = nut/100
        for nut, minimo in req_min.items():
            if minimo is None:
                continue
            if nut not in df_food_sel.columns:
                continue
            cname = f"{nut}_min"
            a_ij = nutr(nome, nut) / 100.0
            s += dual.get(cname, 0.0) * a_ij

        # máximos opcionais: sum(x*FB)/100 <= fb_max -> coef = FB/100
        if fb_max is not None and "FB" in df_food_sel.columns:
            a_ij = nutr(nome, "FB") / 100.0
            s += dual.get("FB_max", 0.0) * a_ij

        if ee_max is not None and "EE" in df_food_sel.columns:
            a_ij = nutr(nome, "EE") / 100.0
            s += dual.get("EE_max", 0.0) * a_ij

        rc = c_j - s

        rows.append({
            "Ingrediente": nome,
            "Inclusao_%": float(var.varValue or 0.0),
            "Reduced_Cost": rc,
        })

    df = pd.DataFrame(rows)

    # Deixa mais legível: ordena pelos que estão fora da solução e mais “perto” de entrar
    df["Usado?"] = df["Inclusao_%"] > 1e-6
    df = df.sort_values(["Usado?", "Reduced_Cost"], ascending=[False, True]).reset_index(drop=True)

    return df
