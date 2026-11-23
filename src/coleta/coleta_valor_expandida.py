#!/usr/bin/env python3
"""Coleta dados de VALOR (preco) em escala, de duas populacoes distintas.

Por que duas fases, e por que a coluna 'origem' e obrigatoria:

  fase 'busca'   -> produtos do dataset de busca (produtos_mlb_expandido.csv) que
                    estao 'active'. Cobertura de preco medida: ~26%. E a populacao
                    que CASA com o dataset de 100 mil produtos: mesma distribuicao,
                    cauda longa inclusa. E a que serve para modelar preco.

  fase 'ranking' -> mais vendidos de /highlights. Cobertura 100%, mas 3 a 6 produtos
                    liquidos por categoria (36-46% das categorias devolvem 404,
                    22-25% dos produtos repetem entre pai e filho, 38-60% dos slots
                    sao USER_PRODUCT e vao fora). Populacao ENVIESADA: 100% active,
                    100% novos, e preco nao correlaciona com posicao no ranking.

Misturar as duas sem marcar a origem produz um dataset que ninguem consegue
interpretar depois. Daí a coluna.

LGPD/Termos: /products/{id}/items e a UNICA rota do projeto que devolve dado
pessoal (seller_id, seller_address). Descartados AQUI, na ingestao — nunca
chegam ao CSV. Guardamos so agregados de preco.

Credenciais: NUNCA no codigo. MELI_CLIENT_ID/MELI_CLIENT_SECRET ou
~/.config/meli/{app_id,secret}.

Uso:
  python3 scripts/coleta_valor_expandida.py busca   8000
  python3 scripts/coleta_valor_expandida.py ranking 7000
"""
import csv
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

BASE = "https://api.mercadolibre.com"
SITE = "MLB"
PAUSA = 0.12
TIMEOUT = 25
CONF = Path("~/.config/meli").expanduser()
RAIZ = Path(__file__).resolve().parents[2]  # raiz do repositório (src/coleta/ -> raiz)
ENTRADA = RAIZ / "dados" / "produtos_mlb_expandido.csv"
SAIDA = RAIZ / "dados" / "valor_mlb_expandido.csv"
ARVORE = Path("/tmp/arvore.json")

COLUNAS = ["product_id", "nome", "domain_id", "origem", "n_anuncios",
           "preco_min", "preco_mediana", "preco_max", "amplitude_pct",
           "frete_gratis_pct", "novos_pct", "posicao_ranking", "categoria_ranking"]

# Sem isto, "zero resultados" e indistinguivel de "a requisicao morreu". Foi
# exatamente o bug que produziu um falso paredao de saturacao na coleta anterior.
ERROS = Counter()


def _ler(p):
    try:
        return p.read_text().strip()
    except OSError:
        return None


def credenciais():
    cid = os.getenv("MELI_CLIENT_ID") or _ler(CONF / "app_id")
    sec = os.getenv("MELI_CLIENT_SECRET") or _ler(CONF / "secret")
    if not (cid and sec):
        sys.exit(f"Faltam credenciais: env ou {CONF}/app_id e {CONF}/secret (chmod 600).")
    return cid, sec


def autenticar(cid, sec):
    """client_credentials: sem browser, sem refresh_token. Vale 6h; renovar = repetir."""
    corpo = urllib.parse.urlencode({"grant_type": "client_credentials",
                                    "client_id": cid, "client_secret": sec}).encode()
    req = urllib.request.Request(
        f"{BASE}/oauth/token", data=corpo,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)["access_token"]


def get(estado, path, tentativas=4):
    """estado e um dict mutavel com token e credenciais, para reautenticar no meio
    da coleta: uma corrida de 50 mil requisicoes atravessa a validade de 6h."""
    for t in range(tentativas):
        req = urllib.request.Request(
            BASE + path, headers={"Authorization": f"Bearer {estado['token']}"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            ERROS[e.code] += 1
            if e.code == 429:
                time.sleep(2 ** t)
                continue
            if e.code in (401, 403):
                ERROS["reauth"] += 1
                try:
                    estado["token"] = autenticar(estado["cid"], estado["sec"])
                    continue
                except Exception:
                    time.sleep(2 ** t)
                    continue
            return None                      # 404 = produto sem anuncio vivo
        except Exception as e:
            ERROS[type(e).__name__] += 1
            time.sleep(1)
    return None


def ja_coletados():
    if not SAIDA.exists():
        return set()
    with SAIDA.open() as f:
        return {l["product_id"] for l in csv.DictReader(f)}


def agrega(estado, pid, nome, dom, origem, pos=None, cat=None):
    """Chama /products/{id}/items e devolve SO agregados. seller_id e
    seller_address existem na resposta e morrem nesta funcao."""
    d = get(estado, f"/products/{pid}/items")
    if not d:
        return None
    res = d.get("results") or []
    precos = [r["price"] for r in res
              if isinstance(r.get("price"), (int, float)) and r["price"] > 0]
    if not precos:
        return None
    gratis = sum(1 for r in res if (r.get("shipping") or {}).get("free_shipping"))
    novos = sum(1 for r in res if r.get("condition") == "new")
    mn, mx = min(precos), max(precos)
    return {
        "product_id": pid, "nome": nome, "domain_id": dom, "origem": origem,
        "n_anuncios": len(res),
        "preco_min": round(mn, 2),
        "preco_mediana": round(statistics.median(precos), 2),
        "preco_max": round(mx, 2),
        "amplitude_pct": round(100 * (mx - mn) / mn, 1) if mn else "",
        "frete_gratis_pct": round(100 * gratis / len(res), 1),
        "novos_pct": round(100 * novos / len(res), 1),
        "posicao_ranking": pos if pos is not None else "",
        "categoria_ranking": cat or "",
    }


def fila_busca(vistos):
    """Produtos 'active' do dataset de busca. Os 'inactive' tem cobertura de
    preco medida de 0% — pedir por eles e queimar requisicao."""
    if not ENTRADA.exists():
        sys.exit(f"{ENTRADA} nao existe. Rode coleta_expandida.py primeiro.")
    fila = []
    with ENTRADA.open() as f:
        for l in csv.DictReader(f):
            if l.get("status") == "active" and l["product_id"] not in vistos:
                fila.append((l["product_id"], l["nome"], l["domain_id"], None, None))
    return fila


def categorias():
    """Prefere a arvore completa (/tmp/arvore.json). Cai para o CSV de 150 se nao houver."""
    if ARVORE.exists():
        try:
            d = json.load(ARVORE.open())
            ids = list(d) if isinstance(d, dict) else [
                x.get("category_id") or x.get("id") for x in d]
            ids = [i for i in ids if i]
            if ids:
                print(f"  arvore completa: {len(ids)} categorias")
                return ids
        except Exception as e:
            print(f"  ! arvore.json ilegivel ({type(e).__name__}), caindo para o CSV")
    csv_cat = RAIZ / "dados" / "categorias_mlb.csv"
    with csv_cat.open() as f:
        ids = [l["category_id"] for l in csv.DictReader(f)]
    print(f"  amostra do CSV: {len(ids)} categorias (arvore.json ausente)")
    return ids


def fila_ranking(estado, vistos, alvo):
    """Mais vendidos por categoria. USER_PRODUCT nao serve (nao e produto de
    catalogo); duplicatas entre pai e filho saem pelo 'vistos'."""
    fila, locais, cats = [], set(vistos), categorias()
    for i, cid in enumerate(cats, 1):
        if len(fila) >= alvo:
            break
        d = get(estado, f"/highlights/{SITE}/category/{cid}")
        time.sleep(PAUSA)
        if not d:
            continue
        for x in d.get("content") or []:
            pid = x.get("id")
            if x.get("type") != "PRODUCT" or not pid or pid in locais:
                continue
            locais.add(pid)
            fila.append((pid, None, None, x.get("position"), cid))
        if i % 250 == 0:
            print(f"  ranking: {i}/{len(cats)} categorias | fila {len(fila)}"
                  f" | erros {dict(ERROS)}")
    return fila


def grava(linhas, primeira):
    """Append incremental: uma corrida de horas nao pode perder tudo no fim."""
    SAIDA.parent.mkdir(exist_ok=True)
    novo = primeira and not SAIDA.exists()
    with SAIDA.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS)
        if novo:
            w.writeheader()
        w.writerows(linhas)


def coletar(estado, fila, origem, alvo):
    feitos, buffer, t0 = 0, [], time.time()
    primeira = not SAIDA.exists()
    for i, (pid, nome, dom, pos, cat) in enumerate(fila, 1):
        if feitos >= alvo:
            break
        if nome is None:                     # veio do ranking: buscar nome e dominio
            p = get(estado, f"/products/{pid}")
            time.sleep(PAUSA)
            if p:
                nome, dom = p.get("name"), p.get("domain_id")
        r = agrega(estado, pid, nome or "", dom or "", origem, pos, cat)
        time.sleep(PAUSA)
        if r and r["domain_id"]:
            buffer.append(r)
            feitos += 1
        if len(buffer) >= 200:
            grava(buffer, primeira)
            primeira = False
            buffer = []
        if i % 1000 == 0:
            mins = (time.time() - t0) / 60
            print(f"  {i}/{len(fila)} tentados | {feitos} com preco "
                  f"({100*feitos/i:.0f}%) | {mins:.0f} min | erros {dict(ERROS)}")
    if buffer:
        grava(buffer, primeira)
    return feitos


def resumo():
    with SAIDA.open() as f:
        linhas = list(csv.DictReader(f))
    print(f"\n{'='*66}\nRESUMO — {SAIDA.name}\n{'='*66}")
    print(f"registros            : {len(linhas)}")
    print(f"por origem           : {dict(Counter(l['origem'] for l in linhas))}")
    doms = Counter(l["domain_id"] for l in linhas)
    print(f"dominios distintos   : {len(doms)}")
    # este e o numero que decide se da modelo, nao a contagem de linhas
    for corte in (10, 30, 50, 100):
        n = sum(1 for _, c in doms.items() if c >= corte)
        print(f"  dominios com >={corte:<4}: {n}")
    med = sorted(float(l["preco_mediana"]) for l in linhas if l["preco_mediana"])
    if med:
        q = lambda p: med[int(p * (len(med) - 1))]
        print(f"\npreco mediano (R$)   : p10={q(.10):.2f} p25={q(.25):.2f} "
              f"p50={q(.50):.2f} p75={q(.75):.2f} p90={q(.90):.2f}")
    amp = sorted(float(l["amplitude_pct"]) for l in linhas if l["amplitude_pct"])
    if amp:
        q = lambda p: amp[int(p * (len(amp) - 1))]
        print(f"amplitude (%)        : p25={q(.25):.0f} p50={q(.50):.0f} "
              f"p75={q(.75):.0f} p90={q(.90):.0f}")
    print(f"\nerros por tipo       : {dict(ERROS)}")
    print("-> 404 aqui e esperado: produto de catalogo sem anuncio vivo.")


def main():
    fase = sys.argv[1] if len(sys.argv) > 1 else "busca"
    alvo = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    if fase not in ("busca", "ranking"):
        sys.exit("fase deve ser 'busca' ou 'ranking'")
    cid, sec = credenciais()
    estado = {"cid": cid, "sec": sec, "token": autenticar(cid, sec)}
    print(f"token ok | fase={fase} | alvo={alvo}")

    vistos = ja_coletados()
    print(f"ja no CSV: {len(vistos)} produtos (nao serao repetidos)")

    if fase == "busca":
        fila = fila_busca(vistos)
        print(f"fila: {len(fila)} produtos 'active' ineditos")
        print(f"cobertura esperada ~26% -> alvo pede ~{alvo / 0.26:.0f} requisicoes\n")
    else:
        fila = fila_ranking(estado, vistos, alvo * 2)
        print(f"fila: {len(fila)} produtos ranqueados ineditos")
        print("cobertura esperada ~100%\n")

    if not fila:
        sys.exit("fila vazia: nada a coletar.")
    feitos = coletar(estado, fila, fase, alvo)
    print(f"\n{feitos} registros novos nesta rodada")
    resumo()
    print(f"\nsalvo em {SAIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
