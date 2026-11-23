"""Ablação: quanto cada grupo de variáveis contribui (regressão logística, 5 divisões)."""
import numpy as np, pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from config import *
from alvo import carregar, dividir

df = carregar()
cenarios = {
    "Todas as variáveis": dict(num=FEATURES_NUM, cat=FEATURES_CAT, txt=True),
    "Sem frete grátis": dict(num=["n_atributos", "n_variacoes"], cat=FEATURES_CAT, txt=True),
    "Sem marca/modelo": dict(num=FEATURES_NUM, cat=["domain_id"], txt=True),
    "Sem texto do título": dict(num=FEATURES_NUM, cat=FEATURES_CAT, txt=False),
    "Só frete grátis + domínio": dict(num=["frete_gratis_pct"], cat=["domain_id"], txt=False),
}
linhas = []
for nome, c in cenarios.items():
    r = []
    for s in SEMENTES_REPETICAO:
        tr, te, _ = dividir(df, s)
        partes = []
        if c["txt"]: partes.append(("t", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True), FEATURE_TEXTO))
        partes.append(("c", OneHotEncoder(handle_unknown="ignore", min_frequency=2), c["cat"]))
        partes.append(("n", StandardScaler(), c["num"]))
        m = Pipeline([("p", ColumnTransformer(partes)), ("l", LogisticRegression(C=2.0, max_iter=3000))]).fit(tr, tr.faixa)
        p = m.predict(te)
        r.append((f1_score(te.faixa, p, average="macro"), float(np.abs(te.faixa - p).mean())))
    a = np.array(r)
    linhas.append({"cenario": nome, "macro_f1_media": a[:, 0].mean(), "macro_f1_dp": a[:, 0].std(ddof=1),
                   "erro_medio_faixas": a[:, 1].mean()})
    print(linhas[-1], flush=True)
pd.DataFrame(linhas).round(4).to_csv("../saida/ablacao.csv", index=False)
