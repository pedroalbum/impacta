#!/usr/bin/env python3
"""Coleta dados de VALOR: ranking de mais vendidos + preco praticado.

O que existe e o que nao existe na API (medido em 28/09/2026):

  preco               SIM   /products/{id}/items -> price, original_price, shipping.cost
  quantidade vendida  NAO   sold_quantity nao existe em nenhuma rota alcancavel;
                            /items/{id} da 403 e /items/bulk da 403 por item
  faturamento         NAO   exigiria preco x quantidade; sem quantidade, qualquer
                            numero de faturamento seria inventado
  posicao de venda    SIM   /highlights/MLB/category/{cat} -> highlight_type
                            BEST_SELLER, posicoes 1..20. E ordinal, nao cardinal

Portanto: nao ha como calcular faturamento, mas HA como estudar "o que vende
mais" — como problema de ranking/classificacao, nao de regressao sobre receita.

ATENCAO - dado pessoal: /products/{id}/items devolve seller_id e seller_address.
Este script DESCARTA os dois na ingestao e guarda apenas agregados de preco.
Nunca gravar seller_id no CSV.

Saida: dados/valor_mlb.csv
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
from pathlib import Path

BASE = "https://api.mercadolibre.com"
SITE = "MLB"
PAUSA = 0.18
TIMEOUT = 25
CONF = Path("~/.config/meli").expanduser()
RAIZ = Path(__file__).resolve().parents[2]  # raiz do repositório (src/coleta/ -> raiz)


def _ler(p):
    try:
        return p.read_text().strip()
    except OSError:
        return None


def autenticar():
    cid = os.getenv("MELI_CLIENT_ID") or _ler(CONF / "app_id")
    sec = os.getenv("MELI_CLIENT_SECRET") or _ler(CONF / "secret")
    if not (cid and sec):
        sys.exit(f"Faltam credenciais: env MELI_CLIENT_ID/SECRET ou {CONF}/app_id e secret")
    corpo = urllib.parse.urlencode({"grant_type": "client_credentials",
                                    "client_id": cid, "client_secret": sec}).encode()
    req = urllib.request.Request(f"{BASE}/oauth/token", data=corpo,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)["access_token"]


def get(token, path, tentativas=4):
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
            return None          # 404 = sem anuncio; 403 = sem escopo
        except Exception:
            time.sleep(1)
    return None


def ranking(token):
    """Mais vendidos por categoria. 20 posicoes no maximo (limit e ignorado)."""
    csv_cat = RAIZ / "dados" / "categorias_mlb.csv"
    if not csv_cat.exists():
        sys.exit("Rode coleta_categorias.py primeiro.")
    with csv_cat.open() as f:
        cats = [(l["category_id"], l["nome"]) for l in csv.DictReader(f)]

    alvos = {}
    for i, (cid, nome) in enumerate(cats, 1):
        d = get(token, f"/highlights/{SITE}/category/{cid}")
        time.sleep(PAUSA)
        for c in (d or {}).get("content") or []:
            # USER_PRODUCT e anuncio de vendedor, nao produto de catalogo: descartar
            if c.get("type") != "PRODUCT":
                continue
            pid = c["id"]
            # um produto pode ranquear em varias categorias; guarda a melhor posicao
            if pid not in alvos or c["position"] < alvos[pid]["posicao"]:
                alvos[pid] = {"posicao": c["position"], "categoria_ranking": cid,
                              "nome_categoria": nome}
        if i % 25 == 0:
            print(f"  ranking {i}/{len(cats)} categorias | {len(alvos)} produtos")
    return alvos


def precos(token, pid):
    """Agrega os anuncios de um produto. DESCARTA seller_id e seller_address."""
    d = get(token, f"/products/{pid}/items")
    if not d:
        return None
    res = d.get("results") or []
    vals = [x["price"] for x in res if isinstance(x.get("price"), (int, float)) and x["price"] > 0]
    if not vals:
        return None
    fretes = [x for x in res if (x.get("shipping") or {}).get("free_shipping")]
    novos = [x for x in res if x.get("condition") == "new"]
    return {
        "n_anuncios": len(res),
        "preco_min": round(min(vals), 2),
        "preco_mediana": round(statistics.median(vals), 2),
        "preco_max": round(max(vals), 2),
        # amplitude relativa: mede se os anuncios sao do MESMO produto ou lixo agrupado
        "amplitude_pct": round((max(vals) - min(vals)) / min(vals) * 100, 1),
        "frete_gratis_pct": round(100 * len(fretes) / len(res), 1),
        "novos_pct": round(100 * len(novos) / len(res), 1),
    }


def main():
    token = autenticar()
    print("token ok\n")
    print("etapa 1/3 - ranking de mais vendidos")
    alvos = ranking(token)
    print(f"  {len(alvos)} produtos ranqueados\n")

    print("etapa 2/3 - nome e dominio de cada produto ranqueado")
    linhas = []
    for i, (pid, meta) in enumerate(alvos.items(), 1):
        p = get(token, f"/products/{pid}")
        time.sleep(PAUSA)
        if not p:
            continue
        linhas.append({
            "product_id": pid,
            "nome": p.get("name"),
            "domain_id": p.get("domain_id"),
            "status": p.get("status"),
            "posicao_ranking": meta["posicao"],
            "categoria_ranking": meta["categoria_ranking"],
            "nome_categoria": meta["nome_categoria"],
            "n_atributos": len(p.get("attributes") or []),
            "criado_em": (p.get("date_created") or "")[:10],
        })
        if i % 100 == 0:
            print(f"  {i}/{len(alvos)}")

    print(f"\netapa 3/3 - preco praticado ({len(linhas)} produtos)")
    com_preco = 0
    for i, l in enumerate(linhas, 1):
        pr = precos(token, l["product_id"])
        time.sleep(PAUSA)
        l.update(pr or {k: None for k in
                 ("n_anuncios", "preco_min", "preco_mediana", "preco_max",
                  "amplitude_pct", "frete_gratis_pct", "novos_pct")})
        if pr:
            com_preco += 1
        if i % 100 == 0:
            print(f"  {i}/{len(linhas)} | {com_preco} com preco")

    saida = RAIZ / "dados" / "valor_mlb.csv"
    with saida.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    resumo(linhas, com_preco)
    print(f"\nsalvo em {saida.relative_to(RAIZ)}")


def resumo(linhas, com_preco):
    print(f"\n{'='*64}\nRESUMO\n{'='*64}")
    print(f"produtos ranqueados       : {len(linhas)}")
    print(f"com preco obtido          : {com_preco}  ({100*com_preco/len(linhas):.0f}%)")
    print(f"dominios distintos        : {len({l['domain_id'] for l in linhas})}")
    pm = [l["preco_mediana"] for l in linhas if l["preco_mediana"]]
    if pm:
        pm.sort()
        print(f"\npreco mediano do produto (R$):")
        print(f"  min={pm[0]:.2f}  p25={pm[len(pm)//4]:.2f}  mediana={pm[len(pm)//2]:.2f}"
              f"  p75={pm[3*len(pm)//4]:.2f}  max={pm[-1]:.2f}")
    amp = sorted(l["amplitude_pct"] for l in linhas if l["amplitude_pct"] is not None)
    if amp:
        print(f"\namplitude de preco entre vendedores do mesmo produto (%):")
        print(f"  mediana={amp[len(amp)//2]:.0f}  p75={amp[3*len(amp)//4]:.0f}  max={amp[-1]:.0f}")
        ruins = sum(1 for a in amp if a > 200)
        print(f"  com amplitude > 200%: {ruins} de {len(amp)}  ({100*ruins/len(amp):.0f}%)")
        print("  -> amplitude alta indica anuncios MAL AGRUPADOS no produto.")
        print("     Filtre por amplitude antes de usar preco como alvo.")
    na = [l["n_anuncios"] for l in linhas if l["n_anuncios"]]
    if na:
        na.sort()
        print(f"\nanuncios por produto: min={na[0]} mediana={na[len(na)//2]} max={na[-1]}")


if __name__ == "__main__":
    main()
