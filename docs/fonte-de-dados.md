# Fonte de dados: a decisão e por quê

**Data:** 28/09/2026
**Status: RESOLVIDA — Trilha B, a API oficial. Os dados estão em disco.**

Havia duas formas de obter títulos de produto rotulados em português. As duas
funcionavam, então **nunca foi uma questão técnica** — foi escolha sobre
**procedência do dado e o que se pode defender numa apresentação**.

Este documento registra a decisão e o raciocínio, porque o raciocínio é parte do
trabalho: a avaliação de licença da Trilha A é resultado de pesquisa, não rascunho
descartável.

---

## 1. A pergunta

O caso de uso é **classificação de produto em domínio** — entrada `nome`, rótulo
`domain_id`. (**Não** `category_id`: produto de catálogo não retorna esse campo.)

| | Trilha A | Trilha B |
|---|---|---|
| | Dataset público já existente | Coletar pela API oficial |
| Volume | 6 milhões de títulos | **24.421 coletados** |
| Atrito | Nenhum, baixa e usa | Cadastro de aplicação + OAuth |

---

## 2. Trilha A — dataset MeLiDC no Hugging Face

### O que é

Re-upload do **MeLi Data Challenge 2019**, cuja tarefa original era exatamente
título -> categoria.

```
dataset: bccnf/MeLiDC-shuffled-completo
colunas: title, label_quality, language, category
splits:  train 6.000.000 | test 2.000.000 | valid 2.000.000
arquivo: data/train-00000-of-00002.parquet  (~137 MB)
```

`label_quality` (`reliable`/`unreliable`) permite treinar só no subconjunto
confiável; `language` permite filtrar `portuguese`.

**Verificado:** o parquet responde `HTTP 206` a *range request* — download real,
não presumido.

### A favor

- **6 milhões de títulos rotulados** — duas ordens de magnitude acima da API.
- **Zero atrito de credencial.**
- **`title` + `category` não contêm dado pessoal.** A LGPD não se aplica por
  ausência de objeto, sem nem precisar invocar a exceção acadêmica do art. 4º II b.
- Sem aceitar os Termos da API, **não se instaura o vínculo contratual** — o
  conflito Operador × Controlador da cláusula 6.2 não existe.

### O custo honesto

- **Licença ausente.** Verificado nos metadados do HF: o campo de licença **não
  existe** — não é string vazia, inexiste. **Lacuna não é permissão.**
- **A fonte oficial está morta.** `ml-challenge.mercadolibre.com` devolve 503 em
  todos os 5 caminhos testados; o bucket S3 original devolve `NoSuchBucket`. **Não
  há fonte primária citável.**
- **Contrato não é a única via de direito.** Não aceitar os Termos afasta a
  responsabilidade *contratual*, mas direito autoral e de base de dados incidem de
  forma independente — e a própria cláusula 4.3 dos Termos afirma que a base é
  protegida como propriedade intelectual. Um re-upload sem licença **não cria
  direito de uso**; só remove o rastro de quem publicou.
- **Procedência frágil:** 36 downloads, 0 likes. Não é dataset canônico da
  comunidade, é upload obscuro de terceiro.

### A ironia das duas edições

| Edição | Tarefa | Licença dos dados |
|---|---|---|
| 2019 | título -> categoria | **nenhuma** |
| 2020 | recomendação | CC BY-NC-SA 4.0 |

**A licença limpa cobre justamente o dataset que não serve.** Recomendação usa
histórico de navegação — dado comportamental, art. 12 §2º da LGPD. O dataset que
serve nunca teve licença.

---

## 3. Trilha B — API oficial

### O que é

Cadastrar aplicação no DevCenter, obter `client_id`/`client_secret`, autenticar por
OAuth e coletar. Detalhes em `viabilidade-mercadolivre-ml.md` §1; execução passo a
passo em `guia-de-coleta.md`.

### A favor

- **Procedência impecável.** Termos aceitos, fonte oficial citável, dado de 2026.
- **Dado coletado pelo aluno**, se a disciplina exigir.
- **Integração real com API é mérito do trabalho**, não só meio: OAuth, rate
  limit, paginação, os dois tipos de 403.
- **Campos que o dataset de 2019 não tem:** atributos, marca, modelo, variações,
  status, taxonomia vigente, e preço por rota separada.
- **Executado: 24.421 produtos, 1.412 domínios, 8min04s, zero 429.**

### O custo honesto

Dois custos que faziam desta a trilha arriscada **foram pagos no mesmo dia e deram
certo**:

- **`redirect_uri` HTTPS, browser e rotação de token** — eliminados. O grant
  `client_credentials` emite token (200, 6h) sem nenhum dos três, apesar de a
  documentação afirmar que não existe.
- **"Temos credencial e ela não serve"** — era configuração, não impossibilidade.
  O `403 "policy returned UNAUTHORIZED"` sinalizava **escopo faltando**; habilitados
  os escopos de leitura no DevCenter, a aplicação passou a ter 34 escopos e as
  rotas de marketplace abriram.

Uma afirmação deste documento estava **errada** e é corrigida aqui: *"sem busca
livre `?q=`"*. Verdade para `/sites/MLB/search` (busca de **anúncio**, 403), falso
para `/products/search` (busca de **produto**, 200). Foi por onde a coleta saiu.

O que **permanece** como custo real:

| Custo | Detalhe | Cai? |
|---|---|---|
| **Teto por consulta** | `limit`≤100 e `offset`≤100 ⇒ **200 produtos por termo**; `paging.total: 10000` é fantasia. Volume é função do **vocabulário**, não da paginação | **Sim, e é barato** — ver abaixo |
| **24k não são 6M** | Mas 24k **não é o teto.** 11.045 termos disponíveis sem coletar nada novo, e 40 marcas rendem 6.413 produtos inéditos (97% de novidade). Chegar a 60-80k é questão de minutos de execução | Parcialmente |
| **Cauda longa inutilizável** | 457 dos 1.412 domínios têm **1 exemplo**. Exige corte (≥10 ⇒ 357 classes/21.659 produtos), e o corte tem de ser declarado | Mitigável |
| **Cláusula 6.2** | Aceitar os Termos te faz **Operador**, não Controlador; treinar modelo é definir finalidade própria | **Não. É contratual** |
| **Retenção limitada** | 2.2.1.3 só autoriza "cópias intermediárias"; 13 permite revogação com dever de destruir | **Não. É contratual** |
| **Viés de cauda longa** | Só 1% dos produtos do ranking de mais vendidos aparece no dataset. A busca por `q=` acha a cauda, não os campeões | Declarar |
| **Rate limit desconhecido** | Nenhum número oficial publicado; só backoff reativo ao `429` | Não |
| **1 aplicação por conta** | O risco de "tentativa única" **já foi gasto com sucesso** | Gasto |

**A mitigação legal ficou mais forte do que o previsto:** produto de catálogo **não
tem vendedor**, então a resposta não traz `seller_id` nem `nickname`. Não há dado
pessoal a filtrar porque não há dado pessoal na resposta.

---

## 4. Comparação direta

| Critério | Trilha A (dataset) | Trilha B (API) |
|---|---|---|
| Volume | 6M títulos | **24.421 medidos** |
| Tempo até o primeiro treino | Horas | **Zero — já pago** |
| **Procedência citável** | **Fraca** (re-upload sem licença) | **Forte** (fonte oficial) |
| **Licença** | **Ausente** | Termos aceitos, mas restritivos |
| Vínculo contratual | Nenhum | Cláusula 6.2 aplica |
| Direito autoral / base de dados | **Incide, não resolvido** | Coberto pela licença de uso |
| LGPD | Não se aplica | Não se aplica |
| Atualidade | 2019 | **2026** |
| Nº de classes | ~10 mil categorias | 1.412 domínios (357 com ≥10) |
| Campos | `title`, `category` | `nome`, `domain_id`, marca, modelo, atributos, variações, status, preço |
| Infraestrutura | Baixa | **Baixa** — sem browser, HTTPS ou rotação |
| Risco de cronograma | Baixo | **Baixo** — cadastro feito e validando |

---

## 5. A decisão

**Trilha B.** Não por preferência: porque os dois custos que a tornavam arriscada
já foram pagos, e os dados estão em disco.

A pergunta que antes decidiria —

> **A disciplina exige que os dados sejam coletados pelo aluno?**

— **deixou de decidir**, porque a Trilha B ganha nos dois cenários:

| Resposta | Trilha | Por quê |
|---|---|---|
| **Sim, coleta é requisito** | **B** | Requisito atendido pela via oficial |
| **Não, o foco é o modelo** | **B ainda assim** | Procedência forte custa zero agora; a Trilha A carrega licença ausente de graça |
| Quer o melhor resultado possível | **Híbrida** (§6) | A como escala, B como teste externo de 2026 |

A única razão remanescente para a Trilha A é **escala**, e ela ficou mais fraca por
dois motivos independentes:

1. **O baseline não saturou:** macro-F1 **0,852** em 357 classes, em 11 segundos.
   Não há sinal de que faltem dados.
2. **A escala da Trilha B era subestimada.** 24.421 é o teto de um vocabulário de
   134 termos, não da API. Existem 11.045 termos disponíveis sem coletar nada novo,
   e o rendimento marginal medido é de ~140 produtos inéditos por termo novo. A
   diferença deixou de ser 6M contra 24k; virou 6M contra algumas dezenas de
   milhares, alcançáveis em minutos (`src/coleta/coleta_expandida.py`).

**Ressalva importante, e é metodológica, não técnica:** ampliar não corrige o viés
de cauda longa. A busca por `q=` continua não achando os campeões de venda — mais
termos trazem mais cauda. Ampliar ajuda nas classes com poucos exemplos; **não
ajuda em representatividade.**

---

## 6. A trilha híbrida, se houver tempo

As duas não são exclusivas, e combiná-las é provavelmente o melhor trabalho:

1. **Treine no dataset de 2019** (6M títulos) — escala que a API não dá.
2. **Teste nos 24.421 produtos de 2026** coletados por você.
3. **Meça o *drift*:** um modelo treinado em 2019 ainda classifica produto de 2026?

Isso **inverte as fraquezas em resultado**: a desatualização da Trilha A e o volume
modesto da Trilha B deixam de ser limitações e passam a ser as duas pontas de uma
análise de deriva temporal — contribuição legítima, e defensável justamente porque
declara a procedência de cada metade em vez de esconder.

Ressalva: as taxonomias diferem. O dataset de 2019 usa `category`; o CSV de 2026
usa `domain_id`. Use `dados/categorias_mlb.csv` como checagem de sanidade antes de
assumir que os rótulos casam.

---

## 7. Se usar a Trilha A, declare

1. Filtre `language == "portuguese"` e `label_quality == "reliable"`.
2. **Não republique** o dataset nem o modelo treinado nele.
3. **Declare a procedência no relatório.** Texto sugerido:

   > Os dados provêm do MeLi Data Challenge 2019 (Mercado Libre S.R.L.), cuja
   > tarefa original era a classificação de títulos de produtos em categorias.
   > A fonte oficial encontra-se indisponível desde então, e o conjunto foi
   > obtido por meio de republicação de terceiros que não declara licença
   > explícita. O uso nesta pesquisa é exclusivamente acadêmico, sem
   > redistribuição dos dados nem do modelo treinado.

**Declarar é o que torna a escolha defensável. Omitir é o que a torna
indefensável.**

---

## 8. Status de verificação

| Afirmação | Como foi verificado |
|---|---|
| Fonte oficial do Challenge fora do ar | `curl` em 5 caminhos -> 503; bucket S3 -> `NoSuchBucket` |
| Dataset HF existe e baixa | API do HF + range request -> `206`, ~137 MB |
| **Licença ausente** | Metadados do HF: campo de licença **inexistente** |
| 36 downloads, 0 likes | API do HF |
| Licença 2019 (nenhuma) vs 2020 (CC BY-NC-SA) | Páginas de regras recuperadas via Wayback CDX |
| `redirect_uri` exige HTTPS | Doc oficial, citação literal |
| 1 aplicação por conta no Brasil | Doc oficial, citação literal |
| `client_credentials` funciona | `POST /oauth/token` -> 200, `APP_USR-...`, `expires_in: 21600`, sem `refresh_token` |
| Existem **dois** 403 distintos | `forbidden/forbidden` sem token vs `"At least one policy returned UNAUTHORIZED"` com token sem escopo |
| Escopo era configurável, não fatal | Habilitados no DevCenter -> 34 escopos, rotas abriram |
| `/sites/MLB/search` segue fechada | 403 com os 34 escopos |
| `/products/search` responde 200 | Coleta real de 24.421 produtos |
| `offset` máximo é 100 | Busca binária: `100` -> 200; `101` -> `400 Invalid arguments` |
| `paging.total: 10000` é fantasia | O teto de `offset` limita a 200/consulta |
| Produto de catálogo não tem vendedor | Inspeção do objeto: sem `seller_id`, sem `nickname` |
| 24.421 produtos / 1.412 domínios | `coleta_produtos.py`, 8min04s, 134 termos, zero 429 |
| Integridade do CSV | 24.421 linhas pelo módulo `csv`, ids únicos, nenhum campo obrigatório vazio |
| Baseline viável | Corte ≥10 -> 357 classes; **acurácia 0,914 / macro-F1 0,852** em 11 s |
| Só 1% de sobreposição com mais vendidos | 14 de 1.218 produtos ranqueados estão no CSV |

**Não verificado:** se existe espelho do MeLiDC no **Kaggle** com licença
declarada (a API do Kaggle exige autenticação). Se houver, a avaliação da Trilha A
muda — vale checar manualmente antes de descartá-la de vez.
