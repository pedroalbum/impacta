#!/usr/bin/env python3
"""Coleta produtos de CATALOGO do Mercado Livre via /products/search.

Por que /products/search e nao /sites/MLB/search:
  - /sites/MLB/search esta 403 mesmo com token (nenhum escopo cobre busca de anuncio);
  - /products/search responde 200, aceita q= texto livre e filtro domain_id;
  - produto de catalogo NAO tem vendedor, logo nao ha dado pessoal na resposta.
    Isso mantem o projeto fora da LGPD e longe da clausula 6.2 dos Termos.

Saida: um par (nome, domain_id) por linha = exatamente o (texto, rotulo) do
classificador de categoria descrito no AGENTS.md secao 7.

Credenciais: NUNCA no codigo. Le de MELI_CLIENT_ID/MELI_CLIENT_SECRET ou de
~/.config/meli/{app_id,secret}.
"""
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

BASE = "https://api.mercadolibre.com"
SITE = "MLB"
PAUSA = 0.25          # nao ha limite oficial publicado; ser conservador e barato
TIMEOUT = 25
LIMITE = 100          # maximo aceito por pagina
OFFSET_MAX = 100      # verificado empiricamente: offset > 100 devolve 400
CONF = Path("~/.config/meli").expanduser()
RAIZ = Path(__file__).resolve().parents[2]  # raiz do repositório (src/coleta/ -> raiz)


def credenciais():
    cid = os.getenv("MELI_CLIENT_ID") or _ler(CONF / "app_id")
    sec = os.getenv("MELI_CLIENT_SECRET") or _ler(CONF / "secret")
    if not (cid and sec):
        sys.exit(
            "Faltam credenciais. Use:\n"
            "  export MELI_CLIENT_ID=...  MELI_CLIENT_SECRET=...\n"
            f"ou grave em {CONF}/app_id e {CONF}/secret (chmod 600)."
        )
    return cid.strip(), sec.strip()


def _ler(p):
    try:
        return p.read_text().strip()
    except OSError:
        return None


def autenticar(cid, sec):
    """client_credentials: sem browser, sem redirect_uri, sem refresh_token.
    Token vale 6h; para renovar basta repetir este POST."""
    corpo = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": cid,
        "client_secret": sec,
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/oauth/token", data=corpo,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        tok = json.load(r)
    return tok["access_token"]


def get(token, path, tentativas=4):
    """Backoff reativo ao 429 — o limite oficial nao e publicado."""
    for t in range(tentativas):
        req = urllib.request.Request(BASE + path,
                                     headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 ** t)
                continue
            if e.code == 400:      # offset alto ou termo sem resultado
                return None
            print(f"  ! HTTP {e.code} em {path[:60]}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"  ! {type(e).__name__} em {path[:60]}", file=sys.stderr)
            time.sleep(1)
    return None


def termos():
    """Vocabulario de consulta = nomes das categorias ja coletadas.
    /products/search exige 'keywords'; nao ha como enumerar sem termo."""
    csv_cat = RAIZ / "dados" / "categorias_mlb.csv"
    if not csv_cat.exists():
        sys.exit(f"Rode coleta_categorias.py primeiro: {csv_cat} nao existe.")
    vistos, saida = set(), []
    with csv_cat.open() as f:
        for linha in csv.DictReader(f):
            nome = (linha.get("nome") or "").strip().lower()
            if len(nome) >= 4 and nome not in vistos:
                vistos.add(nome)
                saida.append(nome)
    return saida


def atributo(produto, chave):
    for a in produto.get("attributes") or []:
        if a.get("id") == chave:
            return a.get("value_name")
    return None


def coletar(token, lista_termos, alvo):
    produtos, ja = {}, set()
    for i, termo in enumerate(lista_termos, 1):
        if len(produtos) >= alvo:
            break
        for offset in (0, OFFSET_MAX):
            q = urllib.parse.quote(termo)
            d = get(token, f"/products/search?site_id={SITE}&q={q}"
                           f"&limit={LIMITE}&offset={offset}")
            time.sleep(PAUSA)
            if not d:
                break
            for p in d.get("results") or []:
                pid, nome, dom = p.get("id"), p.get("name"), p.get("domain_id")
                if not (pid and nome and dom) or pid in ja:
                    continue
                ja.add(pid)
                produtos[pid] = {
                    "product_id": pid,
                    "nome": nome,
                    "domain_id": dom,
                    "status": p.get("status"),
                    "marca": atributo(p, "BRAND"),
                    "modelo": atributo(p, "MODEL"),
                    "n_atributos": len(p.get("attributes") or []),
                    "n_variacoes": len(p.get("children_ids") or []),
                    "criado_em": (p.get("date_created") or "")[:10],
                    "termo_busca": termo,
                }
        if i % 10 == 0 or len(produtos) >= alvo:
            print(f"  {i:>3}/{len(lista_termos)} termos | {len(produtos)} produtos")
    return list(produtos.values())


def resumo(linhas):
    print(f"\n{'='*64}\nRESUMO\n{'='*64}")
    print(f"produtos unicos      : {len(linhas)}")
    doms = Counter(l["domain_id"] for l in linhas)
    print(f"dominios distintos   : {len(doms)}")
    print(f"com marca preenchida : {sum(1 for l in linhas if l['marca'])}")
    st = Counter(l["status"] for l in linhas)
    print(f"status               : {dict(st)}")

    comp = [len(l["nome"]) for l in linhas]
    atr = [l["n_atributos"] for l in linhas]
    def desc(v, rot):
        v = sorted(v)
        n = len(v)
        med = v[n // 2] if n else 0
        print(f"  {rot:<22} min={v[0] if n else 0:<5} "
              f"mediana={med:<5} media={sum(v)/n if n else 0:<8.1f} max={v[-1] if n else 0}")
    print("\ndistribuicoes:")
    desc(comp, "tamanho do titulo")
    desc(atr, "atributos por produto")

    print(f"\ntop 12 dominios (rotulo do classificador):")
    for dom, n in doms.most_common(12):
        print(f"  {n:>5}  {dom}")

    # desbalanceamento importa: metrica sera macro-F1, nao acuracia
    unicos = sum(1 for _, n in doms.items() if n == 1)
    print(f"\ndominios com 1 so exemplo: {unicos} de {len(doms)}"
          f"  ({100*unicos/len(doms):.0f}%)")
    print("-> distribuicao desbalanceada: avalie por macro-F1, nao acuracia.")


def main():
    alvo = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    cid, sec = credenciais()
    print(f"autenticando (client_credentials)...")
    token = autenticar(cid, sec)
    print(f"token ok\n")

    lista = termos()
    print(f"{len(lista)} termos de busca a partir de categorias_mlb.csv")
    print(f"alvo: {alvo} produtos unicos\n")

    linhas = coletar(token, lista, alvo)
    if not linhas:
        sys.exit("nada coletado.")

    saida = RAIZ / "dados" / "produtos_mlb.csv"
    saida.parent.mkdir(exist_ok=True)
    with saida.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    resumo(linhas)
    print(f"\nsalvo em {saida.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
