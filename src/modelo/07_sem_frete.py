"""Cenário sem frete_gratis_pct (variável ligada ao preço pela regra de frete grátis da plataforma)."""
import json
import numpy as np, pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, accuracy_score, cohen_kappa_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from catboost import CatBoostClassifier, Pool
from config import *
from alvo import carregar, dividir
import importlib; M = importlib.import_module("03_baselines_e_modelos") if False else None

NUM = [c for c in FEATURES_NUM if c != "frete_gratis_pct"]
COLS = [FEATURE_TEXTO] + FEATURES_CAT + NUM
hp = json.loads((SAIDA / "hiperparametros_escolhidos.json").read_text())
df = carregar(); out = []
def met(y, p):
    y, p = np.asarray(y), np.asarray(p)
    return dict(macro_f1=f1_score(y, p, average="macro"), acuracia=accuracy_score(y, p), erro_medio_faixas=float(np.abs(y-p).mean()),
                dentro_de_1_faixa=float((np.abs(y-p) <= 1).mean()), kappa_quadratico=cohen_kappa_score(y, p, weights="quadratic"))
for s in SEMENTES_REPETICAO:
    tr, te, _ = dividir(df, s)
    pre = ColumnTransformer([("t", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True), FEATURE_TEXTO),
                             ("c", OneHotEncoder(handle_unknown="ignore", min_frequency=2), FEATURES_CAT), ("n", StandardScaler(), NUM)])
    lr = Pipeline([("p", pre), ("l", LogisticRegression(C=2.0, max_iter=3000))]).fit(tr[COLS], tr.faixa)
    out.append({"semente": s, "modelo": "TF-IDF + Reg. logística (sem frete)", **met(te.faixa, lr.predict(te[COLS]))})
    # CatBoost: mesma estratégia de parada antecipada (validação retirada do treino)
    from sklearn.model_selection import train_test_split
    t, v = train_test_split(tr, test_size=0.15, random_state=s, stratify=tr.faixa)
    mk = lambda d: Pool(d[COLS], label=d.faixa, cat_features=FEATURES_CAT, text_features=[FEATURE_TEXTO])
    cb = CatBoostClassifier(loss_function="MultiClass", random_seed=s, verbose=0, thread_count=4, allow_writing_files=False,
                            iterations=800, od_type="Iter", od_wait=60, **hp)
    cb.fit(mk(t), eval_set=mk(v), use_best_model=True)
    p = cb.predict(Pool(te[COLS], cat_features=FEATURES_CAT, text_features=[FEATURE_TEXTO])).ravel().astype(int)
    out.append({"semente": s, "modelo": "CatBoost (sem frete)", **met(te.faixa, p)})
    print("semente", s, flush=True)
r = pd.DataFrame(out); r.to_csv(SAIDA / "metricas_sem_frete_por_semente.csv", index=False)
g = r.drop(columns="semente").groupby("modelo").agg(["mean", "std"]).round(4); g.columns = [f"{a}_{b}" for a, b in g.columns]
g.to_csv(SAIDA / "metricas_sem_frete.csv"); print(g.T.to_string())
