# dados/

Esta pasta **não é versionada** (só este README). Os dados do Mercado Livre não podem ser republicados (Termos de uso da API, cláusulas 2(f) e 7.4), então cada pessoa gera ou recebe os arquivos localmente.

## Arquivos esperados

| Arquivo | Como obter | Usado por |
|---|---|---|
| `categorias_mlb.csv` | `python src/coleta/coleta_categorias.py` (sem credencial) | coleta |
| `produtos_mlb.csv` | `python src/coleta/coleta_produtos.py 25000` | coleta |
| `produtos_mlb_expandido.csv` | `python src/coleta/coleta_expandida.py 80000 400` | coleta e modelo |
| `valor_mlb.csv` | `python src/coleta/coleta_valor.py` | coleta |
| `valor_mlb_expandido.csv` | `python src/coleta/coleta_valor_expandida.py` | coleta |
| `mercado_livre_limpo_FINAL.xlsx` | planilha consolidada e limpa pela equipe (aba `valor_mlb_expandido` etc.) | modelo |

Os scripts do modelo procuram os arquivos em `dados/` e, se não acharem, na raiz do repositório. Para usar outra pasta: `export DADOS_DIR=/caminho/para/dados`.

A coleta exige credenciais da API (veja `docs/guia-de-coleta.md`). Elas ficam em `~/.config/meli/`, **nunca** neste repositório.
