#!/usr/bin/env python3
"""Amplia o dataset alem dos 24.421 produtos ampliando o VOCABULARIO de busca.

Por que isso funciona:
  /products/search exige q= e devolve no maximo 200 produtos por termo
  (limit<=100, offset<=100). Logo o volume NAO e funcao da paginacao, e sim do
  numero de termos distintos consultados. Mais termos = mais produtos.

Fontes de vocabulario, em ordem de rendimento medido:
  1. marcas ja coletadas   -> 160 ineditos/termo, 97% de novidade (n=40 medido)
  2. nomes de categoria    -> 194/termo (foi o vocabulario da 1a coleta)
  3. /trends/MLB/{cat}     -> 40 termos por categoria, sao termos de BUSCA real
  4. palavras frequentes dos titulos ja coletados

Imprime a curva de saturacao a cada BLOCO termos, que e a unica forma honesta de
responder "qual e o limite": o teto nao esta documentado, entao se mede.

Uso:
  python3 -u scripts/coleta_expandida.py [alvo_de_produtos] [max_termos]
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
PAUSA = 0.2
TIMEOUT = 25
LIMITE = 100
OFFSET_MAX = 100      # verificado: offset>100 devolve 400
BLOCO = 25            # de quantos em quantos termos reportar a curva
CONF = Path("~/.config/meli").expanduser()
RAIZ = Path(__file__).resolve().parents[2]  # raiz do repositório (src/coleta/ -> raiz)
ENTRADA = RAIZ / "dados" / "produtos_mlb.csv"
SAIDA = RAIZ / "dados" / "produtos_mlb_expandido.csv"


def credenciais():
    cid = os.getenv("MELI_CLIENT_ID") or _ler(CONF / "app_id")
    sec = os.getenv("MELI_CLIENT_SECRET") or _ler(CONF / "secret")
    if not (cid and sec):
        sys.exit(f"Faltam credenciais: env ou {CONF}/{{app_id,secret}} (chmod 600).")
    return cid.strip(), sec.strip()


def _ler(p):
    try:
        return p.read_text().strip()
    except OSError:
        return None


def autenticar(cid, sec):
    corpo = urllib.parse.urlencode({"grant_type": "client_credentials",
                                    "client_id": cid, "client_secret": sec}).encode()
    req = urllib.request.Request(f"{BASE}/oauth/token", data=corpo,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)["access_token"]


ERROS = Counter()      # por que uma requisicao falhou: sem isso, "zero resultados"
                       # e indistinguivel de "a requisicao morreu". Foi o bug que
                       # produziu um falso paredao de saturacao no termo 225.


def get(estado, path, tentativas=4):
    """estado e um dict mutavel com 'token' e as credenciais, para permitir
    reautenticar no meio da coleta quando o token cai."""
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
                # token caiu ou foi invalidado: reautenticar e tentar de novo.
                # client_credentials nao tem refresh_token — renovar e repetir o POST.
                ERROS["reauth"] += 1
                try:
                    estado["token"] = autenticar(estado["cid"], estado["sec"])
                    continue
                except Exception:
                    time.sleep(2 ** t)
                    continue
            return None
        except Exception as e:
            ERROS[type(e).__name__] += 1
            time.sleep(1)
    return None


def existentes():
    """Le o CSV mais completo disponivel: continua de onde a ultima corrida parou,
    em vez de recomecar. Serve de base de deduplicacao E de vocabulario."""
    fonte = SAIDA if SAIDA.exists() else ENTRADA
    if not fonte.exists():
        sys.exit(f"Rode coleta_produtos.py primeiro: {ENTRADA} nao existe.")
    with fonte.open() as f:
        linhas = list(csv.DictReader(f))
    print(f"base: {fonte.name} ({len(linhas)} produtos)")
    return linhas


def vocabulario(estado, base):
    """Monta a fila de termos novos, na ordem de rendimento medido."""
    usados = {(r.get("termo_busca") or "").strip().lower() for r in base}
    fila, vistos = [], set(usados)

    def add(t, origem):
        t = (t or "").strip().lower()
        if len(t) >= 4 and t not in vistos:
            vistos.add(t)
            fila.append((t, origem))

    # 1. marcas com >=5 produtos: marcas reais, nao ruido de digitacao
    marcas = Counter((r.get("marca") or "").strip().lower()
                     for r in base if (r.get("marca") or "").strip())
    for m, n in marcas.most_common():
        if n >= 5:
            add(m, "marca")

    # 2. termos de busca reais do site, por categoria
    cats = RAIZ / "dados" / "categorias_mlb.csv"
    if cats.exists():
        with cats.open() as f:
            ids = [l["category_id"] for l in csv.DictReader(f) if l.get("category_id")]
        for cid in ids[:40]:
            d = get(estado, f"/trends/{SITE}/{cid}")
            time.sleep(PAUSA)
            for t in (d or [])[:40]:
                add(t.get("keyword"), "trend")

    # 3. palavras frequentes dos titulos: cauda de vocabulario
    pal = Counter()
    for r in base:
        for w in (r.get("nome") or "").lower().split():
            w = "".join(c for c in w if c.isalpha())
            if len(w) >= 5:
                pal[w] += 1
    for w, n in pal.most_common(1500):
        if n >= 20:
            add(w, "palavra")

    # marcas menos frequentes ficam no fim: rendimento menor, mas existem 10 mil
    for m, n in marcas.most_common():
        if n < 5:
            add(m, "marca_rara")
    return fila


def atributo(p, chave):
    for a in p.get("attributes") or []:
        if a.get("id") == chave:
            return a.get("value_name")
    return None


def coletar(estado, fila, base, alvo, max_termos):
    produtos = {r["product_id"]: r for r in base}
    inicial = len(produtos)
    curva = []
    t0 = time.time()
    print(f"base inicial: {inicial} produtos | fila: {len(fila)} termos novos")
    print(f"alvo: {alvo} | teto de termos: {max_termos}\n")
    print(f"{'termos':>7} {'produtos':>9} {'ineditos':>9} {'novos/termo':>12} "
          f"{'min':>6}  erros")
    print("-" * 62)

    for i, (termo, origem) in enumerate(fila[:max_termos], 1):
        antes = len(produtos)
        for offset in (0, OFFSET_MAX):
            d = get(estado, f"/products/search?site_id={SITE}"
                           f"&q={urllib.parse.quote(termo)}"
                           f"&limit={LIMITE}&offset={offset}")
            time.sleep(PAUSA)
            if not d:
                break
            for p in d.get("results") or []:
                pid, nome, dom = p.get("id"), p.get("name"), p.get("domain_id")
                if not (pid and nome and dom) or pid in produtos:
                    continue
                produtos[pid] = {
                    "product_id": pid, "nome": nome, "domain_id": dom,
                    "status": p.get("status"),
                    "marca": atributo(p, "BRAND"), "modelo": atributo(p, "MODEL"),
                    "n_atributos": len(p.get("attributes") or []),
                    "n_variacoes": len(p.get("children_ids") or []),
                    "criado_em": (p.get("date_created") or "")[:10],
                    "termo_busca": termo,
                }
            if len(d.get("results") or []) < LIMITE:
                break          # nao ha 2a pagina: economiza uma requisicao
        if i % BLOCO == 0:
            ineditos = len(produtos) - inicial
            taxa = (len(produtos) - antes)
            curva.append((i, len(produtos), ineditos))
            print(f"{i:>7} {len(produtos):>9} {ineditos:>9} "
                  f"{ineditos/i:>12.0f} {(time.time()-t0)/60:>6.1f}  "
                  f"{dict(ERROS) if ERROS else '-'}")
        if len(produtos) >= alvo:
            print(f"\nalvo de {alvo} alcancado no termo {i}")
            break
    return list(produtos.values()), curva, inicial


def resumo(linhas, curva, inicial):
    print(f"\n{'='*64}\nRESUMO\n{'='*64}")
    print(f"produtos: {inicial} -> {len(linhas)}  (+{len(linhas)-inicial})")
    doms = Counter(l["domain_id"] for l in linhas)
    print(f"dominios distintos: {len(doms)}")
    st = Counter(l["status"] for l in linhas)
    print(f"status: {dict(st)}")

    if len(curva) >= 2:
        print("\n-- curva de saturacao: ineditos por termo, por bloco --")
        ant = (0, inicial, 0)
        for i, tot, ined in curva:
            delta_t = i - ant[0]
            delta_p = tot - ant[1]
            print(f"  termos {ant[0]+1:>4}-{i:<4} -> +{delta_p:>5} produtos "
                  f"({delta_p/delta_t:>5.0f} por termo)")
            ant = (i, tot, ined)
        print("  -> se 'por termo' cai forte, o vocabulario esta saturando;")
        print("     se fica estavel, ainda ha espaco e o limite nao foi atingido.")
        print("  -> se cai a ZERO de uma vez, NAO e saturacao: e falha. Veja os erros.")
    if ERROS:
        print(f"\nerros por tipo: {dict(ERROS)}")
        print("  429=rate limit  401/403=token caiu (reautenticado)  400=termo invalido")
    else:
        print("\nnenhum erro de requisicao.")

    cortes = [(n, sum(1 for _, v in doms.items() if v >= n)) for n in (1, 2, 5, 10, 20, 50)]
    print("\n-- classes treinaveis por corte minimo --")
    for n, q in cortes:
        prods = sum(v for _, v in doms.items() if v >= n)
        print(f"  >={n:<3} {q:>5} classes  {prods:>7} produtos")


def main():
    alvo = int(sys.argv[1]) if len(sys.argv) > 1 else 60000
    max_termos = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    cid, sec = credenciais()
    estado = {"cid": cid, "sec": sec, "token": autenticar(cid, sec)}
    print("token ok")
    base = existentes()
    fila = vocabulario(estado, base)
    print(f"vocabulario por origem: {Counter(o for _, o in fila)}\n")

    linhas, curva, inicial = coletar(estado, fila, base, alvo, max_termos)
    SAIDA.parent.mkdir(exist_ok=True)
    with SAIDA.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    resumo(linhas, curva, inicial)
    print(f"\nsalvo em {SAIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
