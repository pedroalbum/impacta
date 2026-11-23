"""Caminhos e parâmetros comuns.

Os dados do Mercado Livre NÃO ficam no repositório (Termos da API proíbem republicar).
Procure-os em `dados/` (padrão) ou aponte outra pasta com a variável de ambiente DADOS_DIR.
Arquivos esperados: produtos_mlb_expandido.csv e mercado_livre_limpo_FINAL.xlsx.
"""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]          # raiz do repositório
DADOS = Path(os.getenv("DADOS_DIR", RAIZ / "dados")).expanduser()
SAIDA = RAIZ / "saida"
FIGURAS = SAIDA / "figuras"


def _achar(nome):
    """Procura o arquivo em DADOS e, se não achar, na raiz; falha com mensagem clara."""
    for pasta in (DADOS, RAIZ):
        if (pasta / nome).exists():
            return pasta / nome
    raise FileNotFoundError(f"{nome} não encontrado em {DADOS} nem em {RAIZ}. Veja dados/README.md "
                            "ou defina DADOS_DIR.")


PLANILHA = _achar("mercado_livre_limpo_FINAL.xlsx")
CSV_PRODUTOS = _achar("produtos_mlb_expandido.csv")

SEMENTE = 42
AMPLITUDE_MAX = 100.0   # filtro declarado no relatório (amplitude_pct <= 100)
MIN_PRODUTOS_DOMINIO = 12
N_FAIXAS = 4            # quartis dentro do domínio
TAM_TESTE = 0.2
SEMENTES_REPETICAO = [42, 7, 123, 2024, 99]  # repetições do split para medir estabilidade

# Features permitidas. Proibidas por vazarem o alvo: preco_min, preco_max, preco_mediana, amplitude_pct.
# n_anuncios fora: mede oferta/concorrência, é censurado em 100 e só existe depois de observar os anúncios.
FEATURES_NUM = ["frete_gratis_pct", "n_atributos", "n_variacoes"]
FEATURES_CAT = ["domain_id", "marca", "modelo"]
FEATURE_TEXTO = "nome"
PROIBIDAS = {"preco_min", "preco_max", "preco_mediana", "amplitude_pct", "n_anuncios", "faixa_preco"}
