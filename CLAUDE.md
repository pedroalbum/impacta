# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this directory is

Not a code repository (no git, no scripts, no tests). It is a university project workspace for **Faculdade Impacta – Data Project: Modeling & Implementation (DPMI)**, Equipe 7 (Data Master): *Competitividade de preços no Mercado Livre com Machine Learning*, following CRISP-DM steps 1–6. Documents are in Brazilian Portuguese; keep new text in Portuguese. The final report is dated 18/11/2026.

**Project state:** the scope was revised (decided with the user): task = **price band (quartile of `preco_mediana` within the domain), 4-class ordinal classification**; framing = market benchmark, no specific seller; data = `valor_mlb_expandido` (origem=busca) joined to the 100k product CSV from `meli-ml_2.zip`. Modeling is done and `saida/Relatorio final - revisado.pdf` (13 pages) replaces the old "a apurar" tables. The original `Relatorio final.pdf` is untouched. Section 6.2 (extension work / partner) is deliberately left blank for the team to fill with real facts, never invented.

**Results (mean of 5 splits, 4,242 products, 99 domains):** macro-F1 baseline 0.11; TF-IDF+LogReg (all attributes) 0.59; CatBoost 0.55 (does not beat LogReg). Without `frete_gratis_pct` (which tracks price through a shipping rule): LogReg 0.51, CatBoost 0.47. Report both scenarios; do not present only the higher number.

## Pipeline (run from `src/modelo/`, not with `python -I`, because scripts import `config.py`; data files are looked up in `dados/` or `$DADOS_DIR`)

```
cd src/modelo   # raiz do repositório -> src/modelo
PY=python        # com o venv ativo (pip install -r requirements.txt)
$PY 01_montar_dataset.py        # join + filters -> saida/dataset_modelagem.csv, log_dataset.json
$PY 03_baselines_e_modelos.py   # grid search + 5-split evaluation (CatBoost step takes ~30+ min)
$PY 07_sem_frete.py             # scenario B (no frete_gratis_pct)
$PY 06_ablacao.py               # feature-group ablation (LogReg)
$PY 04_analise_erros.py         # figures + analise_erros.json (needs 03 outputs)
$PY 05_gerar_relatorio.py       # LOCAL ONLY (git-ignored): builds the final-report PDF; every number is read from saida/*.csv|json
$PY 08_gerar_trabalho_completo.py  # LOCAL ONLY (git-ignored): builds the 17-section 'Trabalho completo - atualizado.pdf'
```
`config.py` holds paths, seed (42), amplitude filter (<=100), min 12 products/domain, and the allowed/forbidden feature lists. `alvo.py` does the stratified split and computes quartile cuts **on train only**. Do not republish `dataset_modelagem.csv`, predictions or the model (API terms).

Known limits stated in the report: hyperparameters were tuned on seed-42 split only; splits are by product, not product group (possible optimism); `Dashboard.pbix` uses a `produtos_termo_busca` table absent from the workbook and has not been aligned with these numbers.

## Files

- `mercado_livre_limpo_FINAL.xlsx` – cleaned data from the Mercado Livre API (see sheets below).
- `Dashboard.pbix` – Power BI dashboard, 4 pages (CAPA, GERAL, PRODUTOS, ANÚNCIOS) built on `produtos_mlb_expandido`, `valor_mlb_expandido`, `categorias_mlb` and a `produtos_termo_busca` table. Inspect via `unzip -p Dashboard.pbix 'Report/definition/...'` (JSON); `DataModel` is binary.
- `Trabalho completo.pdf` – team's full CRISP-DM report (sections 1–17, ends with next steps).
- `Relatorio final.pdf` – the official template filled in by the team (Etapas 1–6).
- `modelo_relatorio_final_crispdm_dpmi.docx.pdf` – blank professor template (Prof. Gilberto Alves Pereira).

## Environment

Use a venv with `pip install -r requirements.txt`. Run with `-I`. Loading the whole workbook with `pd.read_excel(..., sheet_name=None)` takes a while (large sheets) but works. `pdftotext -layout` is available for the PDFs.

## Workbook sheets (actual columns)

| Sheet | Rows | Granularity / notes |
|---|---|---|
| `produtos_mlb` | 24,396 | product catalog; subset of the expanded one |
| `produtos_mlb_expandido` | 34,998 | unique `product_id`; `nome, domain_id, status, marca, modelo, n_atributos, n_variacoes, criado_em, termo_busca`. 1,749 domains, 21,115 inactive / 13,883 active, 200 products per `termo_busca`. `marca` ~4.7% null, `modelo` ~14% null. **No price column.** |
| `categorias_mlb` | 150 | category tree (`category_id, raiz, profundidade, total_itens, folha`) |
| `valor_mlb` | 1,218 | price stats **per domain × ranking position** (`posicao_ranking` 1–20, `categoria_ranking`, `preco_min/mediana/max`, `frete_gratis_pct`, ...). 333 domains |
| `valor_mlb_expandido` | 12,805 | price stats **per `product_id`** (`origem` = `busca` 6,803 or `ranking` 5,998; 4 rows with null `origem`); 1,612 domains. `posicao_ranking` only filled when `origem == 'ranking'` |
| `resumo_outliers_IQR` | 22 | IQR summary per sheet/variable |
| `correcoes_aplicadas` | 8 | log of absurd `preco_max` (e.g. 999,999; 2,200,000) set to null with `amplitude_pct`; rows kept |

## Data facts that affect modelling

- **There is no `preco` column and no `data_coleta`.** The report's planned dictionary (`produto_id, categoria, preco, frete_gratis, data_coleta`) does not match the workbook. The only per-product price signals are `preco_min/mediana/max` (aggregates over `n_anuncios` listings, median ~R$86, p99 ~R$5,121, max R$333,333) and `frete_gratis_pct`; `novos_pct` is constant 100. Any target must be defined from these (likely `preco_mediana`), and the report's own "use `preco_mediana` as baseline, not as feature" leakage warning then applies to `preco_min/max` and `amplitude_pct` too.
- **Join coverage is poor in the workbook, and the cause is known:** only ~24% of `valor_mlb_expandido.product_id` values exist in the workbook's `produtos_mlb_expandido`. Two reasons (verified against `meli-ml_2.zip`): (a) the workbook keeps only 34,998 of the 100,129 products in the original `produtos_mlb_expandido.csv`; (b) the 6,000 `origem == 'ranking'` rows (best sellers) are **disjoint from the search products by design** (~1% overlap) – they are a different population, not a sample. Against the full 100k CSV, 100% of the 6,805 `origem == 'busca'` rows join. Check row counts before and after every join; `valor_mlb` and `valor_mlb_expandido` are different levels (domain vs product); never mix them.
- **Companion project `meli-ml_2.zip`** (in this dir; the collection pipeline: `scripts/`, `dados/*.csv`, `docs/`, its own `AGENTS.md`/`CLAUDE.md`). It is reference material, not part of the deliverable. Extract it into a separate empty directory (e.g. `meli_extract/`) and do not run its scripts (they need Mercado Livre API credentials). Its docs say the originally validated use case is **classifying `nome` → `domain_id`** (macro-F1 0.852, 357 classes, TF-IDF char n-grams + LinearSVC, only on the 24k set; not re-measured on 100k), and that price regression in R$ is **not** supported by the data – it recommends price bands (quartiles within domain) instead. `marca`, `modelo` and `termo_busca` leak the domain label; for domain classification use only `nome`. Its legal notes: don't republish the dataset/model, never keep `seller_id`, never commit credentials, no scraping.
- Heavy right skew: report's IQR count is 1,484 outliers in 12,801 `preco_mediana` values (11.6%); consider log-target. Outliers are kept unless proven errors.
- `posicao_ranking` is a best-seller position (1–20), not units sold. In the report's dictionary `modelo` is mislabeled as "units sold"; it is actually the product model name (categorical).
- `criado_em` runs 2015-08 to 2026-09; it is listing creation date, not a collection timestamp, so the planned temporal validation has no collection dates to use. `marca`/`modelo` missing values should get indicators, not unjustified fills.

## Report commitments (from the PDFs)

- Regression on listed price vs. baselines (global median, median per category/comparable group); CatBoost Regressor is the main candidate, with ridge/Random Forest/HistGradientBoosting as extras. Metrics: MAE, RMSE (R$), R² (complementary), coverage, and error per category/brand/price band. Report residual = observed − estimated.
- Split by product/group (not random rows) to avoid leakage; compute baselines only on training data. No SMOTE (regression). No target numbers for MAE reduction were agreed yet.
- Scope limits: no claims about sales, margin, profit or optimal price; outputs only flag listings for human review, never auto-reprice. Results apply to the sample only, not to a specific seller (the seller's own listings are not identified in the data).
