"""Baselines e CatBoost para prever a faixa de preço (quartil dentro do domínio).

Hiperparâmetros do CatBoost são escolhidos só com treino/validação (semente principal); os modelos são
então avaliados em 5 divisões treino/teste diferentes para medir a estabilidade.
"""
import json, time, itertools
import numpy as np, pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, accuracy_score, cohen_kappa_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from catboost import CatBoostClassifier, Pool
from config import *
from alvo import carregar, dividir

COLS = [FEATURE_TEXTO] + FEATURES_CAT + FEATURES_NUM


def metricas(y, p):
    y, p = np.asarray(y), np.asarray(p)
    return {
        "macro_f1": f1_score(y, p, average="macro"),
        "acuracia": accuracy_score(y, p),
        "erro_medio_faixas": float(np.abs(y - p).mean()),
        "dentro_de_1_faixa": float((np.abs(y - p) <= 1).mean()),
        "kappa_quadratico": cohen_kappa_score(y, p, weights="quadratic"),
    }


def modelo_tfidf(usar_atributos):
    textos = ("txt", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True), FEATURE_TEXTO)
    if usar_atributos:
        pre = ColumnTransformer([textos,
                                 ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=2), FEATURES_CAT),
                                 ("num", StandardScaler(), FEATURES_NUM)])
    else:
        pre = ColumnTransformer([textos, ("dom", OneHotEncoder(handle_unknown="ignore"), ["domain_id"])])
    return Pipeline([("pre", pre), ("clf", LogisticRegression(C=2.0, max_iter=3000))])


def catboost(params, semente):
    return CatBoostClassifier(loss_function="MultiClass", random_seed=semente, verbose=0, thread_count=4,
                              allow_writing_files=False, **params)


def pool(df, com_y=True):
    return Pool(df[COLS], label=df["faixa"] if com_y else None,
                cat_features=FEATURES_CAT, text_features=[FEATURE_TEXTO])


def ajustar_catboost(tr, params, semente):
    """Treina com parada antecipada usando uma validação retirada do TREINO."""
    t, v = train_test_split(tr, test_size=0.15, random_state=semente, stratify=tr.faixa)
    m = catboost({**params, "iterations": 800, "od_type": "Iter", "od_wait": 60}, semente)
    m.fit(pool(t), eval_set=pool(v), use_best_model=True)
    return m, v


# ---------- 1) escolha de hiperparâmetros (só treino/validação, semente principal) ----------
df = carregar()
tr0, te0, _ = dividir(df, SEMENTE)
grade = [dict(depth=d, learning_rate=lr, l2_leaf_reg=l2)
         for d, lr, l2 in itertools.product([4, 6], [0.05, 0.1], [3, 10])]
busca = []
for g in grade:
    t0 = time.time()
    m, v = ajustar_catboost(tr0, g, SEMENTE)
    f1 = f1_score(v.faixa, m.predict(pool(v, False)).ravel().astype(int), average="macro")
    busca.append({**g, "f1_validacao": f1, "arvores": int(m.get_best_iteration() + 1), "seg": round(time.time() - t0, 1)})
    print(busca[-1], flush=True)
busca = pd.DataFrame(busca).sort_values("f1_validacao", ascending=False)
busca.to_csv(SAIDA / "busca_hiperparametros.csv", index=False)
melhor = {k: (int(busca.iloc[0][k]) if k == "depth" else float(busca.iloc[0][k])) for k in ["depth", "learning_rate", "l2_leaf_reg"]}
print("melhores:", melhor, flush=True)

# ---------- 2) avaliação em várias divisões ----------
linhas, diag = [], []
for s in SEMENTES_REPETICAO:
    tr, te, _ = dividir(df, s)
    # baseline: classe majoritária (por construção ~25%)
    d = DummyClassifier(strategy="most_frequent").fit(tr[COLS], tr.faixa)
    linhas.append({"semente": s, "modelo": "Baseline: classe majoritária", **metricas(te.faixa, d.predict(te[COLS]))})
    for nome, usar in [("TF-IDF + Reg. logística (nome + domínio)", False),
                       ("TF-IDF + Reg. logística (todos os atributos)", True)]:
        mdl = modelo_tfidf(usar).fit(tr[COLS], tr.faixa)
        linhas.append({"semente": s, "modelo": nome, **metricas(te.faixa, mdl.predict(te[COLS]))})
        if s == SEMENTE:
            diag.append({"modelo": nome, "f1_treino": f1_score(tr.faixa, mdl.predict(tr[COLS]), average="macro"),
                         "f1_teste": f1_score(te.faixa, mdl.predict(te[COLS]), average="macro")})
    m, _ = ajustar_catboost(tr, melhor, s)
    p = m.predict(pool(te, False)).ravel().astype(int)
    linhas.append({"semente": s, "modelo": "CatBoost (texto + atributos)", **metricas(te.faixa, p)})
    if s == SEMENTE:
        diag.append({"modelo": "CatBoost (texto + atributos)",
                     "f1_treino": f1_score(tr.faixa, m.predict(pool(tr, False)).ravel().astype(int), average="macro"),
                     "f1_teste": f1_score(te.faixa, p, average="macro")})
        te.assign(previsto=p).drop(columns=["faixa"]).assign(faixa=te.faixa.values).to_csv(SAIDA / "predicoes_teste.csv", index=False)
        m.save_model(str(SAIDA / "catboost_modelo.cbm"))
        imp = pd.DataFrame({"variavel": COLS, "importancia": m.get_feature_importance(pool(te))}).sort_values("importancia", ascending=False)
        imp.to_csv(SAIDA / "importancia_variaveis.csv", index=False)
        ev = m.get_evals_result()
        pd.DataFrame({"iteracao": range(len(ev["learn"]["MultiClass"])), "treino": ev["learn"]["MultiClass"],
                      "validacao": ev["validation"]["MultiClass"]}).to_csv(SAIDA / "curva_aprendizado.csv", index=False)
    print("semente", s, "ok", flush=True)

res = pd.DataFrame(linhas)
res.to_csv(SAIDA / "metricas_por_semente.csv", index=False)
resumo = res.drop(columns="semente").groupby("modelo").agg(["mean", "std"]).round(4)
resumo.columns = [f"{a}_{b}" for a, b in resumo.columns]
resumo.to_csv(SAIDA / "metricas.csv")
pd.DataFrame(diag).to_csv(SAIDA / "diagnostico_overfitting.csv", index=False)
(SAIDA / "hiperparametros_escolhidos.json").write_text(json.dumps(melhor))
print(resumo.T.to_string())
print(pd.DataFrame(diag))
