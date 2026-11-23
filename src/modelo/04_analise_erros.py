"""Análise de erros, figuras e checagem do confundidor de comprimento de título."""
import json
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import confusion_matrix, f1_score
from config import *

FIGURAS.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
AZUL = "#1f4e79"

df = pd.read_csv(SAIDA / "dataset_modelagem.csv")
pr = pd.read_csv(SAIDA / "predicoes_teste.csv")
out = {}

# --- Fig 1/2: distribuição do preço mediano (escala log) ---
fig, ax = plt.subplots(1, 2, figsize=(9, 3.4))
ax[0].hist(np.log10(df.preco_mediana), bins=40, color=AZUL)
ax[0].set_xlabel("log10(preço mediano em R$)"); ax[0].set_ylabel("Produtos"); ax[0].set_title("Histograma")
ax[1].boxplot(df.preco_mediana, vert=False, showfliers=True, flierprops=dict(markersize=2, alpha=.4))
ax[1].set_xscale("log"); ax[1].set_xlabel("Preço mediano (R$, escala log)"); ax[1].set_yticks([]); ax[1].set_title("Boxplot")
fig.tight_layout(); fig.savefig(FIGURAS / "fig_distribuicao_preco.png", dpi=170); plt.close(fig)

# --- Fig 3: matriz de confusão ---
cm = confusion_matrix(pr.faixa, pr.previsto, labels=range(N_FAIXAS))
cmn = cm / cm.sum(1, keepdims=True)
fig, ax = plt.subplots(figsize=(4.4, 3.8))
im = ax.imshow(cmn, cmap="Blues", vmin=0, vmax=1)
for i in range(N_FAIXAS):
    for j in range(N_FAIXAS):
        ax.text(j, i, f"{cm[i,j]}\n{cmn[i,j]:.0%}", ha="center", va="center", color="white" if cmn[i, j] > .5 else "black", fontsize=9)
rot = ["Q1\n(mais barato)", "Q2", "Q3", "Q4\n(mais caro)"]
ax.set_xticks(range(4)); ax.set_xticklabels(rot, fontsize=8); ax.set_yticks(range(4)); ax.set_yticklabels(rot, fontsize=8)
ax.set_xlabel("Faixa prevista"); ax.set_ylabel("Faixa real"); ax.set_title("CatBoost – conjunto de teste")
fig.tight_layout(); fig.savefig(FIGURAS / "fig_matriz_confusao.png", dpi=170); plt.close(fig)
out["matriz_confusao"] = cm.tolist()

# --- Fig 4: importância das variáveis ---
imp = pd.read_csv(SAIDA / "importancia_variaveis.csv")
fig, ax = plt.subplots(figsize=(5.2, 3.2))
ax.barh(imp.variavel[::-1], imp.importancia[::-1], color=AZUL); ax.set_xlabel("Importância (CatBoost)")
fig.tight_layout(); fig.savefig(FIGURAS / "fig_importancia.png", dpi=170); plt.close(fig)

# --- Fig 5: curva de aprendizado ---
cv = pd.read_csv(SAIDA / "curva_aprendizado.csv")
fig, ax = plt.subplots(figsize=(5.2, 3.2))
ax.plot(cv.iteracao, cv.treino, label="Treino", color=AZUL); ax.plot(cv.iteracao, cv.validacao, label="Validação", color="#c0504d")
ax.set_xlabel("Iteração"); ax.set_ylabel("Perda (MultiClass)"); ax.legend(frameon=False)
fig.tight_layout(); fig.savefig(FIGURAS / "fig_curva_aprendizado.png", dpi=170); plt.close(fig)

# --- erro por domínio e por categoria raiz ---
pr["erro_abs"] = (pr.faixa - pr.previsto).abs()
pr["acerto"] = (pr.faixa == pr.previsto).astype(int)
dom = pr.groupby("domain_id").agg(n=("acerto", "size"), acuracia=("acerto", "mean"), erro_medio=("erro_abs", "mean")).reset_index()
dom = dom[dom.n >= 5].sort_values("acuracia")
dom.to_csv(SAIDA / "erro_por_dominio.csv", index=False)
out["dominios_com_n>=5"] = int(len(dom))
out["pior_5_dominios"] = dom.head(5).to_dict("records")
out["melhor_5_dominios"] = dom.tail(5).to_dict("records")

# --- casos de maior erro (candidatos a revisão humana) ---
grandes = pr[pr.erro_abs >= 2].sort_values("erro_abs", ascending=False)
grandes[["product_id", "nome", "domain_id", "faixa", "previsto", "preco_mediana", "n_anuncios"]].head(30).to_csv(SAIDA / "casos_maior_erro.csv", index=False)
out["teste_erro_>=2_faixas"] = int(len(grandes)); out["teste_n"] = int(len(pr))

# --- confundidor: comprimento do título e preço, e se o modelo se apoia nele ---
df["len_nome"] = df.nome.str.len()
rho = df.groupby("domain_id").apply(lambda g: g.len_nome.corr(np.log(g.preco_mediana), method="spearman") if len(g) >= 12 else np.nan).dropna()
out["spearman_len_titulo_vs_preco_dentro_do_dominio_mediana"] = round(float(rho.median()), 3)
out["spearman_len_titulo_vs_faixa_global"] = round(float(df.len_nome.corr(np.log(df.preco_mediana), method="spearman")), 3)
# preditor trivial só com o comprimento do título (dentro do teste): mesma faixa para quem passa da mediana do domínio
med = df.groupby("domain_id").len_nome.median()
prev_len = (pr.nome.str.len() > pr.domain_id.map(med)).astype(int) * 3
out["macro_f1_regra_so_comprimento"] = round(float(f1_score(pr.faixa, prev_len, average="macro")), 3)

# --- relação preço x frete grátis (descritiva) ---
df["faixa_dom"] = df.groupby("domain_id").preco_mediana.rank(pct=True)
out["spearman_frete_vs_posicao_de_preco_no_dominio"] = round(float(df.frete_gratis_pct.corr(df.faixa_dom, method="spearman")), 3)

# --- ranking x preço (linhas de ranking, só descritiva) ---
v = pd.read_excel(PLANILHA, sheet_name="valor_mlb_expandido")
rk = v[(v.origem == "ranking") & v.preco_mediana.notna()]
out["ranking_n"] = int(len(rk))
out["spearman_posicao_ranking_vs_preco"] = round(float(rk.posicao_ranking.corr(np.log(rk.preco_mediana), method="spearman")), 3)

# --- IQR de preco_mediana na planilha completa (confere o 1.484 / 11,6% do relatório) ---
x = v.preco_mediana.dropna()
q1, q3 = x.quantile([.25, .75]); lim = q3 + 1.5 * (q3 - q1)
out["iqr_preco_mediana"] = {"validos": int(len(x)), "outliers": int((x > lim).sum() + (x < q1 - 1.5 * (q3 - q1)).sum()), "limite_sup": round(float(lim), 2)}
out["iqr_posicao_ranking_validos"] = int(v.posicao_ranking.notna().sum())

(SAIDA / "analise_erros.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=float))
print(json.dumps(out, indent=2, ensure_ascii=False, default=float))
