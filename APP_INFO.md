# Formulador de Ração - Suínos

Aplicação web para formulação de rações de suínos por **mínimo custo** (programação linear), com gestão de cadastros próprios de **alimentos** e **exigências nutricionais**, histórico de formulações e geração de relatórios em HTML/PDF.

---

## 1. Visão geral

- **Stack:** Python + Streamlit (UI) + PuLP/HiGHS (solver LP) + Supabase (auth + banco de dados Postgres) + ReportLab (PDF) + Pandas/Openpyxl (planilhas).
- **Autenticação:** via Supabase (email + senha). Cada usuário tem seus próprios alimentos, exigências e histórico (RLS por `user_id`).
- **Deploy:** scripts `start.sh` / `render-build.sh` / `render.yaml` para hospedagem no Render.

## 2. Estrutura de pastas

```
Forrmulacao1/
├── Forrmulacao1.sln
├── otimizar.py
├── APP_INFO.md                  ← este documento
└── Forrmulacao1/
    ├── app.py                   ← entry-point Streamlit (UI principal)
    ├── auth_ui.py               ← login / signup / logout (Supabase Auth)
    ├── supabase_client.py       ← clients Supabase (anon e autenticado)
    ├── bootstrap_db.py          ← cópia inicial de templates para o usuário
    ├── catalog_db.py            ← import/fetch de foods e requirements
    ├── history_db.py            ← persistência de runs (formulações salvas)
    ├── history.py               ← utilitários de histórico (pasta local)
    ├── io_excel.py              ← leitura da planilha (.xlsx) do usuário
    ├── solver.py                ← LP de mínimo custo (PuLP + HiGHS)
    ├── reporting.py             ← HTML estilizado e PDF (reportlab)
    ├── requirements.txt
    ├── runtime.txt
    ├── start.sh
    ├── render-build.sh
    ├── render.yaml
    └── data/
```

## 3. Banco de dados (Supabase)

Três tabelas principais (com `user_id` para isolamento por usuário):

| Tabela          | Campos relevantes                                                                 |
|-----------------|-----------------------------------------------------------------------------------|
| `foods`         | `id`, `user_id`, `nome`, `categoria`, `preco`, `nutrientes` (jsonb), `updated_at` |
| `requirements`  | `id`, `user_id`, `exigencia`, `fase`, `req_min` (jsonb), `updated_at`             |
| `runs`          | `id`, `codigo`, `data_hora`, `fase`, `custo_R_kg`, `payload` (jsonb)              |

`nutrientes` e `req_min` aceitam: `PB, EM, Pdig, Ca, Na, Lisina, MetCis, Treonina, Triptofano, FB, EE`.

## 4. Solver (LP)

Arquivo: `solver.py`.

- Variáveis: inclusão (%) por ingrediente, com `lowBound = Min_%` e `upBound = Max_%`.
- Restrições: soma das inclusões = 100; mínimos por nutriente; máximos opcionais (FB, EE).
- Objetivo: minimizar `Σ x_i · Preço_i / 100` (R$/kg).
- Saídas: tabela de inclusão, dieta resultante, **preços-sombra** (`get_shadow_prices`) e **reduced costs manuais** via duals (`get_reduced_costs_manual`).
- **Fallback elástico (`solve_lp_relaxado`)**: quando o LP rígido é inviável, refaz com variáveis de folga (slack) nos mínimos de nutrientes e máximos opcionais (FB/EE), penalizadas no objetivo (peso normalizado pelo valor exigido). Sempre acha solução desde que a soma dos `Max_%/Min_%` permita fechar 100%. O payload é marcado com `relaxado=True` e a UI exibe aviso + coluna **Falta** na aba de Atendimento de Exigências.

## 5. Fluxo da UI (organização atual)

A aplicação está organizada em uma **tela inicial** (Home) e em **páginas dedicadas** acessíveis pelo menu lateral. A formulação é um **wizard de 4 etapas** e os resultados aparecem em **abas separadas**.

### 5.1 Tela inicial (Home)

- Boas-vindas com identificação do usuário logado.
- Cards de navegação:
  - **Formular Ração** → wizard de formulação.
  - **Cadastros** → alimentos e exigências do usuário.
  - **Histórico** → reabrir/baixar formulações anteriores.
  - **Importar Planilha** → upload de `.xlsx` para popular o banco.
- Pequeno resumo: nº de alimentos cadastrados, nº de exigências, nº de formulações no histórico.

### 5.2 Formular Ração (wizard de 4 etapas)

| Etapa | Conteúdo |
|------|----------|
| **1 — Categoria + Fase** | Escolha da `Exigencia` (categoria/fonte: Rostagno, NRC, etc.) e da `Fase`. Após escolher, é exibida uma **tabela editável com todos os mínimos da fase** (PB, EM, Pdig, Ca, Na, Lisina, MetCis, Treonina, Triptofano), permitindo ajustar os valores antes de avançar. |
| **2 — Alimentos** | Tabela editável com seleção dos ingredientes, `Min_%`, `Max_%` e preço. Limites opcionais de FB (máx) e EE (máx). |
| **3 — Dados do Relatório** | Granja/Empresa, Produtor, Nutricionista, Nº da fórmula, Lote/Obs, Observações livres. |
| **4 — Calcular** | Executa o solver e libera a aba de **Resultados**. |

A barra de progresso mostra a etapa atual; botões **Voltar / Avançar** preservam o estado em `st.session_state["form_data"]`.

### 5.3 Resultados (abas)

Após o cálculo, os resultados são exibidos em quatro abas:

1. **Resumo** — custo (R$/kg e R$/ton), tabela de inclusão dos ingredientes.
2. **Atendimento de Exigências** — comparação obtido vs exigido, com OK/NAO destacado.
3. **Análise de Sensibilidade** — preço-sombra das restrições (`get_shadow_prices`) e reduced cost dos ingredientes (`get_reduced_costs_manual`).
4. **Salvar / Baixar** — salvar formulação no histórico (Supabase) e download do relatório em HTML / PDF.

### 5.4 Cadastros

Aba dupla:
- **Alimentos:** cadastrar / listar / editar / excluir.
- **Exigências:** cadastrar / listar / editar / excluir.

### 5.5 Histórico

- Lista todas as formulações salvas (código, data, fase, custo).
- Reabrir relatório (HTML embutido) ou baixar HTML.

### 5.6 Importar Planilha

- Upload de `.xlsx` com abas `Alimentos` e `Exigencias`.
- Botão para popular as tabelas `foods` e `requirements` do usuário.

## 6. Estado da sessão (session_state)

Chaves principais usadas no fluxo:

| Chave                          | Finalidade                                       |
|--------------------------------|--------------------------------------------------|
| `current_page`                 | Página ativa (`home`, `formular`, `cadastros`, `historico`, `importar`). |
| `form_step`                    | Etapa atual do wizard (1..4).                    |
| `form_data`                    | Dicionário com `exigencia`, `fase`, `req_min`, `edited`, `fb_lim`, `ee_lim`, dados do relatório. |
| `last_payload` / `last_df_res` | Resultado da última formulação para salvar/baixar. |
| `last_saved_id`                | ID retornado após salvar no histórico.           |
| `session` / `user`             | Auth do Supabase.                                |

## 7. Como rodar localmente

```bash
cd Forrmulacao1
pip install -r requirements.txt
streamlit run app.py
```

Variáveis de ambiente exigidas:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_KEY`

## 8. Histórico de alterações deste documento

- **2026-05-08** — Criado `APP_INFO.md`. Refatoração da UI: tela inicial com navegação; formulação dividida em wizard de 4 etapas (categoria+fase → alimentos → dados → calcular); resultados separados em abas (Resumo / Exigências / Sensibilidade / Salvar). Páginas Histórico e Importar Planilha separadas.
- **2026-05-10** — Etapa 1 do wizard: substituído o card de `st.metric` (somente leitura) por uma tabela editável (`st.data_editor`) com os mínimos da fase. Os valores ajustados são persistidos em `form_data["req_min"]` e usados pelo solver.
- **2026-05-10** — Etapa 2: tabela de alimentos passa a iniciar com a coluna **Usar** toda **desmarcada** (antes vinha tudo marcado).
- **2026-05-10** — Solver: adicionado `solve_lp_relaxado` (LP elástico com slacks normalizadas pelo valor exigido). Quando o LP rígido é inviável, `_executar_calculo` cai automaticamente no relaxado, marca `payload["relaxado"]=True` e a UI mostra aviso + coluna **Falta** na aba "Atendimento de Exigências". A aba "Análise de Sensibilidade" fica desativada nesse modo.
