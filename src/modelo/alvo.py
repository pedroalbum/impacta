"""Divisão treino/teste e alvo (faixa de preço por quartil DENTRO do domínio).

Os cortes de quartil são calculados apenas com o treino e aplicados ao teste, para não vazar informação.
"""
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from config import *


def carregar():
    df = pd.read_csv(SAIDA / "dataset_modelagem.csv")
    assert not (set(FEATURES_NUM + FEATURES_CAT + [FEATURE_TEXTO]) & PROIBIDAS)
    return df


def _cortes(precos, n=N_FAIXAS):
    # quantis internos (n-1 cortes); com poucos produtos/empates algumas faixas podem ficar vazias
    return np.quantile(precos, [i / n for i in range(1, n)])


def dividir(df, semente=SEMENTE):
    """Retorna (treino, teste) já com a coluna 'faixa' (0..3), cortes por domínio só do treino."""
    tr, te = train_test_split(df, test_size=TAM_TESTE, random_state=semente, stratify=df.domain_id)
    tr, te = tr.copy(), te.copy()
    cortes = {d: _cortes(g.preco_mediana.values) for d, g in tr.groupby("domain_id")}
    for d_, parte in (("tr", tr), ("te", te)):
        parte["faixa"] = [int(np.searchsorted(cortes[dom], p, side="right"))
                          for dom, p in zip(parte.domain_id, parte.preco_mediana)]
    assert set(te.domain_id) <= set(tr.domain_id)
    return tr, te, cortes


if __name__ == "__main__":
    df = carregar()
    tr, te, _ = dividir(df)
    print("treino", len(tr), "teste", len(te), "dominios", df.domain_id.nunique())
    print("faixas treino", tr.faixa.value_counts(normalize=True).sort_index().round(3).to_dict())
    print("faixas teste ", te.faixa.value_counts(normalize=True).sort_index().round(3).to_dict())
