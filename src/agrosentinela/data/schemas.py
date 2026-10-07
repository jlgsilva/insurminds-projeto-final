"""
Esquemas canônicos dos conjuntos de dados curados.

O ETL do Banco Central e o gerador de demonstração produzem **exatamente
as mesmas colunas**, de modo que o aplicativo não sabe (nem precisa saber)
qual das duas origens está em uso. Isso mantém o app testável offline e
garante que trocar a fonte não quebre nenhuma página.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

# --------------------------------------------------------------------------
# municipios — referência geográfica e de risco por município
# --------------------------------------------------------------------------
MUNICIPIOS_COLS: dict[str, str] = {
    "cd_ibge": "int64",
    "municipio": "string",
    "uf": "string",
    "regiao": "string",
    "lat": "float64",
    "lon": "float64",
    "aliquota_proagro": "float64",   # alíquota básica do Proagro (%)
    "polo_agricola": "string",
    "fonte": "string",
}

# --------------------------------------------------------------------------
# carteira — uma linha por operação de crédito rural (Sicor)
# --------------------------------------------------------------------------
CARTEIRA_COLS: dict[str, str] = {
    # identificação (Sicor)
    "ref_bacen": "string",           # REF_BACEN
    "nu_ordem": "int64",             # NU_ORDEM
    "cnpj_if": "string",             # CNPJ_IF
    "instituicao": "string",         # SICOR_LISTA_IFS
    # localização
    "cd_ibge": "int64",              # SICOR_COMPLEMENTO_OPERACAO_BASICA
    "municipio": "string",
    "uf": "string",
    "regiao": "string",
    "lat": "float64",
    "lon": "float64",
    # empreendimento
    "cd_empreendimento": "string",   # CD_EMPREENDIMENTO
    "produto": "string",             # Produto.csv
    "cultura": "string",             # cultura interna (catalogo.py)
    "atividade": "string",
    "modalidade": "string",
    "finalidade": "string",
    # programa e enquadramento
    "cd_programa": "string",
    "programa": "string",            # Programa.csv
    "categoria_emitente": "string",  # CategoriaEmitente.csv
    "fonte_recurso": "string",       # FonteRecursos.csv
    # datas do ciclo (usadas para a fase fenológica)
    "dt_emissao": "datetime64[ns]",
    "dt_vencimento": "datetime64[ns]",
    "dt_inic_plantio": "datetime64[ns]",
    "dt_fim_plantio": "datetime64[ns]",
    "dt_inic_colheita": "datetime64[ns]",
    "dt_fim_colheita": "datetime64[ns]",
    # valores
    "valor_credito": "float64",      # VL_PARC_CREDITO
    "area_ha": "float64",            # VL_AREA_FINANC
    "produtividade_prevista": "float64",   # VL_PREV_PROD
    "receita_bruta_esperada": "float64",   # VL_RECEITA_BRUTA_ESPERADA
    "unidade_medida": "string",
    # risco e cobertura
    "cd_tipo_seguro": "string",      # CD_TIPO_SEGURO
    "tipo_seguro": "string",         # TipoGarantiaEmpreendimento.csv
    "tem_cobertura": "bool",
    "aliquota_proagro": "float64",   # VL_ALIQ_PROAGRO
    "irrigada": "bool",              # CD_TIPO_IRRIGACAO
    # público-alvo
    "persona": "string",
    "safra": "string",
}

# --------------------------------------------------------------------------
# proagro_sinistros — histórico agregado de COP/RCP por município x evento
# --------------------------------------------------------------------------
SINISTROS_COLS: dict[str, str] = {
    "cd_ibge": "int64",
    "uf": "string",
    "cultura": "string",
    "evento": "string",              # código interno do evento climático
    "evento_proagro": "string",      # rótulo original em EventoProagro.csv
    "ano_inicio": "int64",
    "ano_fim": "int64",
    "n_operacoes": "int64",
    "n_cop": "int64",                # pedidos de cobertura
    "n_rcp": "int64",                # comprovações de perdas
    "freq_evento": "float64",        # participação do evento nos sinistros
    "taxa_acionamento": "float64",   # n_cop / n_operacoes
    "valor_indenizado": "float64",
    # --- cadeia completa COP -> RCP -> súmula -> parcelas ---------------
    "n_deferidos": "int64",          # SICOR_SUMULA_JULGAMENTO
    "taxa_comprovacao": "float64",   # n_rcp / n_cop  (a perícia confirmou?)
    "taxa_deferimento": "float64",   # n_deferidos / n_cop (foi pago?)
    "perda_media_pct": "float64",    # VL_PERDA_COMPROVADA / produção esperada
    "valor_coberto": "float64",      # SICOR_PARCELAS_PROAGRO
    "prazo_medio_pagamento_dias": "float64",
    "motivo_negativa_frequente": "string",
}

# --------------------------------------------------------------------------
# serie_credito — evolução do crédito rural (para a página analítica)
# --------------------------------------------------------------------------
SERIE_COLS: dict[str, str] = {
    "ano": "int64",
    "uf": "string",
    "cultura": "string",
    "n_operacoes": "int64",
    "valor_credito": "float64",
    "area_ha": "float64",
}


# --------------------------------------------------------------------------
# glebas — geometria das áreas financiadas (SICOR_GLEBAS_WKT)
#
# É o salto de precisão do projeto: com a gleba, a consulta climática deixa
# de ser no centroide do município (que em Ribas do Rio Pardo fica a 80 km
# da lavoura) e passa a ser no centroide do próprio talhão.
# --------------------------------------------------------------------------
GLEBAS_COLS: dict[str, str] = {
    "ref_bacen": "string",
    "nu_ordem": "int64",
    "nu_gleba": "int64",
    "cd_ibge": "int64",
    "uf": "string",
    "lat": "float64",              # centroide do polígono
    "lon": "float64",
    "area_gleba_ha": "float64",    # área declarada no Sicor
    "area_wkt_ha": "float64",      # área calculada a partir da geometria
    "divergencia_area_pct": "float64",
    "cultura": "string",
    "tem_geometria": "bool",
}

# --------------------------------------------------------------------------
# exposicao — posição financeira por operação (saldos, liberação, renegociação)
#
# Converte "área em risco" em "dinheiro em risco", que é a única unidade em
# que gerente de crédito, atuário e gestor de política conversam.
# --------------------------------------------------------------------------
EXPOSICAO_COLS: dict[str, str] = {
    "ref_bacen": "string",
    "nu_ordem": "int64",
    "cd_ibge": "int64",
    "uf": "string",
    "dt_posicao": "datetime64[ns]",
    "saldo_devedor": "float64",
    "saldo_vencido": "float64",
    "valor_liberado": "float64",
    "valor_a_liberar": "float64",
    "proxima_parcela": "datetime64[ns]",
    "renegociada": "bool",
    "dias_em_atraso": "int64",
    "faixa_atraso": "string",
}

# --------------------------------------------------------------------------
# contexto_externo — enriquecimento municipal por fontes públicas livres
#
# Toda coluna aqui vem de fonte gratuita e pública, e a procedência de cada
# uma viaja junto em ``origem_contexto`` — o aplicativo nunca apresenta um
# valor de referência embutido como se fosse consulta ao vivo.
# --------------------------------------------------------------------------
CONTEXTO_COLS: dict[str, str] = {
    "cd_ibge": "int64",
    "municipio": "string",
    "uf": "string",
    "regiao": "string",
    "chuva_normal_mm_mes": "float64",      # NASA POWER
    "temp_normal_c": "float64",            # NASA POWER
    "rendimento_ref_kg_ha": "float64",     # IBGE / PAM
    "cultura_referencia": "string",
    "penetracao_seguro_privado": "float64",  # PSR / MAPA
    "bioma": "string",                     # MapBiomas
    "frac_lavoura": "float64",
    "frac_pastagem": "float64",
    "frac_nativa": "float64",
    "perfil_uso": "string",
    "focos_calor_24h": "float64",          # INPE Queimadas
    "classe_seca": "string",               # Monitor de Secas
    "severidade_seca": "float64",
    "origem_contexto": "string",
}


@dataclass(frozen=True)
class Dataset:
    nome: str
    colunas: dict[str, str]
    descricao: str
    origem_bcb: str


DATASETS: tuple[Dataset, ...] = (
    Dataset(
        "municipios",
        MUNICIPIOS_COLS,
        "Referência geográfica, com centroide e alíquota básica do Proagro.",
        "MunicipiosSicor.csv + AliquotaBaseProagro.csv + centroides IBGE",
    ),
    Dataset(
        "carteira",
        CARTEIRA_COLS,
        "Operações de crédito rural vigentes, com empreendimento, datas do "
        "ciclo, valores e cobertura de risco.",
        "SICOR_OPERACAO_BASICA_ESTADO_AAAA.gz + "
        "SICOR_COMPLEMENTO_OPERACAO_BASICA.gz + tabelas de domínio",
    ),
    Dataset(
        "proagro_sinistros",
        SINISTROS_COLS,
        "Histórico de pedidos de cobertura e comprovações de perdas do "
        "Proagro, agregado por município, cultura e evento.",
        "SICOR_COP_BASICO.gz + SICOR_RCP_BASICO.gz + EventoProagro.csv",
    ),
    Dataset(
        "serie_credito",
        SERIE_COLS,
        "Série anual de contratações por UF e cultura.",
        "SICOR_OPERACAO_BASICA_ESTADO_AAAA.gz (2013 em diante)",
    ),
    Dataset(
        "glebas",
        GLEBAS_COLS,
        "Centroide e área de cada gleba financiada, com conferência entre a "
        "área declarada e a área do polígono.",
        "sicor_glebas_wkt_AAAA.gz + SICOR_GLEBAS_CONTRAT.gz + "
        "SICOR_PROPRIEDADES.gz",
    ),
    Dataset(
        "exposicao",
        EXPOSICAO_COLS,
        "Saldo devedor, saldo vencido, desembolso e marca de renegociação por "
        "operação — a exposição financeira corrente da carteira.",
        "SICOR_SALDOS_AAAA.gz + SICOR_LIBERACAO_RECURSOS.gz + "
        "SICOR_PARCELAS_DESEMBOLSO.gz + SICOR_LISTA_RENEGOCIACAO.gz",
    ),
    Dataset(
        "contexto_externo",
        CONTEXTO_COLS,
        "Enriquecimento municipal com fontes externas gratuitas e públicas: "
        "normais climáticas, produtividade, seguro privado, uso do solo, "
        "focos de calor e classificação oficial de seca.",
        "NASA POWER + IBGE SIDRA + PSR/MAPA + MapBiomas + INPE Queimadas + "
        "Monitor de Secas (ANA)",
    ),
)

DATASETS_OPCIONAIS = ("glebas", "exposicao", "contexto_externo")
"""
Conjuntos que enriquecem a solução, mas cuja ausência não a interrompe.

O aplicativo detecta o que existe e adapta o que mostra, em vez de exigir
que o usuário rode o ETL completo — decisão que mantém a prova de conceito
publicável no plano gratuito do Streamlit Cloud.
"""

DATASETS_POR_NOME = {d.nome: d for d in DATASETS}


def aplicar_esquema(df: pd.DataFrame, colunas: dict[str, str]) -> pd.DataFrame:
    """
    Garante que o DataFrame tenha exatamente as colunas do esquema, na
    ordem certa e com os tipos corretos. Colunas faltantes são criadas
    vazias; colunas extras são preservadas ao final (úteis para depuração).
    """
    out = df.copy()
    for col, tipo in colunas.items():
        if col not in out.columns:
            if tipo.startswith("datetime"):
                out[col] = pd.NaT
            elif tipo == "bool":
                out[col] = False
            elif tipo.startswith(("int", "float")):
                out[col] = 0
            else:
                out[col] = pd.NA
        try:
            if tipo.startswith("datetime"):
                out[col] = pd.to_datetime(out[col], errors="coerce")
            elif tipo == "bool":
                out[col] = out[col].fillna(False).astype(bool)
            elif tipo.startswith("int"):
                out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype("int64")
            elif tipo.startswith("float"):
                out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")
            else:
                out[col] = out[col].astype("string")
        except (TypeError, ValueError):
            pass
    extras = [c for c in out.columns if c not in colunas]
    return out[list(colunas.keys()) + extras]


def validar(df: pd.DataFrame, dataset: str) -> list[str]:
    """Devolve a lista de problemas encontrados (vazia = tudo certo)."""
    problemas: list[str] = []
    esquema = DATASETS_POR_NOME.get(dataset)
    if esquema is None:
        return [f"Dataset desconhecido: {dataset}"]
    if df is None or df.empty:
        return [f"{dataset}: conjunto vazio"]
    faltando = [c for c in esquema.colunas if c not in df.columns]
    if faltando:
        problemas.append(f"{dataset}: colunas ausentes -> {', '.join(faltando)}")
    if dataset == "carteira":
        if df["valor_credito"].fillna(0).le(0).all():
            problemas.append("carteira: nenhum valor de crédito positivo")
        if df["cd_ibge"].nunique() < 1:
            problemas.append("carteira: nenhum município identificado")
        nulos_geo = df["lat"].isna().mean() if "lat" in df.columns else 1.0
        if nulos_geo > 0.2:
            problemas.append(
                f"carteira: {nulos_geo:.0%} das operações sem coordenada — "
                "o alerta climático depende da localização"
            )
    if dataset == "municipios":
        dup = df["cd_ibge"].duplicated().sum() if "cd_ibge" in df.columns else 0
        if dup:
            problemas.append(f"municipios: {dup} códigos IBGE duplicados")
    return problemas


def resumo_dataset(df: pd.DataFrame) -> dict[str, Any]:
    """Estatística descritiva rápida, exibida na página de documentação."""
    if df is None or df.empty:
        return {"linhas": 0, "colunas": 0}
    return {
        "linhas": int(len(df)),
        "colunas": int(df.shape[1]),
        "memoria_mb": round(df.memory_usage(deep=True).sum() / 1e6, 2),
        "nulos_pct": round(float(df.isna().mean().mean()) * 100, 1),
    }
