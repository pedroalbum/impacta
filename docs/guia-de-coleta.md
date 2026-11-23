# Guia prático: como buscar e explorar os dados

Passo a passo operacional. Cada comando aqui foi executado de verdade.
Para o *porquê* de cada decisão, ver `../AGENTS.md`.

- [Parte 1 — Preparar credenciais](#parte-1--preparar-credenciais)
- [Parte 2 — Coletar](#parte-2--coletar)
- [Parte 3 — Explorar os dados](#parte-3--explorar-os-dados)
- [Parte 4 — Consultar a API na mão](#parte-4--consultar-a-api-na-mão)
- [Parte 5 — Quando der erro](#parte-5--quando-der-erro)

---

## Parte 1 — Preparar credenciais

### 1.1 De onde vêm

Painel do **DevCenter** do Mercado Livre (não o do Mercado Pago — são registros
diferentes, mesma conta):

```
https://developers.mercadolivre.com.br/devcenter
```

Você precisa de dois valores: **`App ID`** (ou `client_id`) e **`Client Secret`**.

> **Atenção:** *Public Key* e *Access Token* do painel de **Mercado Pago** não
> servem. São de tokenização de checkout, não da API de marketplace. Se as rotas
> de marketplace derem 403 com token válido, é isso.

### 1.2 Habilitar os escopos — o passo que mais trava

No cadastro da aplicação, marque os escopos de **leitura** do Mercado Livre
(`urn:ml:*`). Sem eles o token é emitido normalmente e **todas** as rotas de
marketplace respondem 403. Esse erro parece bloqueio definitivo e é só um toggle.

### 1.3 Guardar em disco, fora do projeto

**Nunca** coloque o segredo em arquivo do projeto, nem em código, nem em commit.

```bash
mkdir -p ~/.config/meli && chmod 700 ~/.config/meli
printf 'SEU_APP_ID'       > ~/.config/meli/app_id
printf 'SEU_CLIENT_SECRET' > ~/.config/meli/secret
chmod 600 ~/.config/meli/app_id ~/.config/meli/secret
```

`printf` em vez de `echo` de propósito: não acrescenta `\n` ao segredo.

Alternativa por sessão, sem tocar o disco:

```bash
export MELI_CLIENT_ID='...'
export MELI_CLIENT_SECRET='...'
```

Os scripts procuram o ambiente primeiro e caem no arquivo depois.

### 1.4 Testar se funciona

```bash
curl -s -X POST https://api.mercadolibre.com/oauth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "grant_type=client_credentials&client_id=$(cat ~/.config/meli/app_id)&client_secret=$(cat ~/.config/meli/secret)" \
  | python3 -m json.tool
```

Esperado:

```json
{"access_token": "APP_USR-...", "token_type": "Bearer",
 "expires_in": 21600, "scope": "..."}
```

`expires_in: 21600` = **6 horas**. Não vem `refresh_token` e **não precisa**:
para renovar, repita este mesmo `POST`. Sem browser, sem `redirect_uri`.

Guardar o token para usar no `curl` das próximas partes:

```bash
curl -s -X POST https://api.mercadolibre.com/oauth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "grant_type=client_credentials&client_id=$(cat ~/.config/meli/app_id)&client_secret=$(cat ~/.config/meli/secret)" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])' \
  > ~/.config/meli/token
chmod 600 ~/.config/meli/token
export TOK=$(cat ~/.config/meli/token)
```

Conferir quantos escopos vieram — se for poucos e nenhum começar com `urn:ml:`,
volte ao passo 1.2:

```bash
curl -s "https://api.mercadolibre.com/users/me" -H "Authorization: Bearer $TOK" \
  | python3 -m json.tool | head -20
```

---

## Parte 2 — Coletar

**A ordem importa.** O segundo script depende do CSV que o primeiro gera.

### 2.1 Categorias — sem credencial

```bash
cd ~/meli-ml
python3 src/coleta/coleta_categorias.py
```

Gera `dados/categorias_mlb.csv` (150 registros). Roda **sem token de propósito**:
com token sem escopo, `domain_discovery` cai de 200 para 403. **Não adicione
`Authorization` a este script.**

Saída real:

```
registros: 150 | folhas: 52 | raizes: 18
```

Este CSV tem duas funções: é dado do relatório **e** é o **vocabulário de busca**
do próximo passo — `/products/search` exige o parâmetro `q`, e não existe rota
que enumere produtos sem termo.

### 2.2 Produtos — o dataset principal

```bash
export MELI_CLIENT_ID=$(cat ~/.config/meli/app_id)
export MELI_CLIENT_SECRET=$(cat ~/.config/meli/secret)
python3 src/coleta/coleta_produtos.py 25000
```

O argumento é o alvo de produtos únicos; o script **para antes** se os termos
acabarem. Gera `dados/produtos_mlb.csv`.

**Duração real: 8min04s** para 24.421 produtos. Se o seu terminal tiver timeout,
rode em background:

```bash
nohup python3 src/coleta/coleta_produtos.py 25000 > coleta.log 2>&1 &
tail -f coleta.log
```

24.421 é o teto deste vocabulário de 134 termos. Para passar disso, **amplie o
vocabulário, não o alvo** — `/trends/MLB/{categoria}` dá 40 termos populares por
categoria (Parte 4.6).

### 2.3 Valor — ranking de mais vendidos e preço

```bash
python3 src/coleta/coleta_valor.py
```

Gera `dados/valor_mlb.csv`. Três etapas: ranking por categoria, ficha de cada
produto ranqueado, preço agregado dos anúncios.

**Leia `dados-de-valor.md` antes de usar este CSV.** Resumo do que importa:
preço existe para uma fração dos produtos, **quantidade vendida e faturamento não
existem na API**, e esta é a única rota do projeto que devolve dado pessoal
(`seller_id`), que o script descarta na ingestão.

### 2.4 Ampliar além de 24 mil produtos

```bash
python3 -u src/coleta/coleta_expandida.py 80000 400
#                                       |     |
#                                       |     teto de termos novos a consultar
#                                       alvo de produtos
```

Gera `dados/produtos_mlb_expandido.csv` **sem tocar** no `produtos_mlb.csv`
validado.

**Por que isso funciona.** `/products/search` devolve no máximo 200 produtos por
termo (`limit`≤100, `offset`≤100). Isso parece um teto e é um teto **por termo** —
o volume total é função de **quantos termos distintos** você consulta. A primeira
coleta usou 134 nomes de categoria; existem 11.045 termos disponíveis sem coletar
nada novo (marcas do próprio CSV, `/trends`, palavras dos títulos).

**Use `-u`.** Sem ele o Python bufferiza e você não vê a curva de saturação
enquanto roda. E **não jogue em `| tail`** — o pipe segura tudo até o fim, erro que
este projeto cometeu e custou 20 minutos de cegueira.

A saída mostra o rendimento marginal:

```
 termos  produtos  ineditos  novos/termo    min
     25     27850      3429          137    1.4
     50     31406      6985          140    3.1
```

**É assim que você descobre o limite**, porque nenhum número oficial existe:
enquanto `novos/termo` fica estável, há espaço; quando cai forte, o vocabulário
saturou e mais termos não compram mais dados.

---

## Parte 2.5 — Qual CSV é qual

Três arquivos em `dados/`, com propósitos diferentes. **Confundi-los é o erro mais
provável deste projeto:**

| Arquivo | Linhas | O que é | Use para |
|---|---|---|---|
| `categorias_mlb.csv` | 150 | Árvore de categorias: `nome`, `raiz`, `profundidade`, `total_itens` | **Vocabulário de busca** do coletor; sanidade da taxonomia |
| `produtos_mlb.csv` | 24.421 | Produtos achados por `q=`: `nome`, `domain_id`, marca, atributos | **Treinar o classificador** `nome` -> `domain_id` |
| `valor_mlb.csv` | 1.218 | Mais vendidos com posição 1..20 + preço agregado | **Preço e popularidade** |

**Os dois últimos são quase disjuntos: só 14 produtos em comum.** Não são duas
amostras da mesma coisa, são **duas populações**:

```
produtos_mlb.csv  <- cauda longa. 50% inactive. So 23% dos active tem anuncio no ar
valor_mlb.csv     <- campeoes de venda. 100% active, 100% com preco
```

Consequências práticas:

- **Preço:** use `valor_mlb.csv` (cobertura 100%), não `produtos_mlb.csv` (11%).
- **Classificação de domínio:** use `produtos_mlb.csv` (1.412 domínios), não
  `valor_mlb.csv` (333 domínios, e só 16 com ≥10 exemplos após filtrar amplitude).
- **Popularidade:** só `valor_mlb.csv` diz algo. `produtos_mlb.csv` **não
  representa** o que vende, e nenhuma conclusão sobre vendas sai dele.

---

## Parte 3 — Explorar os dados

### 3.1 Primeiro olhar

```bash
python3 -c "
import pandas as pd
df = pd.read_csv('dados/produtos_mlb.csv')
print(df.shape)
print(df.dtypes)
print(df.head(3).to_string())
"
```

> **Nunca conte registros com `wc -l`.** Dois títulos contêm quebra de linha
> (escapada corretamente), então `wc -l` diz 24.423 para 24.421 registros. Só o
> parser de CSV acerta.

### 3.2 O rótulo e seu desbalanceamento

Esta é a análise que decide o modelo:

```bash
python3 -c "
import pandas as pd
df = pd.read_csv('dados/produtos_mlb.csv')
c = df['domain_id'].value_counts()
print(f'classes: {len(c)}')
print(f'com 1 exemplo: {(c==1).sum()}  ({(c==1).mean()*100:.0f}%)')
print()
print('efeito de cada corte minimo:')
for k in (1,2,5,10,20,50):
    ok = c[c>=k]
    print(f'  >={k:>2}: {len(ok):>4} classes, {ok.sum():>6} produtos '
          f'({ok.sum()/len(df)*100:.0f}% dos dados)')
print()
print(c.head(10).to_string())
"
```

### 3.3 Aplicar o corte e montar o split

O corte recomendado é **≥10 exemplos**: 357 classes, 21.659 produtos.

```bash
python3 -c "
import pandas as pd
from sklearn.model_selection import train_test_split
df = pd.read_csv('dados/produtos_mlb.csv')
c = df['domain_id'].value_counts()
df = df[df['domain_id'].isin(c[c>=10].index)]
print(f'apos corte: {len(df)} produtos, {df.domain_id.nunique()} classes')
# stratify exige >=2 exemplos por classe no split; o corte >=10 garante isso
tr, te = train_test_split(df, test_size=0.2, random_state=42, stratify=df['domain_id'])
print(f'treino {len(tr)} | teste {len(te)}')
print(f'classes no teste: {te.domain_id.nunique()} (deve igualar o treino)')
"
```

### 3.4 Texto de entrada

```bash
python3 -c "
import pandas as pd
df = pd.read_csv('dados/produtos_mlb.csv')
t = df['nome'].str.len()
print(t.describe().to_string())
print()
print('mais curtos:', df.loc[t.nsmallest(3).index,'nome'].tolist())
print()
print('palavras por titulo:', df['nome'].str.split().str.len().median())
"
```

Títulos de 3 caracteres existem. Decida se filtra por comprimento mínimo — e
registre a decisão.

### 3.5 Checar vazamento de rótulo antes de treinar

Vale rodar isto **antes** do primeiro treino. Se uma coluna prevê o rótulo quase
sozinha, ela é vazamento, não feature:

```bash
python3 -c "
import pandas as pd
df = pd.read_csv('dados/produtos_mlb.csv')
for col in ('marca','termo_busca'):
    g = df.groupby(col)['domain_id'].nunique()
    print(f'{col}: {g.median():.0f} dominios por valor (mediana)')
    print(f'  valores que apontam para 1 unico dominio: {(g==1).mean()*100:.0f}%')
"
```

Resultado real desta checagem:

```
marca      : mediana 1 dominio por valor  | 85% das marcas apontam para 1 unico dominio
termo_busca: mediana 11 dominios por valor|  8% dos termos apontam para 1 unico dominio
```

**`marca` é o vazamento mais grave** — 85% das marcas determinam o domínio
sozinhas, porque vêm de `attributes[]`, que a ML preenche já sabendo o domínio.
`termo_busca` vaza de forma mais fraca do que parece (mediana 11 domínios), mas
ainda reduz 1.412 classes para ~11, o que é forte demais para ser feature.

**Treine só com `nome`.** `marca` serve para análise de erro; `termo_busca`, para
auditar a cobertura da coleta.

### 3.6 Baseline completo, do CSV ao macro-F1

```bash
python3 -c "
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score, accuracy_score

df = pd.read_csv('dados/produtos_mlb.csv')
c = df['domain_id'].value_counts()
df = df[df['domain_id'].isin(c[c>=10].index)]
tr, te = train_test_split(df, test_size=0.2, random_state=42, stratify=df['domain_id'])

mod = make_pipeline(
    TfidfVectorizer(analyzer='char_wb', ngram_range=(3,5), min_df=2, sublinear_tf=True),
    LinearSVC(C=1.0, class_weight='balanced'))
mod.fit(tr['nome'], tr['domain_id'])
p = mod.predict(te['nome'])
print(f'classes    : {df.domain_id.nunique()}')
print(f'acuracia   : {accuracy_score(te.domain_id, p):.3f}  <- enganosa, nao relate so isto')
print(f'macro-F1   : {f1_score(te.domain_id, p, average=\"macro\"):.3f}  <- a metrica que vale')
"
```

Resultado real desta execução:

```
classes    : 357
treino/teste: 17327/4332
acuracia   : 0.914
macro-F1   : 0.852
tempo      : 11 segundos
```

`class_weight='balanced'` está aí porque as classes seguem desbalanceadas mesmo
após o corte (de 10 a 829 exemplos). Compare sempre as duas métricas: a distância
entre acurácia (0,914) e macro-F1 (0,852) **é** a medida do desbalanceamento — e é
por isso que relatar só a acurácia superestima o modelo.

### 3.7 Onde o modelo erra

Mais útil para o relatório que um número só:

```bash
python3 -c "
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
df = pd.read_csv('dados/produtos_mlb.csv')
c = df['domain_id'].value_counts(); df = df[df['domain_id'].isin(c[c>=10].index)]
tr, te = train_test_split(df, test_size=0.2, random_state=42, stratify=df['domain_id'])
mod = make_pipeline(TfidfVectorizer(analyzer='char_wb', ngram_range=(3,5), min_df=2),
                    LinearSVC(class_weight='balanced')).fit(tr['nome'], tr['domain_id'])
te = te.assign(pred=mod.predict(te['nome']))
err = te[te.pred != te.domain_id]
print(f'erros: {len(err)}/{len(te)}')
print()
print('confusoes mais frequentes:')
print((err.groupby(['domain_id','pred']).size()
         .sort_values(ascending=False).head(12).to_string()))
"
```

Resultado real (381 erros em 4.332):

```
MLB-DRILL_BITS                      -> MLB-DRILL_AND_SCREWDRIVER_BITS      6
MLB-MICROCONTROLLER_BOARDS          -> MLB-BATTERY_AND_CELL_BATTERIES...   4
MLB-ELBOW_SUPPORTS                  -> MLB-SPORTS_PROTECTION_ELBOW_PADS    4
MLB-NAUTICAL_CLEATS                 -> MLB-NAUTICAL_ROPES                  3
MLB-FOOTBALL_BALLS                  -> MLB-HANDBALL_BALLS                  3
```

Os pares confundidos são **semanticamente adjacentes**, e vários são ambiguidade
da própria taxonomia: "brocas" e "brocas e bits de parafusadeira" se sobrepõem de
fato. Isso é achado do trabalho, não defeito — argumentar com esta tabela na mão
vale mais que um décimo de macro-F1.

### 3.8 Explorar valor e ranking

```bash
python3 -c "
import pandas as pd
df = pd.read_csv('dados/valor_mlb.csv')
print(f'{len(df)} produtos ranqueados | com preco: {df.preco_mediana.notna().sum()}')
print()
print('preco mediano por posicao no ranking:')
print(df.groupby(pd.cut(df.posicao_ranking,[0,5,10,15,20]),observed=True)
        ['preco_mediana'].agg(['count','median']).to_string())
print()
print('amplitude de preco (indica anuncio mal agrupado):')
print(df['amplitude_pct'].describe().to_string())
print(f'  acima de 200%: {(df.amplitude_pct>200).sum()} produtos -> filtre antes de usar')
"
```

---

## Parte 4 — Consultar a API na mão

Todas exigem `export TOK=...` da Parte 1.4. Útil para sondar antes de escrever script.

### 4.1 Buscar produtos de catálogo

```bash
curl -s "https://api.mercadolibre.com/products/search?site_id=MLB&q=notebook&limit=5" \
  -H "Authorization: Bearer $TOK" \
  | python3 -c "
import json,sys
for p in json.load(sys.stdin)['results']:
    print(p['id'], '|', p['domain_id'], '|', p['name'][:55])"
```

`q` é **obrigatório**. `limit` máximo 100. **`offset` máximo 100** — acima disso
vem `400`, então o teto é **200 produtos por consulta**. `paging.total: 10000` é
fantasia. Para mais volume, varie `q`, não o `offset`.

Filtrar por domínio (junto com `q`, nunca sozinho):

```bash
curl -s "https://api.mercadolibre.com/products/search?site_id=MLB&q=notebook&domain_id=MLB-NOTEBOOKS&limit=3" \
  -H "Authorization: Bearer $TOK" | python3 -m json.tool | head -30
```

### 4.2 Ficha de um produto

```bash
curl -s "https://api.mercadolibre.com/products/MLB54982411" \
  -H "Authorization: Bearer $TOK" | python3 -m json.tool | head -40
```

### 4.3 Preço: os anúncios de um produto

```bash
curl -s "https://api.mercadolibre.com/products/MLB54982411/items" \
  -H "Authorization: Bearer $TOK" \
  | python3 -c "
import json,sys
d = json.load(sys.stdin)
print('anuncios:', d['paging']['total'])
for x in d['results'][:8]:
    print(f\"  R\$ {x['price']:>9} | {x['condition']:<4} | frete_gratis={(x.get('shipping') or {}).get('free_shipping')}\")"
```

**404 aqui é normal** — significa produto sem anúncio, e acontece em ~77% dos
`active` e em 100% dos `inactive`. Esta rota também devolve `seller_id` e
`seller_address`: **descarte na ingestão.**

### 4.4 Mais vendidos de uma categoria

```bash
curl -s "https://api.mercadolibre.com/highlights/MLB/category/MLB1051" \
  -H "Authorization: Bearer $TOK" | python3 -m json.tool | head -20
```

`query_data.highlight_type` é **`BEST_SELLER`**. Máximo **20 posições** — `limit`
é ignorado. Os `id` de `type: PRODUCT` são `product_id` de catálogo e juntam com
`produtos_mlb.csv`. Entradas `type: USER_PRODUCT` são anúncio de vendedor:
descarte.

### 4.5 Árvore de categorias

```bash
curl -s "https://api.mercadolibre.com/sites/MLB/categories" \
  -H "Authorization: Bearer $TOK" | python3 -m json.tool | head
curl -s "https://api.mercadolibre.com/categories/MLB1051" | python3 -m json.tool | head -25
```

A segunda funciona **sem token**.

### 4.6 Termos de busca populares — para ampliar o vocabulário

```bash
curl -s "https://api.mercadolibre.com/trends/MLB/MLB1051" \
  -H "Authorization: Bearer $TOK" \
  | python3 -c "
import json,sys
for t in json.load(sys.stdin)[:10]: print(' -', t['keyword'])"
```

40 termos por categoria. É **daqui** que se amplia a coleta além de 24.421.

### 4.7 O que NÃO funciona — não perca tempo

```bash
# busca de ANUNCIO: 403, e nenhum dos 34 escopos cobre
curl -s -o /dev/null -w '%{http_code}\n' \
  "https://api.mercadolibre.com/sites/MLB/search?q=notebook" -H "Authorization: Bearer $TOK"

# detalhe de anuncio: 403
curl -s -o /dev/null -w '%{http_code}\n' \
  "https://api.mercadolibre.com/items/MLB5963285546" -H "Authorization: Bearer $TOK"

# bulk: envelope 200, cada item 403 DENTRO. Leia o corpo, nao o status
curl -s "https://api.mercadolibre.com/items/bulk?ids=MLB5963285546" \
  -H "Authorization: Bearer $TOK" | python3 -m json.tool
```

---

## Parte 5 — Quando der erro

| O que você vê | O que significa | O que fazer |
|---|---|---|
| `{"error":"forbidden","message":"forbidden"}` | Não mandou credencial | Envie `Authorization: Bearer` |
| `{"message":"At least one policy returned UNAUTHORIZED."}` **sem** campo `error` | Token válido, **falta escopo** | Habilite os escopos `urn:ml:*` no DevCenter. Não é bloqueio definitivo |
| `401` | Token inválido ou vencido (6h) | Repita o `POST` da Parte 1.4. O endpoint **existe** — não conclua que foi removido |
| `400 Field 'keywords'... required` | Faltou `q` em `/products/search` | `q` é obrigatório; `domain_id` só filtra |
| `400 Invalid arguments` em `/products/search` | `offset` acima de 100 | Teto é 200 por consulta. Varie `q` |
| `404` em `/products/{id}/items` | Produto sem anúncio | Normal em ~77% dos ativos e 100% dos inativos |
| `200` no `/items/bulk` mas nada utilizável | Envelope 200, `status_code: 403` por item | Leia `status_code` de cada entrada |
| `429` | Rate limit | Backoff exponencial. Não há número oficial publicado |
| `domain_discovery` respondia 200 e passou a 403 | Você **adicionou** token sem escopo | **Remova** o `Authorization` dessa chamada |
| Página de doc com 200 e conteúdo inútil | A doc devolve 200 em página inexistente | Verifique o conteúdo, não o status |
| `wc -l` não bate com o número de registros | Títulos com quebra de linha | Conte com o parser de CSV |

### Regra que resume tudo

**Se a API não entrega o dado, a resposta é mudar o escopo do trabalho, não
raspar o site.** Scraping é proibido pela cláusula 7.6 dos Termos e o
`robots.txt` bloqueia crawlers de IA nominalmente.
