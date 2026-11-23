# Viabilidade de um projeto de ML com dados do Mercado Livre

**Trabalho acadêmico. Levantamento com verificação empírica.**
Data: 28/09/2026. Site: `MLB` (Brasil).

Toda afirmação aqui é de fonte primária (documentação oficial, Termos e
Condições, `robots.txt`, legislação) ou de teste executado contra a API. Onde não
foi possível verificar, está escrito **que não foi**. O §8 lista o que ficou em
aberto.

| Seção | Assunto |
|---|---|
| [1](#1-fonte-de-dados) | Fonte de dados: acesso, autenticação, limites |
| [2](#2-infraestrutura) | Infraestrutura |
| [3](#3-conformidade-legal-e-contratual) | Conformidade legal e contratual |
| [4](#4-casos-de-uso-de-ml) | Casos de uso de ML |
| [5](#5-código-e-dados-coletados) | Código e dados coletados |
| [6](#6-resultado-do-modelo) | Resultado do modelo |
| [7](#7-roadmap-e-riscos) | Roadmap e riscos |
| [8](#8-pendências-de-verificação) | Pendências de verificação |
| [9](#9-fontes-primárias) | Fontes primárias |

---

## Sumário executivo

A premissa "Mercado Livre como base de dados aberta para ML" **não se sustenta na
forma originalmente proposta**, mas o projeto é viável e **a coleta foi executada
com sucesso**. Dos dois bloqueios identificados, um caiu e o outro não.

1. **Bloqueio técnico — superado.** A API não é pública: de 7 endpoints testados
   sem token, apenas 2 responderam `200`. Com aplicação registrada e escopos
   `urn:ml:*` habilitados, a coleta funciona — **24.421 produtos e 1.412 domínios
   em 8 minutos**, pela rota `/products/search`. A busca de *anúncio* permanece
   fechada; a busca de *produto de catálogo* não.
2. **Bloqueio contratual — permanece.** Os Termos definem o desenvolvedor como
   **Operador**, não Controlador, e não autorizam retenção permanente. Isso é
   contratual, não técnico: **nenhuma credencial resolve.**

O escopo redesenhado é **classificação de produto em domínio** (`nome` ->
`domain_id`), e ele **já foi treinado e avaliado**: macro-F1 **0,852** em 357
classes (§6).

O caso de uso usa apenas dado não pessoal, por um motivo mais forte que o
previsto: **produto de catálogo não tem vendedor**, então a resposta da API não
contém `seller_id` nem `nickname`. Não há dado pessoal a filtrar porque não há
dado pessoal na resposta.

**Faturamento, receita e quantidade vendida não são obteníveis** (§1.5 e
`dados-de-valor.md`). **Preço é obtenível**: 100% dos mais vendidos, 11% do
dataset de busca.

---

## 1. Fonte de dados

### 1.1 Teste empírico de acesso público

Sete endpoints, sem credencial:

| Endpoint | Status |
|---|---|
| `/categories/{id}` | **200** |
| `/sites/MLB/domain_discovery/search?q=` | **200** |
| `/sites/MLB/search?q=` | 403 |
| `/sites/MLB/categories` | 403 |
| `/items/{id}` | 403 |
| `/items?ids=` | 403 |
| `/trends/MLB` | 403 |

Conclusão: **a API não é pública.** Qualquer plano que dependa de coleta anônima
está inviável desde o início.

### 1.2 Autenticação

OAuth 2.0. Grants testados contra `/oauth/token`:

| Grant | Resultado |
|---|---|
| `authorization_code` | Suportado (documentado) |
| `refresh_token` | Suportado. **Só no fluxo `authorization_code`** |
| `client_credentials` | **FUNCIONA — verificado.** `200`, `APP_USR-...`, `expires_in: 21600`, **sem** `refresh_token`. A documentação afirma que não existe; a documentação está errada |
| `device_code` | `unsupported_grant_type` |
| `password` | `unsupported_grant_type` |
| `implicit` | `unsupported_grant_type` |

**`client_credentials` é o achado que viabilizou o projeto.** Consequências
verificadas: **sem browser, sem `redirect_uri`, sem rotação de token.** Renovar é
repetir o mesmo `POST`. Uma aplicação sem `redirect_uri` configurado serve para
`client_credentials` — ela só não serve para `authorization_code`.

#### Como a contradição foi resolvida

A documentação diz que só `authorization_code` e `refresh_token` são aceitos. O
servidor discordava:

```
grant_type=client_credentials  -> {"error":"invalid_client",        "status":400}
grant_type=device_code         -> {"error":"unsupported_grant_type","status":400}
grant_type=banana              -> {"error":"unsupported_grant_type","status":400}
```

O grupo de controle (`banana`) é o que dá sentido à diferença: um grant
**inexistente** devolve `unsupported_grant_type`. O `client_credentials` passou
dessa validação e falhou só nas credenciais falsas — logo **o grant era
reconhecido**. Testado depois com credenciais reais: `HTTP 200`.

**Lição metodológica: quando a documentação e o servidor discordam, teste o
servidor — e use grupo de controle para ler códigos de erro.**

### 1.3 Autenticado não é autorizado: os dois `403`

```
sem token    403  {"error":"forbidden","message":"forbidden"}
com token    403  {"message":"At least one policy returned UNAUTHORIZED."}
                  ^ sem campo "error" — token OK, falta ESCOPO no app
```

O segundo caso travou o projeto por um dia inteiro e era **configuração**: depois
de habilitar os escopos de leitura no DevCenter, a mesma aplicação passou a ter 34
escopos e as rotas de marketplace abriram.

**Armadilha correlata:** com token **sem** escopo `urn:ml:*`,
`/sites/MLB/domain_discovery/search` **cai de 200 para 403** — a policy avalia o
escopo e nega em vez de cair na regra pública. Mandar token pode **piorar** o
acesso.

### 1.4 O mapa de acesso com token válido

```
200  /products/search?site_id=MLB&q=...   <- busca de CATALOGO. O alicerce
200  /products/{id}                        <- ficha: nome, dominio, atributos
200  /products/{id}/items                  <- anuncios do produto: PRECO
200  /highlights/MLB/category/{cat}        <- MAIS VENDIDOS, posicoes 1..20
200  /trends/MLB  e  /trends/MLB/{cat}     <- 40 termos populares
200  /sites/MLB/categories                 <- arvore completa
200  /categories/{id}/attributes           <- 143 atributos em MLB1652
200  /catalog_domains/{domain_id}
403  /sites/MLB/search                     <- busca de ANUNCIO: fechada
403  /items/{id}                           <- detalhe de anuncio: fechado
200  /items/bulk?ids=   ARMADILHA: envelope 200, cada item 403 dentro
```

#### `/items/bulk` mente sobre o status

O HTTP é `200`; cada entrada do corpo traz `"status_code": 403`:

```json
[{"id": "MLB5963285546", "status_code": 403,
  "error": {"message": "Access to the requested resource is forbidden"}}]
```

Versões anteriores deste levantamento registraram `/items/bulk` como funcional,
porque só o envelope foi conferido. **Erro corrigido: leia o `status_code` de cada
item.**

#### Por que `/products/search` é preferível, não um consolo

A busca de anúncio está fechada e nenhum dos 34 escopos a cobre. A busca de
produto de catálogo responde 200 e é **melhor** para este projeto:

1. **Não tem vendedor.** Ficha canônica, não oferta: sem `seller_id`, sem
   `nickname`. Elimina o dado pessoal na origem em vez de filtrá-lo depois.
2. **Título canônico.** Cem vendedores do mesmo notebook viram **um** produto, em
   vez de cem quase-duplicatas.
3. **Já vem rotulado** com `domain_id` — o rótulo do classificador, sem anotação.

**`q` é obrigatório.** Sem ele: `400 Field 'keywords', 'product_identifier',
'parent...' required`. **Não existe rota que enumere produtos sem termo de
busca** — daí a dependência do CSV de categorias como vocabulário. `domain_id`
funciona como filtro adicional, nunca sozinho.

### 1.5 Preço, quantidade vendida e faturamento

| Dado | Existe? | Observação |
|---|---|---|
| Preço | **Sim.** 100% dos mais vendidos, 11,3% do dataset de busca | `/products/{id}/items`. Ver a tabela de populações abaixo |
| Frete, condição, nº de vendedores | **Sim** | mesma rota |
| Posição de mais vendido | **Sim**, ordinal | `/highlights/...`, `BEST_SELLER`, 1..20 |
| **Quantidade vendida** | **Não** | `sold_quantity` só no detalhe do anúncio, que é 403 |
| **Faturamento / receita** | **Não** | exigiria preço × quantidade |
| Estoque | **Não** | inalcançável; a doc indica faixas |
| Histórico de preço | **Não** | a API só dá o agora |

**Não estime faturamento.** Preço × posição de ranking é inválido: a posição é
ordinal e não se sabe se o 1º vende 2× ou 200× mais que o 20º. Um número obtido
assim é plausível e falso.

**A cobertura de preço depende de qual população se consulta, e a diferença é
enorme:**

| População | Com preço | Medição |
|---|---|---|
| Mais vendidos (`valor_mlb.csv`) | **1.213 de 1.218 = 100%** | censo completo |
| Busca `q=`, `active` | **23%** | 35 de 150, amostra aleatória |
| Busca `q=`, `inactive` | **0%** | 0 de 100 |
| Busca `q=`, total estimado | **11,3%** (~2.757) | projeção sobre 11.815/12.606 |

Os `404` são ausência de anúncio, não falta de permissão: nenhum `403` nas 250
requisições. **Isso é a mesma descoberta do §5.5 por outro ângulo** — a busca por
`q=` encontra produtos tão obscuros que 77% dos marcados `active` não têm anúncio
no ar. Os campeões de venda têm, por definição.

**Três features que parecem úteis e não são**, medidas nos 1.213:

- **`novos_pct` tem variância zero** — 1.213 de 1.213 com 100% de anúncios `new`.
  Coluna constante, inútil como feature.
- **Preço não correlaciona com posição no ranking.** Mediana na posição 1:
  R$ 98,93; na 10: R$ 176,62; na 20: R$ 135,49. **Sem tendência monotônica** — o
  que é evidência empírica, e não só conceitual, contra estimar receita por
  `preço × posição`.
- **`n_anuncios` é censurado em 100** (mediana 6, mas 75 produtos travam no teto de
  `limit` da rota). O valor real ali é "100 ou mais".

**Sobre a dispersão de preço, uma correção:** uma medição anterior deste relatório,
em amostra de 14, sugeriu amplitude mediana "na casa dos milhares por cento". Sobre
os 1.213, **é falso**: mediana **64%**, p75 144%, p90 273%, e só **16% passam de
200%**. O máximo (2,6 milhões por cento) é outlier único. A hipótese de agrupamento
ruim permanece, agora como problema de uma minoria — e **não dá para confirmar**,
porque validar exigiria o título do anúncio e `/items/{id}` é 403.

Análise completa e casos de uso: **`dados-de-valor.md`**.

### 1.6 Limites

Documentados:

- **Teto de 1000 registros** na paginação por offset.
- Contorno oficial `search_type=scan` em `/users/{id}/items/search` e
  `/questions/search`; devolve `scroll_id`, que **expira em 5 minutos**.
- `limit`: default 50, **máximo 100**.
- `429` = `local_rate_limited`.
- **Allowlist de IPs por aplicação**, que pode causar `403` inesperado.

Medidos em `/products/search`, **mais rígidos que os documentados**:

```
limit    maximo 100   (limit=200 devolve lista vazia)
offset   maximo 100   (offset=100 -> 200 OK; offset=101 -> 400 Invalid arguments)
```

Teto real: **200 produtos por consulta**, não 1000. `paging.total` reporta
`10000` e é irrelevante — o teto de `offset` impede alcançá-los, e `search_type=scan`
**não** existe nesta rota. Em `/highlights`, o máximo é **20** e `limit` é ignorado.

**Consequência arquitetural: o volume é função do vocabulário de consulta, não da
paginação.** ~194 produtos únicos por termo; 134 termos -> 24.421 únicos.

#### Isso significa que o teto NÃO é 24 mil

O limite de 200 por consulta parece um teto e não é — é um teto **por termo**. Mais
termos, mais produtos. Medido com 40 marcas novas, tiradas do próprio CSV:

```
40 termos novos -> 6.413 produtos INEDITOS
                   160 por termo, taxa de novidade 97%
                   332 dominios ineditos (o dataset tinha 1412)
```

**97% de novidade** significa que as marcas quase não repetem o que a busca por
nome de categoria já achou: são fatias diferentes do catálogo.

Vocabulário disponível **sem coletar nada novo**, extraído do que está em disco:

| Origem | Termos | Rendimento |
|---|---|---|
| Marcas com ≥5 produtos | 762 | **160 inéditos/termo** (medido) |
| `/trends/MLB/{cat}`, 40 categorias | 638 | termos de busca reais do site |
| Palavras frequentes dos títulos | 692 | não medido |
| Marcas raras (<5 produtos) | 8.953 | rendimento menor, cauda longa |
| **Total** | **11.045** | |

O teto real é onde a **curva de saturação** achata, e isso não está documentado em
lugar nenhum — tem de ser medido. `src/coleta/coleta_expandida.py` existe para isso:
imprime inéditos por termo a cada 25 termos, o que mostra a saturação acontecendo.

**O limite prático não é a API, é o tempo:** ~1 s por termo, então 400 termos ≈ 7
min. O limite metodológico aparece antes do técnico — ver §7, risco 5.

> **Não encontrado:** números oficiais de requisições por segundo ou por dia. A
> página `/pt_br/limites-de-requisicoes` retorna 404. Valores que circulam em blogs
> não são confirmáveis. **Implemente backoff reativo ao `429`** em vez de codificar
> contra um número não verificado. Empiricamente: **zero `429` em 24.421
> requisições** com pausa de 0,25 s — o que não é garantia.

### 1.7 Deprecação com prazo: 25/10/2026

| Antigo | Novo |
|---|---|
| `/items?ids=` | `/items/bulk?ids=` |
| `/users?ids=` | `/users/bulk?ids=` |

Mudanças de contrato na resposta: `code` -> **`status_code`**, `id` passa à raiz do
objeto, e os campos antes em `attributes` exigem prefixo **`body.`**.

Impacto real neste projeto: **baixo**, porque o classificador não usa `/items`.
Escrever já no formato novo custa nada.

### 1.8 Degradação de dado relevante para ML

- `available_quantity` é retornado **em faixas**, não em número exato, o que
  degrada qualquer feature de estoque.
- Não há **histórico de preço**: série temporal exige coleta repetida ao longo de
  semanas. É espera de calendário, não trabalho.

---

## 2. Infraestrutura

### 2.1 Princípio: não superdimensionar

É trabalho de faculdade em máquina local, sem orçamento de cloud. A tentação de
montar *data lake*, orquestrador e *feature store* deve ser resistida: o dataset
inteiro tem **3,5 MB**. Um CSV e um script bastam.

### 2.2 O que foi realmente usado

| Componente | Escolha | Por quê |
|---|---|---|
| Linguagem | Python 3.11.13 | já instalado |
| HTTP | **`urllib` (biblioteca padrão)** | zero dependência para reproduzir |
| Análise | `pandas` 2.3.0 | já instalado |
| ML | `scikit-learn` 1.7.0 | baseline linear basta |
| Armazenamento | **CSV** | 3,5 MB; banco seria cerimônia |
| Orquestração | **nenhuma** | dois comandos em ordem |
| Segredo | `~/.config/meli/`, `chmod 600` | fora do projeto, fora de commit |

`requests` está instalado mas os coletores não o usam, de propósito: quem
reproduzir o trabalho não precisa instalar nada.

### 2.3 Pipeline

```
coleta_categorias.py  (sem token)   -> categorias_mlb.csv   150 registros
         |                                    |
         |  o CSV e o VOCABULARIO de busca ---+
         v
coleta_produtos.py    (com token)   -> produtos_mlb.csv   24.421 registros
coleta_valor.py       (com token)   -> valor_mlb.csv      ranking + preco
         |
         v
   corte >=10 exemplos -> split estratificado -> TF-IDF + LinearSVC -> macro-F1
```

A dependência do primeiro para o segundo **não é opcional**: `/products/search`
exige `q`, e não há rota que enumere produtos sem termo.

### 2.4 Retenção

A cláusula 2.2.1.3 autoriza apenas "cópias intermediárias" e a 13 permite
revogação com dever de destruir. Consequência prática: o CSV é **artefato
descartável**, e o script que o regenera é o entregável real. Não há camada
bronze/silver a construir — não há dado pessoal para anonimizar nem TTL de titular
a aplicar.

---

## 3. Conformidade legal e contratual

### 3.1 Termos e Condições da API

| Cláusula | Conteúdo | Efeito no projeto |
|---|---|---|
| **6.1 / 6.2** | Desenvolvedor é **Operador**, não Controlador | Treinar modelo próprio é definir finalidade própria. **Principal conflito** |
| **2.2.1.3** | Só "cópias intermediárias" | Retenção permanente não autorizada |
| **13** | Revogação discricionária, com dever de destruir | Modelo treinado sobre dado que se deve destruir é problema sem solução técnica limpa |
| **7.6** | Veda "robôs, harvesters, spiders, scraping" | **Scraping está fora** |
| **2(f) / 7.4** | Não redistribuir a terceiros | Não publicar dataset nem modelo |
| **7.9** | Não armazenar dado de cartão nem credencial | Nunca persistir |
| **4.3** | A base é protegida como propriedade intelectual | Relevante também para dataset de terceiro (§ `fonte-de-dados.md`) |

**Mitigação adotada:** treinar **somente sobre dado não pessoal**. Produto de
catálogo garante isso por construção, não por filtro.

### 3.2 Scraping como alternativa: não

Duas barreiras independentes:

1. **Contratual** — cláusula 7.6 veda explicitamente scraping.
2. **Técnica e expressa** — o `robots.txt` do site bloqueia crawlers de IA
   **nominalmente**: `GPTBot`, `ClaudeBot`, `PerplexityBot`, `Amazonbot`, todos com
   `Disallow: /`.

O bloqueio nominal remove a ambiguidade: não é omissão, é recusa expressa.

> **Regra operacional do projeto: se a API não entrega o dado, a resposta é mudar
> o escopo do trabalho, não raspar o site.**

Durante todo o levantamento, só o subdomínio `developers` foi acessado — ele não
tem `robots.txt`.

### 3.3 LGPD (Lei 13.709/2018)

O desenho do projeto **evita a LGPD por ausência de objeto**, não por exceção:
produto de catálogo não contém dado pessoal.

Artigos que importariam se o escopo mudasse:

- **Art. 4º II b** — tratamento para fins **acadêmicos** é excepcionado. Atenção:
  isso dispensa da **lei**, **não do contrato**. Os Termos continuam integralmente
  em vigor.
- **Art. 11** — dado sensível (saúde, religião, política). **Não inferir** nada
  disso de histórico de compra.
- **Art. 12 §2º** — perfilização pode caracterizar dado pessoal. Afeta
  recomendação.
- **Art. 20** — decisão automatizada dá direito a revisão. Afeta score de vendedor.

**A única rota do projeto que traz dado pessoal** é `/products/{id}/items`, que
devolve `seller_id` e `seller_address`. `coleta_valor.py` **descarta os dois na
ingestão** e grava só agregados de preço.

### 3.4 Conclusão prática

O projeto é conforme se, e somente se:

1. treinar apenas sobre dado **não pessoal** (produto, nome, domínio, atributo, preço);
2. **descartar `seller_id`, `nickname` e autoria de avaliação na ingestão**;
3. **não publicar** dataset nem modelo para terceiros;
4. **não inferir** dado sensível;
5. tratar o CSV como **cópia intermediária**, regenerável pelo script;
6. **não fazer scraping**, em nenhuma circunstância;
7. declarar a procedência no relatório.

---

## 4. Casos de uso de ML

Filtrados pelo que é de fato coletável **e** conforme.

### 4.1 Recomendado: classificação de produto em domínio

**Entrada `nome`, rótulo `domain_id`.** É o único caso que sobrevive a todas as
restrições:

- dado inequivocamente **não pessoal**;
- rótulo **de graça**, sem anotação manual;
- **dados já coletados**: 24.421 exemplos.

**Atenção ao nome do rótulo:** é `domain_id` (`MLB-BOOKS`), **não `category_id`**
(`MLB1196`) — produto de catálogo não retorna `category_id`.

**Três vazamentos de rótulo**, medidos:

| Coluna | Evidência | Veredito |
|---|---|---|
| `marca` | **85% das marcas apontam para 1 único domínio** | Vazamento grave. Fora |
| `modelo` | idem `marca` (vem de `attributes[]`) | Fora |
| `termo_busca` | mediana de 11 domínios por termo — reduz 1.412 para ~11 | Forte demais. Fora |

`marca` e `modelo` vêm de `attributes[]`, que a própria ML preenche **já sabendo**
o domínio. **Treine só com `nome`.**

### 4.2 Outros casos viáveis

Detalhamento em `dados-de-valor.md` §3.

| Caso | Viabilidade |
|---|---|
| Campeão de venda vs cauda longa | Promissor, **com confundidor sério**: os dois conjuntos vêm de rotas diferentes, então acurácia alta pode ser artefato de coleta |
| Faixa de preço a partir do título | Viável, mas nenhum dos dois CSVs é confortável: `valor_mlb.csv` tem cobertura 100% e só 16 classes treináveis; `produtos_mlb.csv` tem ~2.757 com preço em 1.412 domínios. Use quartis **dentro do domínio**, não regressão em reais |
| Detectar anúncio mal agrupado | Original: usa `amplitude_pct` como rótulo. Transforma a limitação em objeto de estudo |
| Frete grátis a partir do título | Fácil, rótulo limpo e binário |
| Classificação hierárquica | Deve ajudar nas confusões intra-raiz do §6 |

### 4.3 Casos a NÃO implementar

| Caso | Motivo |
|---|---|
| Previsão de faturamento | **O dado não existe.** Ver §1.5 |
| Recomendação | Exige interação usuário-item que a API não entrega; art. 12 §2º |
| Score de vendedor | Dado pessoal de PF + art. 20 |
| Detecção de fraude | Não existe rótulo de fraude. Não é aprendível com estes dados |
| Sentimento em avaliações | Endpoint fechado; texto pode conter dado pessoal de terceiro |

---

## 5. Código e dados coletados

Três scripts em `src/coleta/`. Passo a passo de execução: **`guia-de-coleta.md`**.

### 5.1 `coleta_categorias.py` — sem credencial

`/sites/MLB/categories` exige token, então a via pública é semear `category_id`
por `domain_discovery` e caminhar a árvore com `path_from_root` e
`children_categories` de `/categories/{id}`.

**Status: executado e validado.**

```
registros: 150 | folhas: 52 | raizes: 18

       profundidade  total_itens  n_filhos
count         150.0        150.0     150.0
mean            2.7    2919261.3       7.4
min             1.0        290.0       0.0
max             5.0  109680170.0      40.0

-- top 4 categorias por volume --
 MLB5672      Acessórios para Veículos     109680170
MLB22693 Peças de Carros e Caminhonetes     66569068
 MLB1574      Casa, Móveis e Decoração      47023970
 MLB1430     Calçados, Roupas e Bolsas      35045694
```

**Roda sem `Authorization` de propósito:** com token sem escopo,
`domain_discovery` cai de 200 para 403. Este CSV também é o **vocabulário de
busca** do próximo script.

### 5.2 `coleta_produtos.py` — o dataset principal

Atende ao requisito de **≥100 registros de produto com resumo estatístico**.
Entregou **24.421**.

Autenticação por `client_credentials`; credenciais de ambiente ou de
`~/.google/../.config/meli/` em `chmod 600`, **nunca do código**. Backoff reativo
ao `429`. Pagina apenas os dois offsets legais (0 e 100) e deduplica por
`product_id`.

**Status: executado e validado.** Resumo estatístico real:

```
134 termos de busca a partir de categorias_mlb.csv
================================================================
produtos unicos      : 24421
dominios distintos   : 1412
com marca preenchida : 23100
status               : {'active': 11815, 'inactive': 12606}

distribuicoes:
  tamanho do titulo      min=3     mediana=51    media=53.8     max=200
  atributos por produto  min=1     mediana=7     media=8.5      max=54

top 12 dominios (rotulo do classificador):
    829  MLB-BOOKS
    382  MLB-CAT_AND_DOG_FOODS
    323  MLB-BATHROOM_ACCESSORIES_KITS
    310  MLB-STUDIO_MONITORS
    232  MLB-BICYCLE_BASKETS
    218  MLB-DRILL_CHUCKS
    209  MLB-BOOKCASES
    209  MLB-STATIONARY_BICYCLES
    207  MLB-BOOKENDS
    206  MLB-WIRELESS_MONITOR_SYSTEMS
    205  MLB-THERMAL_REFRIGERATORS_AND_BAGS
    205  MLB-PEDAL_EXERCISERS

dominios com 1 so exemplo: 457 de 1412  (32%)
-> distribuicao desbalanceada: avalie por macro-F1, nao acuracia.
```

Colunas: `product_id`, `nome`, `domain_id`, `status`, `marca`, `modelo`,
`n_atributos`, `n_variacoes`, `criado_em`, `termo_busca`.

**Integridade conferida:** as 24.421 linhas voltam pelo módulo `csv`,
`product_id` é único, nenhum `nome` ou `domain_id` vazio. Dois títulos contêm
quebra de linha — escapados corretamente, então `wc -l` conta 24.423 e só o parser
de CSV acerta. **Não conte registros com `wc -l`.**

Duração: **8min04s**, zero `429`.

### 5.3 `coleta_valor.py` — ranking de mais vendidos e preço

Três etapas: ranking por categoria (`/highlights`), ficha de cada produto
ranqueado, preço agregado dos anúncios. **Descarta `seller_id` e `seller_address`
na ingestão** e grava apenas agregados (`preco_min`, `preco_mediana`,
`preco_max`, `amplitude_pct`, `frete_gratis_pct`, `novos_pct`, `n_anuncios`).

Cobertura do ranking: **130 de 150 categorias, 1.218 produtos únicos**, 20
posições no máximo.

### 5.4 `coleta_expandida.py` — ampliar o dataset além de 24 mil

Existe porque o volume é função do vocabulário (§1.6), não da paginação. Monta a
fila de termos a partir de quatro fontes — marcas do próprio CSV, `/trends`,
palavras frequentes dos títulos, marcas raras — deduplica contra `produtos_mlb.csv`
e grava em `produtos_mlb_expandido.csv`, **sem sobrescrever o dataset validado**.

Duas decisões de projeto que valem registro:

- **Imprime a curva de saturação** a cada 25 termos (inéditos por termo). É a única
  forma honesta de responder "qual é o limite", já que nenhum número oficial
  existe: mede-se até a curva achatar.
- **Pula a segunda página** quando a primeira volta com menos de 100 resultados,
  economizando metade das requisições nos termos pouco produtivos.

### 5.5 `meli_client.py` — cliente para `authorization_code`

Implementa rotação de `refresh_token` de uso único com persistência `chmod 600`,
renovação 10 min antes das 6h, `/items/bulk` no formato novo e `search_type=scan`.

> **Status: verificado em sintaxe e lógica, não em execução.** O fluxo
> `authorization_code` nunca foi rodado, porque `client_credentials` o tornou
> desnecessário. **Trate a execução como não confirmada.** Mantido por só ele
> cobrir rotas que exigem contexto de usuário.

### 5.6 Viés conhecido do dataset

Dos 1.218 produtos do ranking de mais vendidos, **apenas 14 (1%) estão em
`produtos_mlb.csv`**. A busca por `q=` encontra a **cauda longa**, não os campeões
de venda.

Isso **não** invalida o dataset para classificação de domínio, mas **invalida
qualquer conclusão sobre popularidade** tirada dele. É limitação a declarar, e
também oportunidade (§4.2).

---

## 6. Resultado do modelo

Executado sobre `produtos_mlb.csv`.

### 6.1 Corte de classes

1.412 classes com 457 singletons **não é treinável**: não há split estratificado
de classe com um exemplo.

| Corte | Classes | Produtos | % dos dados |
|---|---|---|---|
| ≥1 | 1412 | 24.421 | 100% |
| ≥2 | 955 | 23.964 | 98% |
| ≥5 | 540 | 22.868 | 94% |
| **≥10** | **357** | **21.659** | **89%** |
| ≥20 | 219 | 19.816 | 81% |
| ≥50 | 123 | 16.799 | 69% |

**Corte adotado: ≥10** — descarta 11% dos dados e 75% das classes, quase toda a
cauda de ruído. É decisão metodológica e está declarada.

### 6.2 Baseline

TF-IDF `char_wb` (3-5), `min_df=2`, `sublinear_tf` + `LinearSVC` com
`class_weight='balanced'`. Split 80/20 estratificado, `random_state=42`.

```
classes     : 357
treino/teste: 17.327 / 4.332
acuracia    : 0.914
macro-F1    : 0.852
tempo       : 11 segundos
```

**A distância entre acurácia (0,914) e macro-F1 (0,852) é a medida do
desbalanceamento** — e é por isso que relatar só acurácia superestima o modelo.
Macro-F1 é a métrica do trabalho.

### 6.3 Análise de erro: 381 erros em 4.332

```
MLB-DRILL_BITS                      -> MLB-DRILL_AND_SCREWDRIVER_BITS      6
MLB-MICROCONTROLLER_BOARDS          -> MLB-BATTERY_AND_CELL_...CHARGERS    4
MLB-ELBOW_SUPPORTS                  -> MLB-SPORTS_PROTECTION_ELBOW_PADS    4
MLB-NAUTICAL_CLEATS                 -> MLB-NAUTICAL_ROPES                  3
MLB-NON_REMOTE_CONTROL_TOY_VEHICLES -> MLB-DIECAST_VEHICLES                3
MLB-FOOTBALL_BALLS                  -> MLB-HANDBALL_BALLS                  3
```

As confusões são **semanticamente adjacentes**, e vários pares são **ambiguidade
da própria taxonomia**: "brocas" e "brocas e bits de parafusadeira" se sobrepõem
de fato; bola de futebol e de handebol diferem em pouco no título.

**Isto é resultado, não defeito.** Mostra que o erro tem estrutura semântica, e
sugere o próximo passo: classificação hierárquica (raiz -> domínio), já que as
confusões são intra-raiz.

---

## 7. Roadmap e riscos

### 7.1 Etapas

| Etapa | Esforço | Status |
|---|---|---|
| 0. Decidir escopo legal | ~4h | **Concluída** (§3.4) |
| 1. Baseline sem credencial | ~4h | **Concluída** — 150 categorias |
| 2. Criar app + obter token | ~2h | **Concluída.** `client_credentials` eliminou browser, HTTPS e rotação. O custo real foi habilitar escopos, não código |
| 3. Coletor de produto | ~3h | **Concluída** — 24.421 registros em 8min04s |
| 4. Corte + split + baseline | ~1h | **Concluída** — macro-F1 0,852 (§6) |
| 5. Coletor de valor | ~1h | **Concluída** — ranking e preço |
| 6. Modelo final e análise de erro | 1-2 dias | **Próxima.** Hierárquico; matriz de confusão |
| 7. Escrita do relatório | 1-2 dias | Procedência é declarável: fonte oficial, Termos aceitos |
| 8. Deploy *(opcional)* | 2-3 dias | Não é requisito do trabalho |

Etapas **removidas** do caminho crítico:

- **Camadas bronze/silver + expurgo (2 dias).** Produto de catálogo não tem dado
  pessoal: nada a anonimizar, nenhum TTL de titular. Um CSV basta. O dever de
  destruir em caso de revogação (cláusula 13) segue valendo sobre ele.
- **Coleta longitudinal (semanas).** Só servia para série de preço, fora do
  escopo. O classificador não precisa de histórico.

### 7.2 Riscos, em ordem de gravidade

1. **Contratual — o maior, e não é o rate limit.** Treinar modelo próprio conflita
   com a cláusula 6.2; a revogação é discricionária (13) com dever de destruir, e
   um modelo já treinado sobre dado que se deve destruir não tem solução técnica
   limpa. Mitigação: só dado não pessoal, e buscar autorização expressa (4.3).
2. **Desbalanceamento severo — principal risco técnico.** 457 de 1.412 domínios
   com 1 exemplo. Mitigado pelo corte ≥10 e por macro-F1, mas as 357 classes
   restantes ainda variam de 10 a 829 exemplos.
3. **Vazamento de rótulo.** `marca` determina o domínio em 85% dos casos.
   Treinar com ela produz número alto e falso. Mitigação: só `nome`.
4. **Viés de cauda longa (§5.5).** 1% de sobreposição com os mais vendidos.
   Qualquer afirmação sobre popularidade a partir deste dataset é inválida.
5. **Teto de volume — deixou de ser risco técnico e virou escolha metodológica.**
   24.421 é o teto de um vocabulário de 134 termos, não da API: 11.045 termos estão
   disponíveis sem coletar nada novo, e 40 marcas novas rendem 6.413 produtos
   inéditos (§1.6). O risco real agora é o **oposto** do que este documento previa:
   crescer o dataset é fácil e barato, então a tentação é crescer sem critério.
   **Mais dados da cauda longa não corrigem o viés do §5.6** — eles o aprofundam,
   porque a busca por `q=` continua não achando os campeões de venda. Ampliar ajuda
   nas classes com poucos exemplos (risco 2); não ajuda em representatividade.
6. **Prazo de 27 dias** para a migração ao `/bulk` (25/10/2026). Impacto baixo: o
   classificador não usa `/items`.
7. **Rate limits desconhecidos.** Sem número oficial. Empiricamente zero `429` em
   24.421 requisições, o que não é garantia.
8. **Preço de cobertura e qualidade limitadas** (§1.5). Não sustenta previsão de
   preço em reais.
9. **Estabilidade do ranking desconhecida** — medido uma vez só.

Riscos que **deixaram de existir**:

- ~~Ausência de `client_credentials`~~ — existe e funciona. O pipeline **é**
  autônomo, sem humano no loop.
- ~~Cadastro de tentativa única travando o cronograma~~ — a aplicação existe e
  valida. O risco foi gasto com sucesso.
- ~~`?q=` sem suporte~~ — fechado em `/sites/MLB/search`, **funciona** em
  `/products/search`.

---

## 8. Pendências de verificação

Não confirmado. **Não trate como fato.**

- **Nenhum dos 34 escopos cobre `/sites/MLB/search`.** Não se sabe se existe
  escopo não listado ou se depende de aprovação comercial.
- **A amplitude de preço absurda não foi explicada.** A hipótese é agrupamento
  ruim de anúncio, mas confirmar exigiria o título do anúncio, e `/items/{id}` é
  403. Registrado como **não explicado**.
- **Estabilidade do ranking de mais vendidos.** Medido uma vez. Se for alvo do
  modelo, colete duas vezes e compare.
- **Nome exato do `grant_type` do Device Grant.** `device_code` dá
  `unsupported_grant_type`; provavelmente exige habilitar no cadastro.
- **Conta apenas-compradora** consegue token funcional?
- **Espelho do MeLiDC no Kaggle** com licença declarada (a API do Kaggle exige
  autenticação). Ver `fonte-de-dados.md`.
- **Caso ANPD × Meta (2024)** sobre legítimo interesse para treino de IA, e status
  do **PL 2338/2023**.
- Os paths de `/reviews`, `/visits` e sugestão de preço vêm de sondagem empírica,
  **não de documentação lida**.

### Nota metodológica: a documentação mente, comprovadamente

1. **Ela devolve `HTTP 200` com ~76KB em páginas inexistentes**, em vez de 404. Ao
   automatizar leitura de doc, **verifique o conteúdo, não o status**. Um link da
   própria doc oficial (`/devcenter/new-list-app`) está morto com 404.
2. **Ela afirma que `client_credentials` não existe.** Funciona (§1.2).
3. **O envelope de `/items/bulk` diz 200 enquanto cada item diz 403** (§1.4).

Os três casos têm a mesma forma: **o status de superfície não corresponde ao
conteúdo.** A prática que resolveu todos foi ler o corpo da resposta e comparar
códigos de erro com grupo de controle.

URLs verificadas:

```
https://developers.mercadolivre.com.br/devcenter              302 -> login ML   OK
https://developers.mercadolivre.com.br/devcenter/new-list-app 404  link da propria doc
https://www.mercadolivre.com.br/developers                    404
```

---

## 9. Fontes primárias

| Fonte | Uso |
|---|---|
| `api.mercadolibre.com` | Todos os testes de endpoint, grant e limite |
| Documentação oficial de desenvolvedores | Autenticação, deprecação, limites, DevCenter |
| Termos e Condições da API | Cláusulas 2(f), 2.2.1.3, 4.3, 6.1, 6.2, 7.4, 7.6, 7.9, 13 |
| `robots.txt` do site | Bloqueio nominal de `GPTBot`, `ClaudeBot`, `PerplexityBot`, `Amazonbot` |
| Lei 13.709/2018 (LGPD) | Arts. 4º II b, 11, 12 §2º, 20 |

**Método:** toda afirmação de acesso vem de requisição executada, não de leitura
de documentação — decisão tomada depois de a documentação se mostrar errada em três
pontos independentes (§8). Onde o teste não foi possível, está registrado como
pendência em vez de inferido.
