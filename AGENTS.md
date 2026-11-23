# AGENTS.md — Projeto de ML com dados do Mercado Livre

Contrato operacional para quem chega sem contexto. **Leia antes de escrever
código.** Há restrições de API e de contrato que invalidam a abordagem óbvia.

**O que é:** trabalho acadêmico de faculdade. Não é produto comercial, não há
CNPJ, não há orçamento de cloud. Máquina local macOS. **Não superdimensione.**

---

## Resumo de 60 segundos

| | |
|---|---|
| **A coleta funciona** | 24.421 produtos (baseline validado) e **100.129** (`produtos_mlb_expandido.csv`) |
| **O teto foi MEDIDO** | 100.129 produtos. Não é limite da API: é do vocabulário, e a curva nunca cedeu. Ver §1 |
| **A árvore tem 12.233 categorias** | Não as 150 do CSV de amostra. 10.630 folhas, profundidade 7 |
| **A tarefa pendente** | **Treinar.** Os dados já estão em disco |
| **O caso de uso** | Classificar `nome` -> `domain_id` |
| **Métrica** | macro-F1. Nunca acurácia — ver §7 |
| **Preço** | **99% dos mais vendidos, 22% dos `active` da busca, 0% dos `inactive`.** Ver §5 |
| **Quantidade vendida e faturamento** | **Não existem.** Ver §5 — não invente |
| **Scraping** | Proibido por contrato. Ver §6 |

Documentos, na ordem em que servem:

1. **`docs/guia-de-coleta.md`** — passo a passo para coletar e explorar. Comece aqui se a tarefa é operar.
2. **`docs/dados-de-valor.md`** — o que há de preço, venda e receita, e o que fazer com isso.
3. **`docs/viabilidade-mercadolivre-ml.md`** — levantamento completo com fontes primárias. É o entregável.
4. **`docs/fonte-de-dados.md`** — por que a API e não um dataset pronto.

---

## 1. O mapa da API

Duas camadas. **Sem token**, 2 rotas respondem. **Com token de aplicação com
escopos `urn:ml:*`**, quase tudo abre — menos a busca de anúncio.

```
SEM TOKEN
  200  /categories/{id}
  200  /sites/MLB/domain_discovery/search?q=
  403  todo o resto

COM TOKEN (client_credentials, 34 escopos)
  200  /products/search?site_id=MLB&q=...     <- busca de CATALOGO. O alicerce
  200  /products/{id}                          <- ficha: nome, dominio, atributos
  200  /products/{id}/items                    <- anuncios do produto: PRECO
  200  /highlights/MLB/category/{cat}          <- MAIS VENDIDOS, posicoes 1..20
  200  /trends/MLB  e  /trends/MLB/{cat}       <- 40 termos populares
  200  /sites/MLB/categories                   <- arvore completa
  200  /categories/{id}/attributes
  200  /catalog_domains/{domain_id}
  403  /sites/MLB/search                       <- busca de ANUNCIO: fechada
  403  /items/{id}                             <- detalhe de anuncio: fechado
  200  /items/bulk?ids=  ARMADILHA: envelope 200, cada item 403 dentro
```

### `/items/bulk` mente sobre o status

O HTTP é `200`, mas cada entrada do corpo traz `"status_code": 403`. Verificado:

```json
[{"id": "MLB5963285546", "status_code": 403,
  "error": {"message": "Access to the requested resource is forbidden"}}]
```

**Nunca conclua acesso a partir do status do envelope.** Leia `status_code` de
cada item. (Este arquivo já documentou `/items/bulk` como funcional; estava
errado, porque só o envelope foi conferido.)

### Por que `/products/search` e não a busca de anúncio

`/sites/MLB/search` está fechada e nenhum dos 34 escopos a cobre.
`/products/search` responde 200 e **é preferível**, não um consolo:

1. **Não tem vendedor.** Produto de catálogo é ficha canônica, não oferta. A
   resposta não traz `seller_id` nem `nickname` — não há dado pessoal para
   descartar. O projeto fica fora da LGPD por ausência de objeto.
2. **Título canônico.** Cem vendedores anunciando o mesmo notebook viram **um**
   produto, em vez de cem quase-duplicatas.
3. **Já vem rotulado** com `domain_id`. É o rótulo do classificador, de graça.

### Limites medidos de `/products/search`

```
limit    maximo 100   (limit=200 devolve lista vazia)
offset   maximo 100   (offset=100 -> 200 OK; offset=101 -> 400 Invalid arguments)
```

Teto real: **200 produtos por consulta**. `paging.total` reporta `10000` e é
fantasia — o teto de `offset` manda, e `search_type=scan` não existe nesta rota.

**A alavanca é variar a consulta, não paginar.** O volume é função do vocabulário
de busca: 134 termos renderam 24.421 únicos (~194 por termo).

### O teto não era 24 mil. Foi medido: 100.129 produtos

O limite de 200 é **por termo**, não do dataset. `produtos_mlb_expandido.csv` tem
**100.129 produtos e 2.724 domínios**, coletados com 275 termos além dos 134
originais.

A curva de saturação, impressa pelo próprio coletor, **nunca cedeu**:

```
termos    1-25   -> + 3104 produtos (124 por termo)
termos   76-100  -> + 3951 produtos (158 por termo)
termos  226-250  -> + 4074 produtos (163 por termo)   <- o MAIOR de todos
termos  251-275  -> + 3971 produtos (159 por termo)
```

O último bloco rendeu **mais** que o primeiro. Vocabulário ainda disponível: ~12.700
termos não usados, de um total de 11.045 catalogados mais os descobertos no caminho
(762 marcas com ≥5 produtos, 638 de `/trends/MLB/{cat}`, 692 palavras frequentes dos
títulos, 8.953 marcas raras). **Não se sabe onde está o teto real — sabe-se que não é
aqui.**

Classes treináveis por corte, no dataset de 100 mil:

| Corte | Classes | Produtos |
|---|---|---|
| ≥5 | 1.592 | 97.956 |
| **≥10** | **1.144** | 94.969 |
| ≥20 | 786 | 89.967 |
| ≥50 | 450 | 79.520 |

Contra 357 classes ≥10 no dataset de 24 mil: **3,2× mais classes utilizáveis**. Mas
atenção: **o baseline de macro-F1 0,852 foi medido nas 357 classes do CSV de 24 mil,
não aqui.** Com 1.144 classes o problema é mais difícil; o número não transfere.

**Uma falha que custou uma rodada, registrada para não repetir:** a primeira tentativa
de expansão relatou `+0 produtos` a partir do termo 225 e eu interpretei como
saturação. Era falha silenciosa — `get()` devolvia `None` sem registrar o motivo.
Reteste ao vivo nos termos "estéreis" devolveu 98-100 resultados cada. Depois de
instrumentar com um contador de erros, os mesmos termos renderam o **maior** bloco da
curva. **Uma queda a zero de uma vez não é saturação: é falha.** Saturação é declive,
não precipício.

**Cuidado metodológico, e ele é o mais importante desta seção:** ampliar **não
corrige** o viés do §4. Mais termos trazem mais cauda longa, não mais campeões de
venda. Ampliar ajuda nas classes com poucos exemplos; **não compra
representatividade.**

### `q=` é obrigatório

Sem ele: `400 Field 'keywords', 'product_identifier', 'parent...' required`.
**Não existe rota que enumere produtos sem termo de busca.** Por isso
`coleta_produtos.py` depende do CSV de categorias — é de lá que sai o vocabulário.
`domain_id` funciona como filtro **adicional**, nunca sozinho.

---

## 2. Existem DOIS 403 diferentes. Saber distinguir economiza dias

```
sem token    403  {"error":"forbidden","message":"forbidden"}
com token    403  {"message":"At least one policy returned UNAUTHORIZED."}
                  ^ sem campo "error" — token OK, falta ESCOPO no app
```

`forbidden/forbidden` = não mandou credencial.
`policy returned UNAUTHORIZED` = credencial válida **sem permissão** — e isso é
**configuração no DevCenter**, não impossibilidade. Foi exatamente o que travou
este projeto por um dia inteiro antes de se revelar um toggle de escopo.

**Ter token não é ter acesso.** `401` = token inválido, mas o endpoint **existe** —
não conclua remoção a partir de `401`. `400` em `/products/search` é quase sempre
`offset` alto, não erro de código.

### ARMADILHA: mandar token onde não precisa pode piorar

Com token **sem** escopo `urn:ml:*`:

```
/sites/MLB/domain_discovery/search    sem token = 200    com token = 403
```

A policy avalia o escopo e nega em vez de cair na regra pública. Por isso
`coleta_categorias.py` roda **sem** `Authorization`, de propósito. **Não
"melhore" o script adicionando token.**

---

## 3. Credenciais

`client_credentials` **funciona**, ao contrário do que a documentação afirma:

```
HTTP 200  access_token: APP_USR-...  expires_in: 21600 (6h)  sem refresh_token
```

Consequência: **sem browser, sem `redirect_uri`, sem rotação de token.** Renovar
é repetir o mesmo `POST`. Uma aplicação sem `redirect_uri` configurado serve para
`client_credentials`; ela só não serve para `authorization_code`.

**Regras, sem exceção:**

- **Nunca comite credencial nem token. Nunca escreva o segredo em arquivo do projeto.**
- Leia de `MELI_CLIENT_ID` / `MELI_CLIENT_SECRET`, ou de `~/.config/meli/{app_id,secret}`.
- `~/.config/meli` em `chmod 700`; os arquivos dentro em `chmod 600`.
- **1 aplicação por conta** no Brasil. "Excluir" é irreversível.

---

## 4. Os dados que existem

```
dados/
├── categorias_mlb.csv           150 categorias. Sem credencial. E o VOCABULARIO de busca
├── produtos_mlb.csv          24.421 produtos, 1.412 dominios. Dataset do CLASSIFICADOR
├── valor_mlb.csv              1.218 mais vendidos + preco agregado. Dataset de PRECO
└── produtos_mlb_expandido.csv       saida de coleta_expandida.py, se voce rodou
```

**`produtos_mlb.csv` e `valor_mlb.csv` são quase disjuntos — 14 produtos em comum.
Não são duas amostras da mesma coisa, são duas populações.** Escolher o errado é o
erro mais provável neste projeto:

| Objetivo | Use | Não use |
|---|---|---|
| Classificar domínio | `produtos_mlb.csv` (1.412 domínios) | `valor_mlb.csv` (333, e só 16 treináveis) |
| Preço | `valor_mlb.csv` (cobertura 100%) | `produtos_mlb.csv` (11%) |
| Popularidade / vendas | `valor_mlb.csv` | `produtos_mlb.csv` — **não representa vendas** |

`produtos_mlb.csv`: `product_id`, `nome`, `domain_id`, `status`, `marca`,
`modelo`, `n_atributos`, `n_variacoes`, `criado_em`, `termo_busca`.

Integridade conferida: 24.421 linhas voltam pelo módulo `csv`, `product_id`
único, nenhum `nome` ou `domain_id` vazio. **Dois títulos contêm quebra de linha**
— escapados corretamente, então `wc -l` conta 24.423 e só o parser de CSV acerta.
Nunca conte registros com `wc -l`.

Como reproduzir e explorar: **`docs/guia-de-coleta.md`**.

### VIÉS CONHECIDO: a coleta por termo não acha os mais vendidos

Dos 1.218 produtos do ranking oficial de mais vendidos, **apenas 14 (1%) estão em
`produtos_mlb.csv`**. A busca por `q=` encontra a **cauda longa**, não os
campeões de venda. Isso não invalida o dataset para classificação de domínio, mas
**invalida qualquer conclusão sobre popularidade** tirada dele. Se o assunto é
"o que vende", use `valor_mlb.csv`, não `produtos_mlb.csv`.

---

## 5. Preço, quantidade vendida e faturamento

Medido em 28/09/2026. **Leia antes de prometer qualquer análise de receita.**

| Dado | Existe? | Rota / motivo |
|---|---|---|
| **Preço** | **Sim**, parcial | `/products/{id}/items` -> `price`, `original_price`, `shipping.cost` |
| **Frete e condição** | **Sim** | mesma rota: `free_shipping`, `condition`, `listing_type_id` |
| **Posição de venda** | **Sim**, ordinal | `/highlights/MLB/category/{cat}`, `highlight_type: BEST_SELLER`, posições 1..20 |
| **Quantidade vendida** | **Não** | `sold_quantity` não existe em nenhuma rota alcançável. `/items/{id}` = 403; `/items/bulk` = 403 por item |
| **Faturamento** | **Não** | exigiria preço × quantidade. Sem quantidade, **qualquer número de receita é inventado** |
| **Estoque** | **Não** | `available_quantity` inalcançável, e a doc indica faixas em vez de número |
| **Histórico de preço** | **Não** | a API só dá o agora. Série temporal exige coletar ao longo de semanas |

**Não relate faturamento, receita, GMV ou "quanto vendeu".** Não é uma limitação
de escopo a contornar — o dado não existe na API. Estimar preço × posição de
ranking produz um número plausível e falso.

### O que dá para fazer em vez disso

A pergunta "o que vende mais" **é respondível**, como **ranking/classificação**,
não como regressão sobre receita: `/highlights` é um ranking oficial de mais
vendidos, ordinal, e seus ids **são `product_id` de catálogo**, que juntam com
nossos CSVs. Cobertura: **130 de 150 categorias, 1.218 produtos únicos**, 20
posições no máximo (`limit` é ignorado).

Detalhes, limitações e casos de uso: **`docs/dados-de-valor.md`**.

### Três ressalvas que decidem se o preço serve

1. **A cobertura depende da população, e a diferença é enorme.**

   ```
   mais vendidos (valor_mlb.csv) : 1213 de 1218 = 100%
   busca q=, active              :   35 de  150 =  23%
   busca q=, inactive            :    0 de  100 =   0%
   busca q=, total estimado      : ~2757 de 24421 = 11,3%
   ```

   Os 404 são ausência de anúncio, não falta de escopo (zero 403 em 250
   requisições). **Para preço, use `valor_mlb.csv`.**

2. **Os anúncios vêm mal agrupados — mas menos do que este arquivo já afirmou.**
   Uma versão anterior disse "mediana na casa dos milhares por cento", extrapolando
   de uma amostra de 14. Medido nos 1.213: **mediana 64%**, p75 144%, p90 273%, e só
   **16% passam de 200%**. O máximo (2,6 milhões por cento) é outlier único.
   **Filtre por `amplitude_pct`** antes de usar preço como alvo — `<=100%` preserva
   763 de 1.213 — e diga no relatório qual filtro usou.

3. **Três features parecem úteis e não são.** `novos_pct` é **constante** (1.213 de
   1.213 em 100% novo); `n_anuncios` é **censurado em 100** (75 produtos travam no
   teto da rota); e **preço não correlaciona com posição de ranking** (mediana
   R$ 98,93 na posição 1, R$ 135,49 na 20, sem tendência) — o que é evidência
   empírica, não só conceitual, contra estimar receita por preço × posição.

### DADO PESSOAL: esta rota reintroduz o que o resto do projeto evita

`/products/{id}/items` devolve **`seller_id`** e **`seller_address`** (cidade e
estado). É a única rota do projeto que traz dado pessoal.

**Descarte na ingestão.** `coleta_valor.py` guarda apenas agregados de preço e
**nunca grava `seller_id`**. Não "enriqueça" o CSV com vendedor.

---

## 6. Limites legais — não são negociáveis por conveniência

- **Scraping é proibido.** Cláusula 7.6 dos Termos veda "robôs, harvesters,
  spiders, scraping". O `robots.txt` bloqueia `GPTBot`, `ClaudeBot`,
  `PerplexityBot` e `Amazonbot` com `Disallow: /`. **Regra operacional: se a API
  não entrega o dado, a resposta é mudar o escopo, não raspar.**
- **Você é Operador, não Controlador** (cláusula 6.2). Treinar modelo próprio é
  definir finalidade própria. Mitigação: treinar só sobre dado não pessoal — o
  que produto de catálogo garante por construção.
- **Retenção limitada** (2.2.1.3, só "cópias intermediárias") e **revogação
  discricionária com dever de destruir** (13). Isto é contratual: nenhuma
  credencial resolve.
- **Não publique nem compartilhe** o dataset ou o modelo com terceiros (2(f), 7.4).
- **Nunca armazene dado de cartão nem credencial** de usuário (7.9).
- **Descarte `seller_id`, `nickname` e autoria de avaliação na ingestão.**
- **Não infira dado sensível** (saúde, religião, política) de histórico de compra
  (LGPD art. 11).
- A exceção acadêmica da LGPD (art. 4º II b) dispensa da **lei**, não do
  **contrato**. Os Termos continuam valendo integralmente.
- **Prazo 25/10/2026:** `/items?ids=` -> `/items/bulk?ids=`,
  `/users?ids=` -> `/users/bulk?ids=`; `code` -> `status_code`, `id` na raiz,
  `attributes` precisa de prefixo `body.`.

---

## 7. Como treinar

**Entrada `nome`, rótulo `domain_id`.** As duas colunas já estão no CSV.

O rótulo é **`domain_id`** (`MLB-BOOKS`), **não `category_id`** (`MLB1196`):
produto de catálogo não retorna `category_id`. (Versões anteriores deste arquivo
diziam `category_id`. Errado.)

### O desbalanceamento é o problema central

```
dominios distintos        1412
com 1 unico exemplo        457   (32%)
titulo: mediana 51 char, media 53.8, max 200
status: 11.815 active / 12.606 inactive
```

1.412 classes com 457 singletons **não é treinável**: não há split estratificado
de classe com um exemplo. Corte por mínimo de exemplos. Números reais:

| Corte | Classes | Produtos retidos |
|---|---|---|
| ≥1 | 1412 | 24.421 |
| ≥2 | 955 | 23.964 |
| ≥5 | 540 | 22.868 |
| **≥10** | **357** | **21.659** |
| ≥20 | 219 | 19.816 |

**Comece em ≥10:** 357 classes, 21.659 produtos — descarta 11% dos dados e 75%
das classes, quase toda a cauda de ruído. **Declare o corte no relatório**; é
decisão metodológica, não detalhe de implementação.

**Baseline:** TF-IDF char n-gram (3-5) + `LinearSVC`. Bate rede neural em título
curto de e-commerce e treina em segundos. Suba para BERTimbau só se o baseline
não atingir a meta.

**Métrica: macro-F1.** Com 357 classes desbalanceadas, acurácia parece ótima e
não significa nada. Macro-F1 pesa cada classe igualmente.

### TRÊS VAZAMENTOS DE RÓTULO — o erro mais fácil de cometer aqui

| Coluna | Por que vaza |
|---|---|
| `marca` | vem de `attributes[]`, que a ML preenche **já sabendo** o domínio |
| `modelo` | idem |
| `termo_busca` | **é** o nome da categoria que gerou a consulta |

Treinar com qualquer uma produz acurácia alta e falsa. **Use só `nome`.**
`marca` serve para análise de erro; `termo_busca` para auditar cobertura.

### Casos de uso a NÃO implementar

| Caso | Motivo |
|---|---|
| Previsão de faturamento | **O dado não existe.** Ver §5 |
| Recomendação | Exige interação usuário-item que a API não entrega; art. 12 §2º |
| Score de vendedor | Dado pessoal de PF + art. 20 (decisão automatizada) |
| Detecção de fraude | Não existe rótulo de fraude. Não é aprendível com estes dados |
| Sentimento em avaliações | Endpoint fechado; texto pode conter dado pessoal de terceiro |

---

## 8. Convenções

- **Português** em código, comentário e documento.
- Comentário explica **por que**, nunca o que a linha faz.
- `coleta_categorias.py` e `coleta_produtos.py` usam só a **biblioteca padrão**
  (`urllib`), de propósito: menos dependência para reproduzir.
- Pausa de 0,18–0,25 s entre chamadas e **backoff reativo ao `429`**. O rate limit
  oficial não é publicado. Empiricamente: zero `429` em 24.421 requisições.
- Ambiente: macOS, Python 3.11.13, `requests` 2.32.5, `pandas` 2.3.0. `uv` e
  `poetry` disponíveis.
- **`sleep` em primeiro plano é bloqueado neste harness.** Use `time.sleep` dentro
  do Python.

---

## 9. Pendências — não trate como fato

- **Nenhum dos 34 escopos cobre `/sites/MLB/search`.** Não se sabe se existe
  escopo não listado ou se depende de aprovação comercial.
- **Amplitude de preço absurda não foi explicada.** A hipótese é agrupamento
  ruim de anúncio, mas **não dá para confirmar**: validar exigiria ler o título do
  anúncio, e `/items/{id}` é 403. Registrado como não explicado, não como resolvido.
- **Estabilidade do ranking de mais vendidos é desconhecida.** Medido uma vez. Se
  o projeto depender disso como alvo, colete duas vezes e compare.
- Nome exato do `grant_type` do **Device Grant** (o `device_code` dá
  `unsupported_grant_type`; provavelmente exige habilitar no cadastro).
- Conta **apenas-compradora** consegue token funcional?
- Espelho do dataset MeLiDC no **Kaggle** com licença declarada (a API do Kaggle
  exige autenticação). Ver `docs/fonte-de-dados.md`.
- Caso **ANPD × Meta** (2024) sobre legítimo interesse para treino de IA, e status
  do **PL 2338/2023**.
- Os paths de `/reviews`, `/visits` e sugestão de preço vêm de sondagem empírica,
  **não de documentação lida**.

### A documentação do Mercado Livre mente. Duas vezes, comprovadamente

1. **Ela devolve `HTTP 200` com ~76KB em páginas inexistentes**, em vez de 404. Ao
   automatizar leitura de doc, **verifique o conteúdo, não o status**. Um link da
   própria doc oficial (`/devcenter/new-list-app`) está morto com 404.
2. **Ela afirma que `client_credentials` não existe.** Funciona. O que revelou
   isso foi comparar **códigos de erro** com um grupo de controle: um `grant_type`
   inventado devolve `unsupported_grant_type`, enquanto `client_credentials`
   devolvia `invalid_client` — logo o grant era reconhecido e só as credenciais
   eram falsas.

**Quando a doc e o servidor discordam, teste o servidor.**

URLs verificadas:

```
https://developers.mercadolivre.com.br/devcenter              302 -> login ML   OK
https://developers.mercadolivre.com.br/devcenter/new-list-app 404  link da propria doc
https://www.mercadolivre.com.br/developers                    404
```
