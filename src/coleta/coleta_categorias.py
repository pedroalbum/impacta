"""Coleta a arvore de categorias do Mercado Livre sem credenciais.

Apenas dois endpoints do ML respondem sem Bearer token (verificado em 28/09/2026):
  GET /categories/{id}
  GET /sites/{site}/domain_discovery/search?q=
Este script usa os dois: semeia category_ids via domain_discovery e percorre
a arvore em largura via /categories/{id}.
"""
from __future__ import annotations

import time
from collections import deque

import pandas as pd
import requests

BASE = "https://api.mercadolibre.com"
SITE = "MLB"
PAUSA = 0.25  # nao ha limite oficial publicado; ser conservador e barato
TIMEOUT = 20

TERMOS_SEMENTE = [
    "notebook", "geladeira", "tenis corrida", "cafeteira", "livro",
    "furadeira", "racao gato", "perfume", "bicicleta", "monitor",
]


def sessao() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "meli-ml/0.1 (pesquisa academica)"
    return s


def get(s: requests.Session, path: str, **params) -> dict | list | None:
    r = s.get(f"{BASE}{path}", params=params or None, timeout=TIMEOUT)
    if r.status_code == 429:
        time.sleep(5.0)
        r = s.get(f"{BASE}{path}", params=params or None, timeout=TIMEOUT)
    if r.status_code != 200:
        print(f"  ! {r.status_code} {path}")
        return None
    return r.json()


def semear(s: requests.Session) -> set[str]:
    """domain_discovery devolve o category_id inferido para um termo de busca."""
    ids: set[str] = set()
    for termo in TERMOS_SEMENTE:
        dados = get(s, f"/sites/{SITE}/domain_discovery/search", q=termo)
        for d in dados or []:
            if cid := d.get("category_id"):
                ids.add(cid)
        time.sleep(PAUSA)
    return ids


def coletar(s: requests.Session, sementes: set[str], alvo: int = 150) -> list[dict]:
    fila = deque(sementes)
    vistos: set[str] = set()
    linhas: list[dict] = []

    while fila and len(linhas) < alvo:
        cid = fila.popleft()
        if cid in vistos:
            continue
        vistos.add(cid)

        cat = get(s, f"/categories/{cid}")
        time.sleep(PAUSA)
        if not cat:
            continue

        caminho = cat.get("path_from_root") or []
        filhos = cat.get("children_categories") or []
        # Enfileira a raiz do caminho tambem: /sites/MLB/categories exige token,
        # entao path_from_root e a unica via publica para chegar as raizes.
        for no in caminho:
            if no.get("id") not in vistos:
                fila.append(no["id"])
        for f in filhos:
            if f.get("id") not in vistos:
                fila.append(f["id"])

        linhas.append({
            "category_id": cat.get("id"),
            "nome": cat.get("name"),
            "raiz": caminho[0]["name"] if caminho else None,
            "profundidade": len(caminho),
            "total_itens": cat.get("total_items_in_this_category"),
            "n_filhos": len(filhos),
            "folha": len(filhos) == 0,
            "permalink": cat.get("permalink"),
        })
        print(f"  [{len(linhas):>3}] {cat.get('id'):<12} {str(cat.get('name'))[:40]}")

    return linhas


def main() -> None:
    s = sessao()
    print("1/3 semeando categorias via domain_discovery...")
    sementes = semear(s)
    print(f"    {len(sementes)} category_ids semente\n")

    print("2/3 percorrendo a arvore de categorias...")
    linhas = coletar(s, sementes)

    df = pd.DataFrame(linhas)
    destino = "dados/categorias_mlb.csv"
    df.to_csv(destino, index=False)
    print(f"\n3/3 {len(df)} registros -> {destino}\n")

    print("=" * 62)
    print(f"registros: {len(df)} | folhas: {int(df['folha'].sum())} | raizes: {df['raiz'].nunique()}")
    print("\n-- describe() --")
    print(df[["profundidade", "total_itens", "n_filhos"]].describe().round(1).to_string())
    print("\n-- top 10 categorias por volume de itens --")
    top = df.nlargest(10, "total_itens")[["category_id", "nome", "raiz", "total_itens"]]
    print(top.to_string(index=False))
    print("\n-- itens por raiz --")
    print(df.groupby("raiz")["total_itens"].agg(["count", "sum"]).sort_values("sum", ascending=False).head(10).to_string())


if __name__ == "__main__":
    main()
