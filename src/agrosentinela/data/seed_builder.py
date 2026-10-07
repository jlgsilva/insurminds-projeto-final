"""
Gerador da **carteira de demonstração**.

Por que existe: os microdados do Sicor somam dezenas de gigabytes e não
podem ser versionados no GitHub nem carregados em um contêiner gratuito do
Streamlit Cloud. Para que a solução seja *executável por qualquer avaliador
em menos de um minuto*, o projeto embarca uma carteira sintética que:

* usa **exatamente o mesmo esquema** da carteira real produzida pelo ETL;
* reproduz as **proporções observadas** nos microdados do Sicor — dominância
  de soja e milho, concentração em MT/PR/RS/GO, predominância do Pronaf em
  número de contratos e das demais linhas em valor, cobertura de Proagro
  concentrada em custeio agrícola de menor porte;
* respeita a **sazonalidade real** do calendário agrícola brasileiro, de
  modo que as datas de plantio e colheita façam sentido na data de execução.

Nada aqui substitui o dado oficial: é um *fixture* de demonstração,
claramente identificado pela coluna ``fonte``.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from ..rules.catalogo import CULTURAS_POR_CODIGO, EVENTOS
from ..personas import inferir_persona_do_mutuario
from .municipios_seed import municipios_seed
from .schemas import (
    CARTEIRA_COLS,
    CONTEXTO_COLS,
    EXPOSICAO_COLS,
    GLEBAS_COLS,
    MUNICIPIOS_COLS,
    SERIE_COLS,
    SINISTROS_COLS,
    aplicar_esquema,
)

SEMENTE_PADRAO = 20260913  # data-limite do Desafio 5 — resultado reprodutível

# --------------------------------------------------------------------------
# Parâmetros calibrados a partir do perfil público do Sicor
# --------------------------------------------------------------------------

# Participação de cada cultura no número de contratos (aproximação do Sicor).
MIX_CULTURAS: dict[str, float] = {
    "SOJA": 0.255, "MILHO": 0.165, "MILHO_2SAFRA": 0.055, "CAFE": 0.075,
    "PASTAGEM": 0.070, "BOVINOS": 0.080, "CANA": 0.045, "ARROZ": 0.040,
    "FEIJAO": 0.045, "TRIGO": 0.035, "ALGODAO": 0.025, "MANDIOCA": 0.025,
    "LARANJA": 0.020, "UVA": 0.015, "MACA": 0.010, "HORTALICAS": 0.025,
    "OUTRAS": 0.015,
}

# Culturas plausíveis por região (evita soja em larga escala onde não há).
CULTURAS_POR_REGIAO: dict[str, tuple[str, ...]] = {
    "Centro-Oeste": ("SOJA", "MILHO", "MILHO_2SAFRA", "ALGODAO", "PASTAGEM", "BOVINOS", "CANA", "FEIJAO"),
    "Sul": ("SOJA", "MILHO", "TRIGO", "ARROZ", "UVA", "MACA", "FEIJAO", "BOVINOS", "PASTAGEM", "HORTALICAS"),
    "Sudeste": ("CAFE", "CANA", "SOJA", "MILHO", "LARANJA", "BOVINOS", "PASTAGEM", "FEIJAO", "HORTALICAS"),
    "Nordeste": ("SOJA", "ALGODAO", "FEIJAO", "MANDIOCA", "CAFE", "BOVINOS", "CANA", "HORTALICAS", "MILHO"),
    "Norte": ("SOJA", "MILHO", "BOVINOS", "PASTAGEM", "MANDIOCA", "CAFE", "ARROZ", "OUTRAS"),
}

# Peso relativo de cada UF no número de operações (proxy do Sicor).
PESO_UF: dict[str, float] = {
    "RS": 0.155, "PR": 0.140, "MG": 0.120, "SC": 0.075, "SP": 0.075,
    "MT": 0.070, "GO": 0.060, "BA": 0.055, "MS": 0.040, "CE": 0.025,
    "PA": 0.025, "RO": 0.020, "TO": 0.018, "MA": 0.018, "PI": 0.015,
    "ES": 0.015, "PE": 0.014, "PB": 0.010, "AL": 0.008, "SE": 0.008,
    "RN": 0.008, "AM": 0.006, "AC": 0.005, "AP": 0.004, "RR": 0.004,
    "DF": 0.004, "RJ": 0.003,
}

PROGRAMAS = (
    # (código, descrição, participação em nº de contratos, faixa de valor)
    ("0001", "PRONAF - Programa Nacional de Fortalecimento da Agricultura Familiar", 0.52, (4_000, 190_000)),
    ("0002", "PRONAMP - Programa Nacional de Apoio ao Médio Produtor Rural", 0.17, (60_000, 900_000)),
    ("0999", "Recursos Obrigatórios / Livres - Demais Produtores", 0.20, (120_000, 6_500_000)),
    ("0013", "MODERFROTA - Modernização da Frota de Tratores", 0.04, (150_000, 1_800_000)),
    ("0018", "INOVAGRO - Incentivo à Inovação Tecnológica", 0.03, (120_000, 1_500_000)),
    ("0022", "ABC+ - Programa para Agricultura de Baixa Emissão de Carbono", 0.02, (150_000, 2_500_000)),
    ("0028", "PCA - Programa para Construção e Ampliação de Armazéns", 0.02, (300_000, 5_000_000)),
)

CATEGORIAS_EMITENTE = (
    ("01", "Produtor rural - pessoa física", 0.78),
    ("02", "Produtor rural - pessoa jurídica", 0.09),
    ("03", "Cooperativa de produção agropecuária", 0.07),
    ("04", "Condomínio / parceria rural", 0.04),
    ("05", "Associação de produtores", 0.02),
)

FONTES_RECURSO = (
    ("0100", "Recursos obrigatórios (MCR 6-2)", 0.31),
    ("0300", "Poupança rural - controlados", 0.22),
    ("0800", "BNDES / Finame rural", 0.13),
    ("0900", "Fundos constitucionais (FCO/FNE/FNO)", 0.12),
    ("1000", "LCA - Letra de Crédito do Agronegócio", 0.11),
    ("0200", "Recursos livres", 0.11),
)

INSTITUICOES = (
    ("00000000", "Banco do Brasil S.A.", 0.32),
    ("00360305", "Caixa Econômica Federal", 0.06),
    ("90400888", "Banco Santander (Brasil) S.A.", 0.07),
    ("60746948", "Banco Bradesco S.A.", 0.08),
    ("60872504", "Itaú Unibanco S.A.", 0.06),
    ("01181521", "Sicredi - Sistema de Crédito Cooperativo", 0.17),
    ("02038232", "Sicoob - Sistema de Cooperativas de Crédito", 0.14),
    ("04902979", "Banco do Nordeste do Brasil S.A.", 0.06),
    ("04814563", "Banco da Amazônia S.A.", 0.04),
)

TIPOS_SEGURO = (
    ("1", "Proagro", 0.30, True),
    ("2", "Proagro Mais (agricultura familiar)", 0.19, True),
    ("3", "Seguro rural privado (PSR)", 0.13, True),
    ("4", "Sem cobertura de risco declarada", 0.38, False),
)

MODALIDADES = (("01", "Custeio", 0.63), ("02", "Investimento", 0.27), ("03", "Comercialização", 0.10))
ATIVIDADES = (("1", "Agrícola", 0.74), ("2", "Pecuária", 0.26))
FINALIDADES = (("1", "Custeio agrícola", 0.55), ("2", "Investimento", 0.28),
               ("3", "Custeio pecuário", 0.11), ("4", "Comercialização", 0.06))

# Mês típico de início de plantio por cultura (hemisfério sul).
JANELA_PLANTIO: dict[str, tuple[int, int]] = {
    "SOJA": (10, 12), "MILHO": (9, 11), "MILHO_2SAFRA": (1, 3), "ALGODAO": (11, 1),
    "ARROZ": (9, 11), "FEIJAO": (2, 4), "TRIGO": (4, 6), "CAFE": (9, 11),
    "CANA": (2, 5), "LARANJA": (8, 10), "UVA": (8, 10), "MACA": (8, 10),
    "MANDIOCA": (9, 12), "PASTAGEM": (10, 12), "BOVINOS": (1, 12),
    "HORTALICAS": (1, 12), "OUTRAS": (9, 12),
}

# Produtividade média (unidade da cultura) e preço unitário de referência.
PRODUTIVIDADE: dict[str, tuple[float, float]] = {
    "SOJA": (58.0, 130.0), "MILHO": (110.0, 65.0), "MILHO_2SAFRA": (95.0, 63.0),
    "ALGODAO": (290.0, 145.0), "ARROZ": (135.0, 85.0), "FEIJAO": (32.0, 250.0),
    "TRIGO": (55.0, 78.0), "CAFE": (32.0, 1100.0), "CANA": (78.0, 130.0),
    "LARANJA": (900.0, 45.0), "UVA": (22.0, 3200.0), "MACA": (38.0, 2400.0),
    "MANDIOCA": (22.0, 480.0), "PASTAGEM": (1.4, 4200.0), "BOVINOS": (1.0, 3200.0),
    "HORTALICAS": (35.0, 1800.0), "OUTRAS": (40.0, 300.0),
}


def _escolher(rng: random.Random, itens, pesos_idx: int = -1):
    """Escolha ponderada em uma tupla de tuplas cuja posição ``pesos_idx`` é o peso."""
    pesos = [it[pesos_idx] if pesos_idx >= 0 else it[-1] for it in itens]
    return rng.choices(itens, weights=pesos, k=1)[0]


def _ts(d) -> "pd.Timestamp | float":
    """Converte data em Timestamp, preservando ausência como NaT."""
    return pd.NaT if d is None else pd.Timestamp(d)


def _data_no_mes(rng: random.Random, ano: int, mes: int) -> date:
    mes = ((mes - 1) % 12) + 1
    dia = rng.randint(1, 28)
    return date(ano, mes, dia)


# Culturas cuja "semeadura" não tem janela definida (pecuária, olerícolas).
_SEM_JANELA = {"BOVINOS", "PASTAGEM", "HORTALICAS", "CANA", "OUTRAS"}


def _sortear_inicio_plantio(rng: random.Random, cultura: str, hoje: date) -> date:
    """
    Sorteia a data de início de semeadura respeitando o calendário agrícola.

    A operação é alocada à safra corrente ou à anterior, de forma que a
    carteira resultante tenha lavouras em **todas as fases fenológicas** na
    data de execução — condição necessária para demonstrar o motor de regras.
    """
    if cultura in _SEM_JANELA:
        # Ciclo contínuo: distribui ao longo dos últimos 12 meses.
        return hoje - timedelta(days=rng.randint(0, 360))

    mes_ini, mes_fim = JANELA_PLANTIO.get(cultura, (9, 12))
    # Meses válidos da janela, tratando viradas de ano (ex.: nov -> jan)
    if mes_fim >= mes_ini:
        meses = list(range(mes_ini, mes_fim + 1))
    else:
        meses = list(range(mes_ini, 13)) + list(range(1, mes_fim + 1))

    candidatas: list[date] = []
    for ano in (hoje.year - 1, hoje.year):
        for mes in meses:
            # Meses após a virada pertencem ao ano seguinte da janela
            ano_efetivo = ano + 1 if (mes_fim < mes_ini and mes <= mes_fim) else ano
            d = _data_no_mes(rng, ano_efetivo, mes)
            # Mantém apenas safras plausivelmente vivas na data de referência
            if -400 <= (d - hoje).days <= 60:
                candidatas.append(d)
    if not candidatas:
        return hoje - timedelta(days=rng.randint(30, 200))

    # Pondera fortemente as safras mais recentes: assim a maior parte das
    # operações da carteira está com o ciclo em andamento na data de hoje,
    # que é o universo efetivamente sujeito a alerta climático.
    pesos = [1.0 / (1.0 + abs((d - hoje).days) / 110.0) for d in candidatas]
    return rng.choices(candidatas, weights=pesos, k=1)[0]


# ==========================================================================
# Carteira
# ==========================================================================

def gerar_carteira(
    n_operacoes: int = 4200,
    *,
    semente: int = SEMENTE_PADRAO,
    data_ref: date | None = None,
) -> pd.DataFrame:
    """Gera a carteira sintética de operações de crédito rural."""
    rng = random.Random(semente)
    np_rng = np.random.default_rng(semente)
    hoje = data_ref or date.today()

    munis = municipios_seed()
    # Peso de cada município: peso da UF dividido entre seus municípios.
    munis = munis.copy()
    munis["peso_uf"] = munis["uf"].map(PESO_UF).fillna(0.004)
    munis["n_na_uf"] = munis.groupby("uf")["cd_ibge"].transform("count")
    munis["peso"] = munis["peso_uf"] / munis["n_na_uf"]
    munis["peso"] = munis["peso"] / munis["peso"].sum()

    idx = np_rng.choice(len(munis), size=n_operacoes, p=munis["peso"].to_numpy())
    escolhidos = munis.iloc[idx].reset_index(drop=True)

    linhas: list[dict] = []
    for i in range(n_operacoes):
        m = escolhidos.iloc[i]
        regiao = str(m["regiao"])
        candidatas = CULTURAS_POR_REGIAO.get(regiao, tuple(MIX_CULTURAS))
        pesos = [MIX_CULTURAS.get(c, 0.01) for c in candidatas]
        cultura = rng.choices(list(candidatas), weights=pesos, k=1)[0]
        info_cultura = CULTURAS_POR_CODIGO[cultura]

        cd_prog, prog_desc, _, faixa = _escolher(rng, PROGRAMAS, 2)
        cd_cat, cat_desc, _ = _escolher(rng, CATEGORIAS_EMITENTE, 2)
        cd_fonte, fonte_desc, _ = _escolher(rng, FONTES_RECURSO, 2)
        cnpj_if, if_nome, _ = _escolher(rng, INSTITUICOES, 2)
        cd_mod, mod_desc, _ = _escolher(rng, MODALIDADES, 2)
        cd_ativ, ativ_desc, _ = _escolher(rng, ATIVIDADES, 2)
        cd_fin, fin_desc, _ = _escolher(rng, FINALIDADES, 2)

        # Coerência entre programa e modalidade: linhas de investimento do
        # BNDES (Moderfrota, Inovagro, ABC+, PCA) só existem em investimento.
        if cd_prog in {"0013", "0018", "0022", "0028"}:
            cd_mod, mod_desc = "02", "Investimento"
            cd_fin, fin_desc = "2", "Investimento"
        elif cd_mod == "02":
            cd_fin, fin_desc = "2", "Investimento"

        # Coerência: pecuária -> atividade pecuária
        if cultura in {"BOVINOS", "PASTAGEM"}:
            cd_ativ, ativ_desc = "2", "Pecuária"
            if cd_mod == "01":
                cd_fin, fin_desc = "3", "Custeio pecuário"

        # Cobertura de risco: Pronaf tende a Proagro Mais; grande porte, PSR.
        tipos = list(TIPOS_SEGURO)
        pesos_seg = [t[2] for t in tipos]
        if cd_prog == "0001":
            pesos_seg = [0.22, 0.46, 0.05, 0.27]
        elif cd_prog in {"0999", "0028"}:
            pesos_seg = [0.18, 0.02, 0.34, 0.46]
        cd_seg, seg_desc, _, coberto = rng.choices(tipos, weights=pesos_seg, k=1)[0]
        # Investimento raramente tem Proagro
        if cd_mod == "02" and cd_seg in {"1", "2"} and rng.random() < 0.6:
            cd_seg, seg_desc, coberto = "4", "Sem cobertura de risco declarada", False

        valor = float(np.round(rng.uniform(*faixa) * rng.choice([0.6, 0.85, 1.0, 1.0, 1.35]), 2))

        # Área compatível com o valor e com a cultura
        custo_ha = {
            "SOJA": 5600, "MILHO": 5200, "MILHO_2SAFRA": 4200, "ALGODAO": 14500,
            "ARROZ": 8200, "FEIJAO": 6100, "TRIGO": 4300, "CAFE": 16500,
            "CANA": 9200, "LARANJA": 14000, "UVA": 42000, "MACA": 38000,
            "MANDIOCA": 7200, "PASTAGEM": 2400, "BOVINOS": 3100,
            "HORTALICAS": 22000, "OUTRAS": 6000,
        }.get(cultura, 6000)
        area = max(0.5, round(valor / (custo_ha * rng.uniform(0.75, 1.4)), 2))
        if cd_mod != "01":
            area = round(area * rng.uniform(0.3, 0.9), 2)

        # --- Datas do ciclo --------------------------------------------
        # A janela de semeadura respeita o calendário agrícola da cultura;
        # a safra é sorteada entre a corrente e a anterior, de modo que a
        # carteira contenha operações em todas as fases fenológicas.
        dt_ini_plantio = _sortear_inicio_plantio(rng, cultura, hoje)
        dt_fim_plantio = dt_ini_plantio + timedelta(days=rng.randint(10, 35))
        ciclo = info_cultura.ciclo_dias
        dt_ini_colheita = dt_ini_plantio + timedelta(days=int(ciclo * rng.uniform(0.92, 1.02)))
        dt_fim_colheita = dt_ini_colheita + timedelta(days=rng.randint(10, 40))
        dt_emissao = dt_ini_plantio - timedelta(days=rng.randint(15, 120))
        dt_vencimento = dt_fim_colheita + timedelta(days=rng.randint(20, 150))
        sem_ciclo = cd_mod == "02"
        if sem_ciclo:
            # Investimento não declara ciclo de lavoura no Sicor: os campos
            # de plantio e colheita ficam vazios, e a operação entra na
            # carteira apenas para as regras financeiras.
            dt_emissao = hoje - timedelta(days=rng.randint(60, 1400))
            dt_vencimento = dt_emissao + timedelta(days=rng.randint(730, 3650))
            dt_ini_plantio = dt_fim_plantio = dt_ini_colheita = dt_fim_colheita = None

        prod_media, preco = PRODUTIVIDADE.get(cultura, (40.0, 300.0))
        produtividade = round(prod_media * rng.uniform(0.75, 1.25), 2)
        receita = round(produtividade * area * preco, 2)

        persona = inferir_persona_do_mutuario(
            programa_descricao=prog_desc,
            categoria_emitente=cat_desc,
            valor_credito=valor,
            area_financiada=area,
        )

        irrigada = rng.random() < (0.30 if cultura in {"ARROZ", "HORTALICAS", "FEIJAO"} else 0.10)
        aliquota = round(rng.uniform(2.0, 7.5), 2) if coberto and cd_seg in {"1", "2"} else 0.0

        safra_ini = (dt_ini_plantio or dt_emissao).year
        safra = f"{safra_ini}/{str(safra_ini + 1)[-2:]}"

        linhas.append(
            {
                "ref_bacen": f"{rng.randint(10**11, 10**12 - 1)}",
                "nu_ordem": rng.randint(1, 4),
                "cnpj_if": cnpj_if,
                "instituicao": if_nome,
                "cd_ibge": int(m["cd_ibge"]),
                "municipio": str(m["municipio"]),
                "uf": str(m["uf"]),
                "regiao": regiao,
                "lat": float(m["lat"]),
                "lon": float(m["lon"]),
                "cd_empreendimento": f"{cd_ativ}{cd_mod}{cd_fin}{rng.randint(1000, 9999)}",
                "produto": info_cultura.nome,
                "cultura": cultura,
                "atividade": ativ_desc,
                "modalidade": mod_desc,
                "finalidade": fin_desc,
                "cd_programa": cd_prog,
                "programa": prog_desc,
                "categoria_emitente": cat_desc,
                "fonte_recurso": fonte_desc,
                "dt_emissao": pd.Timestamp(dt_emissao),
                "dt_vencimento": pd.Timestamp(dt_vencimento),
                "dt_inic_plantio": _ts(dt_ini_plantio),
                "dt_fim_plantio": _ts(dt_fim_plantio),
                "dt_inic_colheita": _ts(dt_ini_colheita),
                "dt_fim_colheita": _ts(dt_fim_colheita),
                "valor_credito": valor,
                "area_ha": area,
                "produtividade_prevista": produtividade,
                "receita_bruta_esperada": receita,
                "unidade_medida": info_cultura.unidade_produtiva,
                "cd_tipo_seguro": cd_seg,
                "tipo_seguro": seg_desc,
                "tem_cobertura": bool(coberto),
                "aliquota_proagro": aliquota,
                "irrigada": bool(irrigada),
                "persona": persona,
                "safra": safra,
                "fonte": "seed_demonstracao",
            }
        )

    df = pd.DataFrame(linhas)

    # A carteira monitorada é a de operações **vigentes**: mantemos apenas
    # contratos ainda não liquidados, tolerando uma pequena fração vencida
    # (situação real de operações em atraso ou em processo de prorrogação).
    ts_hoje = pd.Timestamp(hoje)
    vigentes = df["dt_vencimento"] >= ts_hoje
    vencidas = df.index[~vigentes]
    manter_vencidas = pd.Index(
        rng.sample(list(vencidas), k=min(len(vencidas), int(0.05 * len(df))))
    )
    df = df.loc[df.index[vigentes].union(manter_vencidas)].reset_index(drop=True)

    return aplicar_esquema(df, CARTEIRA_COLS)


# ==========================================================================
# Histórico de sinistros do Proagro
# ==========================================================================

# Motivos de indeferimento observados com mais frequência no Proagro.
# Aparecem na mensagem ao produtor como orientação preventiva: saber o que
# costuma derrubar um pedido vale mais do que saber que houve um evento.
MOTIVOS_NEGATIVA: tuple[str, ...] = (
    "comunicação da ocorrência fora do prazo regulamentar",
    "ausência de comprovação documental do evento",
    "divergência entre a área declarada e a área periciada",
    "inobservância do zoneamento agrícola de risco climático",
    "produtividade obtida acima do limite de cobertura",
    "uso de cultivar não recomendada para o município",
)


def gerar_sinistros(
    carteira: pd.DataFrame,
    *,
    semente: int = SEMENTE_PADRAO,
    ano_inicio: int = 2013,
    ano_fim: int | None = None,
) -> pd.DataFrame:
    """
    Gera o histórico agregado de COP/RCP por município × cultura × evento.

    A distribuição de eventos por região reproduz o padrão conhecido dos
    microdados do Proagro: seca predomina no Nordeste e no Centro-Oeste;
    excesso hídrico e granizo no Sul; geada no Sul e no Sudeste.
    """
    rng = random.Random(semente + 7)
    ano_fim = ano_fim or date.today().year - 1

    perfil_regional: dict[str, dict[str, float]] = {
        "Sul": {"seca": 0.30, "chuva_excessiva": 0.24, "granizo": 0.16,
                "geada": 0.13, "vendaval": 0.09, "chuva_intensa": 0.05, "onda_calor": 0.03},
        "Sudeste": {"seca": 0.38, "chuva_excessiva": 0.18, "granizo": 0.13,
                    "geada": 0.12, "vendaval": 0.08, "chuva_intensa": 0.07, "onda_calor": 0.04},
        "Centro-Oeste": {"seca": 0.52, "chuva_excessiva": 0.17, "granizo": 0.08,
                         "geada": 0.03, "vendaval": 0.09, "chuva_intensa": 0.07, "onda_calor": 0.04},
        "Nordeste": {"seca": 0.64, "chuva_excessiva": 0.13, "granizo": 0.03,
                     "geada": 0.01, "vendaval": 0.07, "chuva_intensa": 0.07, "onda_calor": 0.05},
        "Norte": {"seca": 0.44, "chuva_excessiva": 0.26, "granizo": 0.04,
                  "geada": 0.01, "vendaval": 0.10, "chuva_intensa": 0.11, "onda_calor": 0.04},
    }
    rotulo_proagro = {
        "seca": "SECA", "chuva_excessiva": "CHUVA EXCESSIVA", "granizo": "GRANIZO",
        "geada": "GEADA", "vendaval": "VENDAVAL",
        "chuva_intensa": "TROMBA D'AGUA", "onda_calor": "VARIACAO EXCESSIVA DE TEMPERATURA",
    }

    base = (
        carteira.groupby(["cd_ibge", "uf", "regiao", "cultura"], as_index=False)
        .agg(n_operacoes=("ref_bacen", "count"), valor=("valor_credito", "sum"))
    )

    linhas = []
    for _, r in base.iterrows():
        perfil = perfil_regional.get(str(r["regiao"]), perfil_regional["Centro-Oeste"])
        # Taxa histórica de acionamento por município (varia 3% a 35%)
        taxa_base = min(0.35, max(0.02, rng.gauss(0.14, 0.07)))
        n_ops_hist = int(r["n_operacoes"] * (ano_fim - ano_inicio + 1) * rng.uniform(0.6, 1.4)) + 1
        n_cop_total = int(n_ops_hist * taxa_base)
        if n_cop_total <= 0:
            continue
        for evento, share in perfil.items():
            share_ajustado = max(0.0, rng.gauss(share, share * 0.22))
            n_cop = int(round(n_cop_total * share_ajustado))
            if n_cop <= 0:
                continue
            # Cadeia real do Proagro: nem todo pedido vira comprovação, e
            # nem toda comprovação vira pagamento. Reproduzir as três taxas
            # separadamente é o que permite à solução responder "qual a
            # chance de o meu pedido ser deferido?" — pergunta que o produtor
            # faz e que a leitura isolada do COP não responde.
            taxa_comprovacao = rng.uniform(0.58, 0.92)
            n_rcp = int(round(n_cop * taxa_comprovacao))
            taxa_deferimento = taxa_comprovacao * rng.uniform(0.80, 0.97)
            n_deferidos = int(round(n_cop * taxa_deferimento))
            valor_indenizado = round(
                n_rcp * (r["valor"] / max(r["n_operacoes"], 1)) * rng.uniform(0.25, 0.75), 2
            )
            valor_coberto = round(valor_indenizado * rng.uniform(0.72, 0.98), 2)
            linhas.append(
                {
                    "cd_ibge": int(r["cd_ibge"]),
                    "uf": str(r["uf"]),
                    "cultura": str(r["cultura"]),
                    "evento": evento,
                    "evento_proagro": rotulo_proagro.get(evento, evento.upper()),
                    "ano_inicio": ano_inicio,
                    "ano_fim": ano_fim,
                    "n_operacoes": n_ops_hist,
                    "n_cop": n_cop,
                    "n_rcp": n_rcp,
                    "freq_evento": 0.0,  # preenchido abaixo
                    "taxa_acionamento": round(n_cop / n_ops_hist, 4),
                    "valor_indenizado": valor_indenizado,
                    "n_deferidos": n_deferidos,
                    "taxa_comprovacao": round(taxa_comprovacao, 4),
                    "taxa_deferimento": round(taxa_deferimento, 4),
                    "perda_media_pct": round(rng.uniform(0.22, 0.78), 4),
                    "valor_coberto": valor_coberto,
                    "prazo_medio_pagamento_dias": round(rng.uniform(45, 180), 1),
                    "motivo_negativa_frequente": rng.choice(MOTIVOS_NEGATIVA),
                    "fonte": "seed_demonstracao",
                }
            )

    df = pd.DataFrame(linhas)
    if df.empty:
        return aplicar_esquema(df, SINISTROS_COLS)

    # freq_evento = participação do evento no total de COP do município/cultura
    total = df.groupby(["cd_ibge", "cultura"])["n_cop"].transform("sum")
    df["freq_evento"] = (df["n_cop"] / total.replace(0, np.nan)).fillna(0.0).round(4)
    return aplicar_esquema(df, SINISTROS_COLS)


# ==========================================================================
# Série histórica de crédito
# ==========================================================================

def gerar_serie_credito(
    carteira: pd.DataFrame,
    *,
    semente: int = SEMENTE_PADRAO,
    ano_inicio: int = 2013,
    ano_fim: int | None = None,
) -> pd.DataFrame:
    """Série anual sintética de contratações por UF e cultura."""
    rng = random.Random(semente + 13)
    ano_fim = ano_fim or date.today().year
    base = (
        carteira.groupby(["uf", "cultura"], as_index=False)
        .agg(n=("ref_bacen", "count"), valor=("valor_credito", "sum"), area=("area_ha", "sum"))
    )
    linhas = []
    for ano in range(ano_inicio, ano_fim + 1):
        # Crescimento nominal médio do crédito rural + ruído
        fator = (1.11 ** (ano - ano_inicio)) * rng.uniform(0.93, 1.07)
        for _, r in base.iterrows():
            linhas.append(
                {
                    "ano": ano,
                    "uf": r["uf"],
                    "cultura": r["cultura"],
                    "n_operacoes": int(max(1, r["n"] * fator * rng.uniform(0.85, 1.15))),
                    "valor_credito": round(float(r["valor"]) * fator * rng.uniform(0.85, 1.15), 2),
                    "area_ha": round(float(r["area"]) * fator * rng.uniform(0.9, 1.1), 2),
                }
            )
    return aplicar_esquema(pd.DataFrame(linhas), SERIE_COLS)


# ==========================================================================
# Municípios enriquecidos
# ==========================================================================

def gerar_municipios(*, semente: int = SEMENTE_PADRAO) -> pd.DataFrame:
    """Tabela de municípios com alíquota do Proagro simulada."""
    rng = random.Random(semente + 3)
    df = municipios_seed()
    df["aliquota_proagro"] = [round(rng.uniform(2.0, 7.5), 2) for _ in range(len(df))]
    return aplicar_esquema(df, MUNICIPIOS_COLS)


# ==========================================================================
# Construção completa
# ==========================================================================

# ==========================================================================
# Glebas de demonstração
# ==========================================================================

def gerar_glebas(
    carteira: pd.DataFrame,
    *,
    semente: int = SEMENTE_PADRAO,
    fracao_com_geometria: float = 0.62,
) -> pd.DataFrame:
    """
    Gera as glebas (talhões) de uma parcela das operações.

    ``fracao_com_geometria`` não é um número arbitrário: nem toda operação do
    Sicor tem gleba publicada, e uma demonstração que fingisse cobertura de
    100% daria uma impressão falsa de precisão. Aqui a cobertura parcial é
    explícita, e as páginas mostram claramente quais alertas usaram centroide
    de talhão e quais recorreram ao centroide do município.
    """
    if carteira is None or carteira.empty:
        return aplicar_esquema(pd.DataFrame(), GLEBAS_COLS)

    rng = random.Random(semente + 11)
    linhas = []
    for _, op in carteira.iterrows():
        if rng.random() > fracao_com_geometria:
            continue
        area_total = float(op.get("area_ha") or 0.0)
        if area_total <= 0:
            continue
        # Operações maiores tendem a ter mais talhões.
        n_glebas = 1 if area_total < 120 else (2 if area_total < 600 else rng.randint(2, 4))
        pesos = [rng.uniform(0.5, 1.5) for _ in range(n_glebas)]
        soma = sum(pesos)
        lat0 = float(op.get("lat") or 0.0)
        lon0 = float(op.get("lon") or 0.0)
        if not lat0 or not lon0:
            continue
        for i in range(n_glebas):
            area = round(area_total * pesos[i] / soma, 2)
            # Dispersão típica dentro do município (até ~25 km do centroide).
            dlat = rng.uniform(-0.22, 0.22)
            dlon = rng.uniform(-0.22, 0.22)
            # A área do polígono raramente bate exatamente com a declarada.
            area_wkt = round(area * rng.uniform(0.93, 1.08), 2)
            divergencia = round(abs(area_wkt - area) / area * 100, 2) if area else 0.0
            linhas.append({
                "ref_bacen": op["ref_bacen"],
                "nu_ordem": int(op.get("nu_ordem") or 1),
                "nu_gleba": i + 1,
                "cd_ibge": int(op.get("cd_ibge") or 0),
                "uf": str(op.get("uf") or ""),
                "lat": round(lat0 + dlat, 6),
                "lon": round(lon0 + dlon, 6),
                "area_gleba_ha": area,
                "area_wkt_ha": area_wkt,
                "divergencia_area_pct": divergencia,
                "cultura": str(op.get("cultura") or ""),
                "tem_geometria": True,
                "fonte": "seed_demonstracao",
            })
    return aplicar_esquema(pd.DataFrame(linhas), GLEBAS_COLS)


# ==========================================================================
# Exposição financeira de demonstração
# ==========================================================================

FAIXAS_ATRASO: tuple[tuple[int, str], ...] = (
    (0, "em dia"), (15, "1 a 15 dias"), (30, "16 a 30 dias"),
    (90, "31 a 90 dias"), (180, "91 a 180 dias"), (10**6, "acima de 180 dias"),
)


def _faixa_atraso(dias: int) -> str:
    for limite, rotulo in FAIXAS_ATRASO:
        if dias <= limite:
            return rotulo
    return "acima de 180 dias"


def gerar_exposicao(
    carteira: pd.DataFrame,
    *,
    semente: int = SEMENTE_PADRAO,
    taxa_inadimplencia: float = 0.058,
    taxa_renegociacao: float = 0.041,
) -> pd.DataFrame:
    """
    Posição financeira por operação: saldo devedor, saldo vencido, liberado,
    a liberar, próxima parcela e marca de renegociação.

    As taxas padrão seguem a ordem de grandeza divulgada para o crédito rural
    brasileiro. O que importa aqui não é acertar o número — é que a estrutura
    seja idêntica à do ETL real, de modo que trocar a fonte não mude uma
    linha do aplicativo.
    """
    if carteira is None or carteira.empty:
        return aplicar_esquema(pd.DataFrame(), EXPOSICAO_COLS)

    rng = random.Random(semente + 13)
    hoje = date.today()
    linhas = []
    for _, op in carteira.iterrows():
        credito = float(op.get("valor_credito") or 0.0)
        if credito <= 0:
            continue
        emissao = op.get("dt_emissao")
        vencimento = op.get("dt_vencimento")
        # Quanto do prazo já correu define quanto já foi amortizado.
        try:
            d_emi = pd.Timestamp(emissao).date()
            d_ven = pd.Timestamp(vencimento).date()
            total_dias = max(1, (d_ven - d_emi).days)
            corridos = max(0, min(total_dias, (hoje - d_emi).days))
            progresso = corridos / total_dias
        except (TypeError, ValueError):
            progresso = rng.uniform(0.1, 0.9)
            d_ven = hoje + timedelta(days=180)

        liberado = round(credito * min(1.0, progresso * rng.uniform(1.1, 1.9)), 2)
        a_liberar = round(max(0.0, credito - liberado), 2)
        # Custeio amortiza no vencimento: o saldo cai pouco antes da colheita.
        saldo = round(credito * max(0.0, 1.0 - progresso * rng.uniform(0.0, 0.45)), 2)

        inadimplente = rng.random() < taxa_inadimplencia
        dias_atraso = rng.randint(1, 420) if inadimplente else 0
        vencido = round(saldo * rng.uniform(0.15, 0.85), 2) if inadimplente else 0.0

        linhas.append({
            "ref_bacen": op["ref_bacen"],
            "nu_ordem": int(op.get("nu_ordem") or 1),
            "cd_ibge": int(op.get("cd_ibge") or 0),
            "uf": str(op.get("uf") or ""),
            "dt_posicao": pd.Timestamp(hoje),
            "saldo_devedor": saldo,
            "saldo_vencido": vencido,
            "valor_liberado": liberado,
            "valor_a_liberar": a_liberar,
            "proxima_parcela": pd.Timestamp(d_ven),
            "renegociada": rng.random() < taxa_renegociacao,
            "dias_em_atraso": dias_atraso,
            "faixa_atraso": _faixa_atraso(dias_atraso),
            "fonte": "seed_demonstracao",
        })
    return aplicar_esquema(pd.DataFrame(linhas), EXPOSICAO_COLS)


# ==========================================================================
# Contexto externo de demonstração
# ==========================================================================

def gerar_contexto_externo(
    municipios: pd.DataFrame,
    *,
    offline: bool = True,
) -> pd.DataFrame:
    """
    Monta o conjunto ``contexto_externo`` chamando os conectores externos em
    modo offline — isto é, com as tabelas de referência embutidas.

    Usar o mesmo caminho de código do ETL real (e não uma geração paralela)
    garante que o esquema não se separe com o tempo: se o conector mudar, a
    demonstração muda junto.
    """
    if municipios is None or municipios.empty:
        return aplicar_esquema(pd.DataFrame(), CONTEXTO_COLS)
    try:
        from ..external import contexto_municipal

        # Offline, a normal vem da tabela regional embutida e não custa
        # requisição nenhuma — então vale calcular para todos os municípios.
        limite = len(municipios) if offline else 60
        ctx, _ = contexto_municipal(municipios, offline=offline,
                                    incluir_normais=True, limite_normais=limite)
    except Exception:  # noqa: BLE001 — o contexto é sempre opcional
        return aplicar_esquema(pd.DataFrame(), CONTEXTO_COLS)
    return aplicar_esquema(ctx, CONTEXTO_COLS)


def construir_seed(
    destino=None,
    *,
    n_operacoes: int = 4200,
    semente: int = SEMENTE_PADRAO,
) -> dict[str, pd.DataFrame]:
    """
    Gera e (opcionalmente) grava todos os conjuntos de demonstração.

    Os arquivos são gravados em ``.csv.gz`` — formato lido por qualquer
    instalação de pandas, sem exigir ``pyarrow``.
    """
    from ..config import SEED_DIR

    destino = destino or SEED_DIR
    carteira = gerar_carteira(n_operacoes, semente=semente)
    municipios = gerar_municipios(semente=semente)
    sinistros = gerar_sinistros(carteira, semente=semente)
    serie = gerar_serie_credito(carteira, semente=semente)

    glebas = gerar_glebas(carteira, semente=semente)
    exposicao = gerar_exposicao(carteira, semente=semente)
    contexto = gerar_contexto_externo(municipios)

    conjuntos = {
        "municipios": municipios,
        "carteira": carteira,
        "proagro_sinistros": sinistros,
        "serie_credito": serie,
        "glebas": glebas,
        "exposicao": exposicao,
        "contexto_externo": contexto,
    }
    if destino is not None:
        from pathlib import Path

        destino = Path(destino)
        destino.mkdir(parents=True, exist_ok=True)
        for nome, df in conjuntos.items():
            df.to_csv(destino / f"{nome}.csv.gz", index=False, compression="gzip")
        manifesto = {
            "gerado_em": datetime.now().isoformat(timespec="seconds"),
            "semente": semente,
            "conjuntos": {k: {"linhas": len(v), "colunas": len(v.columns)} for k, v in conjuntos.items()},
            "aviso": (
                "Dados sintéticos de demonstração. Reproduzem o esquema e as "
                "proporções dos microdados do Sicor/BCB, mas NÃO são dados reais."
            ),
            "eventos_modelados": [e.codigo for e in EVENTOS],
            "cobertura_glebas": (
                round(glebas["ref_bacen"].nunique() / max(len(carteira), 1), 3)
                if not glebas.empty else 0.0
            ),
            "fontes_externas": (
                contexto["origem_contexto"].iloc[0]
                if not contexto.empty and "origem_contexto" in contexto.columns
                else ""
            ),
        }
        import json

        (destino / "manifesto.json").write_text(
            json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return conjuntos


if __name__ == "__main__":  # pragma: no cover
    from ..utils.logging_setup import configurar_logging, get_logger

    configurar_logging("INFO")
    _log = get_logger("seed")
    dados = construir_seed()
    for nome, df in dados.items():
        _log.info("%-20s %6d linhas x %2d colunas", nome, len(df), df.shape[1])
