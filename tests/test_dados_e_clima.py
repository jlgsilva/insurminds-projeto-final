"""Testes dos indicadores meteorológicos, do catálogo e das personas."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from agrosentinela.data.municipios_seed import (
    UF_BBOX,
    municipios_seed,
    validar_coordenadas,
)
from agrosentinela.data.schemas import CARTEIRA_COLS, aplicar_esquema, validar
from agrosentinela.data.seed_builder import gerar_carteira, gerar_municipios
from agrosentinela.personas import (
    PERSONAS,
    PERSONAS_POR_CODIGO,
    inferir_persona_do_mutuario,
)
from agrosentinela.rules.catalogo import (
    CULTURAS,
    EVENTOS,
    get_cultura,
    mapear_evento_proagro,
    mapear_produto_para_cultura,
    normalizar,
)
from agrosentinela.weather.indicadores import (
    calcular_indicadores,
    probabilidade_granizo,
)
from agrosentinela.weather.open_meteo import (
    Celula,
    SinteticoProvider,
    para_celula,
)


# ==========================================================================
# Municípios
# ==========================================================================

def test_amostra_de_municipios_consistente():
    df = municipios_seed()
    assert len(df) > 80
    assert df["cd_ibge"].duplicated().sum() == 0
    assert df["uf"].nunique() == 27
    assert validar_coordenadas(df).empty, "coordenadas fora do limite da UF"


def test_codigo_ibge_bate_com_a_uf():
    mapa = {
        11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
        21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL",
        28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR",
        42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF",
    }
    df = municipios_seed()
    df["uf_do_codigo"] = (df["cd_ibge"] // 100000).map(mapa)
    divergentes = df[df["uf_do_codigo"] != df["uf"]]
    assert divergentes.empty, divergentes[["cd_ibge", "municipio", "uf"]].to_dict("records")


# ==========================================================================
# Carteira sintética
# ==========================================================================

def test_carteira_sintetica_respeita_o_esquema():
    df = gerar_carteira(600, semente=7)
    assert not df.empty
    assert list(df.columns)[: len(CARTEIRA_COLS)] == list(CARTEIRA_COLS)
    assert validar(df, "carteira") == []
    assert (df["valor_credito"] > 0).all()
    assert (df["area_ha"] > 0).all()


def test_carteira_sintetica_e_reprodutivel():
    a = gerar_carteira(200, semente=99)
    b = gerar_carteira(200, semente=99)
    pd.testing.assert_frame_equal(a, b)


def test_janelas_de_plantio_sao_agronomicas():
    df = gerar_carteira(3000, semente=5)
    custeio = df[(df["modalidade"] == "Custeio") & df["dt_inic_plantio"].notna()]
    esperado = {
        "SOJA": {10, 11, 12},
        "TRIGO": {4, 5, 6},
        "MILHO_2SAFRA": {1, 2, 3},
    }
    for cultura, meses in esperado.items():
        sub = custeio[custeio["cultura"] == cultura]
        if sub.empty:
            continue
        obtidos = set(sub["dt_inic_plantio"].dt.month.unique())
        assert obtidos <= meses, f"{cultura} plantada fora da janela: {obtidos - meses}"


def test_investimento_nao_tem_ciclo_de_lavoura():
    df = gerar_carteira(1500, semente=11)
    investimento = df[df["modalidade"] == "Investimento"]
    if not investimento.empty:
        assert investimento["dt_inic_plantio"].isna().all()


# ==========================================================================
# Personas
# ==========================================================================

def test_personas_bem_formadas():
    assert len(PERSONAS) == 16
    codigos = {p.codigo for p in PERSONAS}
    assert len(codigos) == len(PERSONAS), "há códigos de persona repetidos"
    for p in PERSONAS:
        assert p.canal_padrao in p.canais
        assert p.limite_caracteres > 100
        assert p.decisao_alvo and p.tom and p.descricao
        assert p.severidade_minima in {"informativo", "atencao", "alerta", "critico"}


def test_toda_persona_pertence_a_um_setor():
    """
    O público-alvo é organizado em setores na interface. Uma persona fora de
    qualquer setor existiria no código e não apareceria para ninguém.
    """
    from agrosentinela.personas import SETORES, setor_da_persona

    cobertas = {c for codigos in SETORES.values() for c in codigos}
    orfas = {p.codigo for p in PERSONAS} - cobertas
    assert not orfas, f"personas sem setor: {sorted(orfas)}"
    for p in PERSONAS:
        assert setor_da_persona(p.codigo) in SETORES


def test_setor_de_seguros_presente():
    """
    O setor de seguros foi pedido explicitamente como público de interesse:
    subscrição, perícia, atuária, comercial e corretagem.
    """
    from agrosentinela.personas import personas_do_setor

    seguros = personas_do_setor("Setor de seguros")
    assert len(seguros) >= 5
    codigos = {p.codigo for p in seguros}
    assert {"subscricao_seguradora", "perito_regulador",
            "atuario_precificacao"} <= codigos


def test_profissionais_mei_representados():
    """MEIs que prestam serviço ao produtor — extensionistas e assessores."""
    codigos = {p.codigo for p in PERSONAS}
    assert {"mei_extensionista", "assessor_rural"} <= codigos


@pytest.mark.parametrize(
    "programa,categoria,valor,esperado",
    [
        ("PRONAF - Agricultura Familiar", "Produtor rural - pessoa física", 40_000,
         "produtor_familiar"),
        ("PRONAMP - Médio Produtor", "Produtor rural - pessoa física", 400_000,
         "produtor_empresarial"),
        ("Recursos livres", "Cooperativa de produção agropecuária", 2_000_000,
         "cooperativa"),
        ("Recursos obrigatórios", "Produtor rural - pessoa jurídica", 1_500_000,
         "produtor_empresarial"),
        ("Recursos obrigatórios", "Produtor rural - pessoa física", 80_000,
         "produtor_familiar"),
    ],
)
def test_inferencia_de_persona(programa, categoria, valor, esperado):
    assert inferir_persona_do_mutuario(
        programa_descricao=programa, categoria_emitente=categoria, valor_credito=valor
    ) == esperado


# ==========================================================================
# Catálogo
# ==========================================================================

def test_eventos_e_culturas():
    assert len(EVENTOS) >= 7
    for e in EVENTOS:
        assert e.sinonimos_proagro and e.indicadores
    for c in CULTURAS:
        assert c.fases, f"{c.codigo} sem fases"
        assert abs(c.fases[0].inicio - 0.0) < 1e-6
        assert abs(c.fases[-1].fim - 1.0) < 1e-6
        # As fases devem cobrir o ciclo sem buraco
        for anterior, seguinte in zip(c.fases, c.fases[1:]):
            assert abs(anterior.fim - seguinte.inicio) < 1e-6, c.codigo


@pytest.mark.parametrize(
    "rotulo,esperado",
    [
        ("SECA", "seca"),
        ("Estiagem prolongada", "seca"),
        ("CHUVA EXCESSIVA", "chuva_excessiva"),
        ("GRANIZO", "granizo"),
        ("GEADA", "geada"),
        ("VENDAVAL", "vendaval"),
        ("PRAGA SEM CONTROLE", None),
    ],
)
def test_mapeamento_de_evento_do_proagro(rotulo, esperado):
    assert mapear_evento_proagro(rotulo) == esperado


@pytest.mark.parametrize(
    "produto,esperado",
    [
        ("SOJA", "SOJA"),
        ("Milho 2ª safra", "MILHO_2SAFRA"),
        ("MILHO", "MILHO"),
        ("CAFÉ ARÁBICA", "CAFE"),
        ("Laranja pera", "LARANJA"),
        ("Bovinos de corte", "BOVINOS"),
        ("Produto inexistente", "OUTRAS"),
    ],
)
def test_mapeamento_de_produto(produto, esperado):
    assert mapear_produto_para_cultura(produto) == esperado


def test_fase_por_progresso():
    soja = get_cultura("SOJA")
    assert soja.fase_em(0.0).codigo == "semeadura"
    assert soja.fase_em(0.55).codigo == "floracao"
    assert soja.fase_em(1.0).codigo == "colheita"


def test_normalizacao_de_texto():
    assert normalizar("Café  Arábica!") == "cafe arabica"
    assert normalizar(None) == ""


# ==========================================================================
# Clima
# ==========================================================================

def test_celula_de_grade_agrupa_vizinhos():
    """
    Pontos próximos dentro da mesma célula de 0,1° devem compartilhar o
    identificador — é isso que reduz o número de chamadas à API do clima.
    (Dois pontos podem, legitimamente, cair em células distintas quando
    estão nos dois lados de uma fronteira de grade.)
    """
    a = para_celula(-12.52, -55.72)
    b = para_celula(-12.48, -55.68)
    assert isinstance(a, Celula)
    assert a.id == b.id, f"esperava a mesma célula, veio {a.id} e {b.id}"
    assert para_celula(-12.52, -55.72).id != para_celula(-20.0, -50.0).id


def test_deduplicacao_reduz_chamadas_de_clima():
    from agrosentinela.weather.open_meteo import celulas_de_municipios

    municipios = [
        {"cd_ibge": 1, "lat": -12.52, "lon": -55.72},
        {"cd_ibge": 2, "lat": -12.48, "lon": -55.68},   # mesma célula do anterior
        {"cd_ibge": 3, "lat": -28.26, "lon": -52.41},
    ]
    celulas, mapa = celulas_de_municipios(municipios)
    assert len(celulas) == 2, "municípios vizinhos deveriam compartilhar a célula"
    assert len(mapa) == 3
    assert mapa["1"] == mapa["2"] != mapa["3"]


def test_provedor_sintetico_e_deterministico():
    celulas = [para_celula(-15.6, -56.1)]
    a = SinteticoProvider().series_diarias(celulas, dias_passados=10, dias_previsao=5)
    b = SinteticoProvider().series_diarias(celulas, dias_passados=10, dias_previsao=5)
    assert a == b
    assert len(a) == 15
    assert {"tmax", "tmin", "precipitacao", "et0", "rajada", "cape_max"} <= set(a[0])


@pytest.mark.parametrize(
    "cenario,coluna,teste",
    [
        ("seca", "precipitacao", lambda v: max(v) == 0),
        ("geada", "tmin", lambda v: min(v) <= 2.5),
        ("onda_calor", "tmax", lambda v: max(v) >= 36),
        ("granizo", "cape_max", lambda v: max(v) >= 2000),
        ("vendaval", "rajada", lambda v: max(v) >= 70),
        ("chuva_excessiva", "precipitacao", lambda v: sum(v) >= 150),
    ],
)
def test_cenarios_sinteticos(cenario, coluna, teste):
    celulas = [para_celula(-25.4, -49.3)]
    registros = SinteticoProvider(cenario=cenario, intensidade=1.5).series_diarias(
        celulas, dias_passados=20, dias_previsao=10
    )
    hoje = date.today().isoformat()
    futuros = [r[coluna] for r in registros if r["data"] >= hoje]
    assert teste(futuros), f"cenário {cenario} não afetou {coluna}: {futuros}"


def test_indicadores_calculados():
    hoje = date.today()
    linhas = []
    for i in range(-14, 8):
        dia = hoje + timedelta(days=i)
        linhas.append({
            "cell_id": "X", "data": dia.isoformat(),
            "tmax": 30.0, "tmin": 18.0, "tmed": 24.0,
            "precipitacao": 0.0, "et0": 5.0, "rajada": 20.0,
            "vento_medio": 12.0, "cape_max": 100.0,
            "umidade_media": 55.0, "umidade_min": 35.0,
            "prob_precipitacao": 5.0,
        })
    jan = calcular_indicadores(pd.DataFrame(linhas), data_ref=hoje, horizonte_dias=7)
    v = jan.valores
    assert v["prec_7d"] == 0.0
    assert v["dias_secos_consecutivos"] >= 20
    assert v["balanco_hidrico_14d"] == pytest.approx(-70.0, abs=1.0)
    assert v["tmin_min"] == 18.0
    assert v["dias_tmax_ge_35"] == 0


def test_proxy_de_granizo():
    assert probabilidade_granizo(400, 90, 60) == 0.0, "sem CAPE não há granizo"
    baixo = probabilidade_granizo(1000, 45, 20)
    alto = probabilidade_granizo(3200, 95, 70)
    assert 0 < baixo < alto <= 100


def test_esquema_preenche_colunas_faltantes():
    df = pd.DataFrame({"ref_bacen": ["1"], "valor_credito": [100.0]})
    out = aplicar_esquema(df, CARTEIRA_COLS)
    assert list(out.columns)[: len(CARTEIRA_COLS)] == list(CARTEIRA_COLS)
    assert out["tem_cobertura"].dtype == bool
    assert str(out["dt_emissao"].dtype).startswith("datetime")
