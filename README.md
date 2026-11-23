# Posicionamento de preços no Mercado Livre com Machine Learning

Trabalho da disciplina **Data Project: Modeling & Implementation (DPMI)**, Faculdade Impacta, Equipe 7 (Data Master), seguindo o CRISP-DM.

## O que o projeto faz

Dado um produto do catálogo do Mercado Livre (título, domínio, marca, modelo, atributos e frete grátis), o modelo estima em qual **faixa de preço dentro do domínio** ele está: Q1 (mais barato) a Q4 (mais caro). É classificação ordinal em 4 classes.

Serve como referência para revisão humana de preços. **Não** prevê preço em reais, preço ótimo, vendas nem lucro.

## Resultados (média de 5 divisões, 4.242 produtos, 99 domínios)

| Modelo | macro-F1 com frete grátis | macro-F1 sem frete grátis |
|---|---|---|
| Classe majoritária (linha de base) | 0,11 | – |
| TF-IDF + regressão logística | 0,59 | 0,51 |
| CatBoost | 0,55 | 0,47 |

O frete grátis acompanha o preço (provável regra de elegibilidade da plataforma), por isso os dois cenários são reportados. Detalhes e limitações nos relatórios em `saida/`.

## Estrutura

```
src/coleta/   scripts de extração de dados da API do Mercado Livre
src/modelo/   preparação, treino, avaliação e geração dos relatórios (config.py, alvo.py, 01_ ... 08_)
docs/         documentação da coleta: guia, fonte de dados, viabilidade e dados de valor
dados/        pasta local para os dados (não versionada; veja dados/README.md)
saida/        métricas (CSV/JSON), figuras e os dois relatórios em PDF
AGENTS.md     mapa da API, limites contratuais e armadilhas conhecidas
CLAUDE.md     notas de contexto do projeto
requirements.txt
```

## Dados: não incluídos

Os dados vêm da API oficial do Mercado Livre e **não são publicados aqui**, porque os Termos de uso da API não permitem redistribuí-los. Ficam de fora o catálogo, a planilha, as predições, o modelo treinado e o dashboard. Para reproduzir, gere os dados com os scripts de `src/coleta/` (precisa de credenciais próprias da API, ver `docs/guia-de-coleta.md`) e siga `dados/README.md`. Nenhuma credencial é guardada no projeto.

## Como reproduzir

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 1) Extração (precisa de credenciais da API em ~/.config/meli/ — ver docs/guia-de-coleta.md)
python src/coleta/coleta_categorias.py
python src/coleta/coleta_produtos.py 25000
python src/coleta/coleta_expandida.py 80000 400
python src/coleta/coleta_valor.py
python src/coleta/coleta_valor_expandida.py

# 2) Modelo (precisa de dados/produtos_mlb_expandido.csv e dados/mercado_livre_limpo_FINAL.xlsx)
cd src/modelo
python 01_montar_dataset.py
python 03_baselines_e_modelos.py   # demorado (CatBoost; dezenas de minutos)
python 07_sem_frete.py
python 06_ablacao.py
python 04_analise_erros.py
```

A planilha `mercado_livre_limpo_FINAL.xlsx` é a consolidação feita pela equipe a partir dos CSVs da coleta; ela não é gerada por nenhum script deste repositório.

Os scripts de `src/modelo/` usam semente fixa. Para usar os dados em outra pasta: `export DADOS_DIR=/caminho`.
