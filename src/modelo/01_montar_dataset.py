"""Monta o dataset de modelagem: preços (planilha, origem=busca) + atributos (CSV de 100 mil)."""
import json
import pandas as pd
from config import *

SAIDA.mkdir(exist_ok=True)
log = {}

v = pd.read_excel(PLANILHA, sheet_name="valor_mlb_expandido")
log["valor_mlb_expandido_linhas"] = len(v)
log["origem_contagem"] = v.origem.value_counts(dropna=False).astype(int).to_dict()

b = v[v.origem == "busca"].copy()
log["busca_linhas"] = len(b)
assert b.product_id.is_unique

p = pd.read_csv(CSV_PRODUTOS)
assert p.product_id.is_unique
log["csv_produtos_linhas"] = len(p)
log["busca_ids_no_csv_pct"] = round(float(b.product_id.isin(p.product_id).mean()) * 100, 2)

# validate='1:1' garante que a junção não duplica nem perde linhas
m = b.merge(p.drop(columns=["nome", "domain_id"]), on="product_id", how="left", validate="1:1")
assert len(m) == len(b)
assert m.status.notna().all(), "há produto de busca sem correspondência no CSV completo"
log["apos_juncao"] = len(m)

# preço e amplitude precisam existir; filtro de amplitude declarado no relatório
n0 = len(m)
m = m[m.preco_mediana.notna() & m.amplitude_pct.notna()]
log["descartados_preco_ou_amplitude_nulos"] = n0 - len(m)
n1 = len(m)
m = m[m.amplitude_pct <= AMPLITUDE_MAX]
log["descartados_amplitude_acima_de_100"] = n1 - len(m)
log["apos_filtro_amplitude"] = len(m)

# domínios pequenos não sustentam quartis
cont = m.domain_id.value_counts()
ok = cont[cont >= MIN_PRODUTOS_DOMINIO].index
log["dominios_antes_corte"] = int(cont.size)
m = m[m.domain_id.isin(ok)].copy()
log["dominios_depois_corte"] = int(len(ok))
log["produtos_final"] = len(m)
log["descartados_dominio_pequeno"] = int(cont[cont < MIN_PRODUTOS_DOMINIO].sum())

m["marca"] = m["marca"].fillna("(ausente)")
m["modelo"] = m["modelo"].fillna("(ausente)")
m["tem_marca"] = (m["marca"] != "(ausente)").astype(int)
m = m.reset_index(drop=True)
m.to_csv(SAIDA / "dataset_modelagem.csv", index=False)

log["produtos_por_dominio"] = m.domain_id.value_counts().describe().round(1).to_dict()
log["preco_mediana_resumo"] = m.preco_mediana.describe().round(2).to_dict()
log["frete_gratis_pct_media"] = round(float(m.frete_gratis_pct.mean()), 1)
(SAIDA / "log_dataset.json").write_text(json.dumps(log, indent=2, ensure_ascii=False, default=float))
print(json.dumps(log, indent=2, ensure_ascii=False, default=float))
