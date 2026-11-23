## Sugestões de uso, da mais sólida para a mais especulativa

### 3.1 Classificador de domínio — **validado, é a âncora do trabalho**

`nome` -> `domain_id`. Já medido de verdade:

```
corte >=10 exemplos: 357 classes, 21.659 produtos (17.327 treino / 4.332 teste)
TF-IDF char_wb (3-5) + LinearSVC(class_weight='balanced')
acuracia  : 0.914
macro-F1  : 0.852
tempo     : 11 segundos
```

**A análise de erro é o melhor material do relatório.** As confusões mais
frequentes são semanticamente adjacentes:

```
MLB-DRILL_BITS            -> MLB-DRILL_AND_SCREWDRIVER_BITS      6
MLB-ELBOW_SUPPORTS        -> MLB-SPORTS_PROTECTION_ELBOW_PADS    4
MLB-NAUTICAL_CLEATS       -> MLB-NAUTICAL_ROPES                  3
MLB-FOOTBALL_BALLS        -> MLB-HANDBALL_BALLS                  3
```

Vários desses pares são **ambiguidade da própria taxonomia**, não erro do modelo:
"brocas" e "brocas e bits de parafusadeira" se sobrepõem de fato. Argumentar isso
com os dados na mão vale mais que um décimo de macro-F1.

### 3.2 Campeão de venda vs cauda longa — **promissor, com um confundidor sério**

Classificação binária: ranqueado (1.218) contra não-ranqueado (24.421).

**Antes de tentar, entenda o problema:** os dois conjuntos vêm de **rotas
diferentes**. Um modelo pode atingir acurácia altíssima aprendendo artefato de
coleta — um viés de comprimento de título, de marca, de domínio — em vez de
"vende bem". **Acurácia alta aqui é suspeita, não sucesso.**

Mitigações obrigatórias, se for tentar:

- **Balancear por domínio.** Compare campeão e cauda longa **dentro** do mesmo
  `domain_id`, nunca entre domínios diferentes.
- **Verificar comprimento e marca** antes de treinar. Se `nome`.len separa as
  classes, o modelo vai usar isso.
- **Relatar o confundidor no texto**, mesmo que o resultado seja bom.

Feito com honestidade, é um bom trabalho. Feito sem, é um número inflado.

### 3.3 Faixa de preço a partir do título — **viável, com escopo reduzido**

Classificar em faixas (quartis) em vez de regressão sobre valor: `preco_mediana`
é ruidoso pelo agrupamento ruim, e faixa é mais robusta.

**Qual dataset usar, medido:**

```
valor_mlb.csv       1213 com preco -> filtro amplitude<=100% -> 763 produtos
                    mas so 16 dominios ficam com >=10 exemplos
produtos_mlb.csv    ~2757 com preco (11,3% estimado), 1412 dominios
```

**Nenhum dos dois é confortável.** `valor_mlb.csv` tem cobertura perfeita mas
espalha 763 produtos em 245 domínios — **16 classes treináveis é pouco**.
`produtos_mlb.csv` tem mais produtos com preço, mas exige coletar o preço deles
primeiro (~7 min de requisições) e a cobertura é de 11%.

**Caminho recomendado:** rodar a etapa 3 de `coleta_valor.py` sobre os `active` de
`produtos_mlb.csv`, o que rende ~2.757 produtos com preço em 1.412 domínios, e só
então cortar por classe.

- Faixas por **quartil dentro do domínio**, não globais — R$ 100 é caro para caneta
  e barato para geladeira.
- Declare o filtro de amplitude e quantos produtos ele descartou.

**Não** prometa "previsão de preço" com precisão em reais. A dispersão dos dados
não sustenta isso — e `novos_pct` não ajuda a desambiguar, porque é constante
(§2.3).

### 3.4 Detectar anúncio mal agrupado — **original, e usa o defeito como rótulo**

O agrupamento ruim de §2.1 vira o alvo: `amplitude_pct > 200` como rótulo de
"produto com anúncio suspeito". Prever isso a partir de `nome`, `domain_id`,
`n_atributos` e `n_anuncios` é uma tarefa real de qualidade de catálogo.

É o caso de uso mais original desta lista, porque **transforma a limitação
encontrada em objeto de estudo**. Ressalva honesta: o rótulo é uma *proxy* não
validada (§2.1), e isso tem de estar escrito.

### 3.5 Frete grátis a partir de título e preço — **fácil, bom para comparação**

`shipping.free_shipping` é binário e limpo. Medido nos 1.213 produtos:

```
frete_gratis_pct: mediana 75%  media 57%
com 100% dos anuncios em frete gratis: 489 de 1213 (40%)
```

**Tem variância real** — diferente de `novos_pct` (§2.3) — então é alvo utilizável.
Desbalanceado, logo **macro-F1 outra vez**. Serve como segunda tarefa para comparar
arquiteturas sem trocar de dataset.

### 3.6 Classificação hierárquica — **melhora o número principal**

`domain_id` tem estrutura implícita, e `categorias_mlb.csv` traz `raiz` e
`profundidade`. Prever primeiro a raiz e depois o domínio dentro dela tende a
ajudar justamente nas confusões de §3.1, que são intra-raiz.

### 3.7 Descritivo, sem ML — **barato e rende gráfico**

- **Dispersão de preço por domínio:** onde o catálogo agrupa pior.
- **Concorrência:** nº de anúncios por produto — mediana **6**, com **75 produtos
  censurados no teto de 100** (§2.3). Trate o teto como "100 ou mais".
- **Geografia de vendedor:** `seller_address` dá cidade e estado — **mas isso é
  dado pessoal.** Se usar, agregue por estado e **nunca** guarde `seller_id`.
- **Idade do catálogo:** `criado_em` (`date_created`) por domínio.

### 3.8 Série temporal — **só se houver semanas de prazo**

Não há histórico. Rodar `coleta_valor.py` semanalmente constrói a série do zero.
Isso é **espera de calendário**, não trabalho — só vale se o prazo for longo.
Bônus: mediria a estabilidade do ranking, hoje desconhecida.

---

## 4. Duas obrigações ao usar dado de valor

### 4.1 `/products/{id}/items` reintroduz dado pessoal

É a **única** rota deste projeto que devolve `seller_id` e `seller_address`. O
resto do trabalho fica fora da LGPD porque produto de catálogo não tem vendedor —
esta rota é a exceção.

**`src/coleta/coleta_valor.py` descarta os dois na ingestão** e grava só agregados.
Não "enriqueça" o CSV com vendedor: isso traz de volta a cláusula 6.2 e o art. 20
da LGPD que o desenho do projeto evitou de propósito.

### 4.2 O que declarar no relatório

Sem isto, os números de valor não são defensáveis:

1. **Quantidade vendida e faturamento não estão disponíveis na API** — e por quê
   (`/items/{id}` = 403).
2. **Cobertura de preço depende da população: 100%** nos mais vendidos
   (`valor_mlb.csv`), **11,3%** no dataset de busca (23% dos `active`, 0% dos
   `inactive`). São duas populações, não duas amostras.
3. **Qual filtro de `amplitude_pct`** foi usado e quantos produtos descartou
   (`<=100%` preserva 763 de 1.213).
4. **Que `novos_pct` é constante** e portanto foi descartado como feature.
5. **Ranking é ordinal**, posições 1..20, e não se converte em volume de vendas —
   e **preço não correlaciona com posição** (§2.3), o que fecha a porta da
   estimativa de receita por via empírica, não só conceitual.
6. **`produtos_mlb.csv` tem viés de cauda longa** — 1% de sobreposição com os
   mais vendidos. Nenhuma conclusão sobre popularidade sai dele.

---

## 5. Resumo em uma frase

**Preço: sim, com ressalvas. "O que vende mais": sim, como ranking ordinal.
Faturamento: não existe, e estimá-lo produziria um número inventado** — então o
caminho é tratar popularidade como problema de ranking e classificação, que os
dados sustentam, em vez de regressão sobre receita, que eles não sustentam.
