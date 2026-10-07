"""
Testes do modelo integrado dos dados do BCB e das fontes externas livres.

Três coisas que este arquivo protege:

1. **O grafo de integração é verdadeiro** — toda entidade é alcançável, toda
   ligação aponta para entidades que existem e as chaves declaradas são as
   que o ETL usa de fato.
2. **Nenhuma fonte externa paga entra no projeto** — a restrição é do autor e
   vale para todas: gratuita, pública, e de preferência sem cadastro.
3. **A degradação é graciosa de verdade** — sem rede, todo conector devolve
   algo utilizável e **rotulado como referência**, jamais um valor de rede
   disfarçado.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from agrosentinela import etl_catalogo as cat
from agrosentinela import fontes_externas as fe
from agrosentinela.data import modelo_integrado as mi
from agrosentinela.data.schemas import (
    CONTEXTO_COLS,
    DATASETS_OPCIONAIS,
    DATASETS_POR_NOME,
    EXPOSICAO_COLS,
    GLEBAS_COLS,
)
from agrosentinela.external import CONECTORES, obter_conector
from agrosentinela.external.base import ORIGEM_OFFLINE
from agrosentinela.external.ibge_malhas import area_aproximada_ha, centroide_de_wkt
from agrosentinela.external.nasa_power import anomalia_chuva, classificar_anomalia
from agrosentinela.external.psr_mapa import classificar_protecao
from agrosentinela.external.queimadas import distancia_km
from agrosentinela.external.zarc import avaliar_plantio, janela_texto
from agrosentinela.external.conab import valor_da_perda


# ==========================================================================
# Modelo integrado
# ==========================================================================

def test_grafo_e_conexo():
    """Uma entidade inalcançável seria dado catalogado que nunca é usado."""
    assert mi.conexo(), "há entidade isolada no grafo de integração"


def test_ligacoes_apontam_para_entidades_existentes():
    conhecidas = set(mi.ENTIDADES_POR_CHAVE)
    for l in mi.LIGACOES:
        assert l.origem in conhecidas, f"origem desconhecida: {l.origem}"
        assert l.destino in conhecidas, f"destino desconhecido: {l.destino}"
        assert l.chaves, f"ligação {l.origem}->{l.destino} sem chave declarada"


def test_caminho_do_proagro_ate_o_municipio():
    """
    A pergunta que mais importa no modelo: como um pedido de cobertura chega
    ao município? A resposta tem de passar pelo complemento — é lá que mora o
    CD_IBGE_MUNICIPIO.
    """
    caminho = mi.caminho("cop", "d_municipios")
    assert caminho, "não há caminho entre o pedido de cobertura e o município"
    entidades = {l.origem for l in caminho} | {l.destino for l in caminho}
    assert "complemento" in entidades


def test_ligacao_operacao_complemento_e_critica():
    """Sem ela não há georreferenciamento e, portanto, não há alerta dirigido."""
    ligacao = next(
        (l for l in mi.LIGACOES
         if {l.origem, l.destino} == {"operacao", "complemento"}), None
    )
    assert ligacao is not None
    assert ligacao.critica
    assert ligacao.chaves == ("REF_BACEN", "NU_ORDEM")


def test_receita_produz_todos_os_conjuntos_curados():
    produzidos = {p.saida for p in mi.RECEITA}
    esperados = set(DATASETS_POR_NOME)
    assert esperados <= produzidos | {"exposicao"}, (
        f"conjuntos sem passo de montagem: {esperados - produzidos}"
    )


def test_mermaid_valido():
    diagrama = mi.mermaid()
    assert diagrama.startswith("graph LR")
    assert "subgraph" in diagrama
    # Toda entidade tem de aparecer no desenho.
    for chave in mi.ENTIDADES_POR_CHAVE:
        assert chave in diagrama, f"{chave} não aparece no diagrama"


# ==========================================================================
# Catálogo do BCB
# ==========================================================================

def test_catalogo_cobre_quase_tudo_e_explica_o_resto():
    """
    A meta declarada é usar **todos** os arquivos publicados. As exceções
    precisam ser poucas e ter motivo escrito — aqui, privacidade.
    """
    resumo = cat.resumo()
    assert resumo["cobertura_pct"] >= 95.0
    for arquivo in cat.nao_usados():
        assert "privacidade" in arquivo.papel.lower(), (
            f"{arquivo.chave} não é usado e não explica por quê"
        )


def test_todo_arquivo_usado_declara_seu_papel():
    sem_papel = [a.chave for a in cat.usados() if not a.papel.strip()]
    assert not sem_papel, f"arquivos usados sem papel declarado: {sem_papel}"


def test_urls_do_catalogo_sao_do_banco_central():
    for arquivo in cat.CATALOGO_BCB:
        assert arquivo.url.startswith("https://www.bcb.gov.br/"), arquivo.chave


# ==========================================================================
# Fontes externas: gratuitas, públicas e livres
# ==========================================================================

def test_toda_fonte_externa_e_gratuita():
    pagas = [f.chave for f in fe.FONTES if not f.gratuita]
    assert not pagas, f"fontes não gratuitas no catálogo: {pagas}"


def test_nenhuma_fonte_exige_cadastro():
    """
    Restrição de projeto: a solução tem de rodar no Streamlit Cloud gratuito
    sem que ninguém precise criar conta em lugar nenhum.
    """
    com_cadastro = [f.chave for f in fe.FONTES if f.exige_chave]
    assert not com_cadastro, f"fontes que exigem cadastro: {com_cadastro}"


def test_toda_fonte_declara_licenca_e_papel():
    for f in fe.FONTES:
        assert f.licenca.strip(), f"{f.chave} sem licença declarada"
        assert f.papel.strip(), f"{f.chave} sem papel declarado"
        assert f.chave_juncao.strip(), f"{f.chave} sem chave de junção"
        assert f.categoria in fe.CATEGORIAS


def test_setor_de_seguros_tem_fonte_externa():
    """O público de seguros foi pedido explicitamente; precisa de dado próprio."""
    seguro = fe.por_categoria(fe.CAT_SEGURO)
    assert len(seguro) >= 2
    assert any("PSR" in f.nome or "Atlas" in f.nome for f in seguro)


def test_todo_conector_tem_fonte_catalogada():
    for chave in CONECTORES:
        assert chave in fe.FONTES_POR_CHAVE, (
            f"conector {chave} sem registro em fontes_externas"
        )


def test_apelidos_resolvem_para_conectores_reais():
    from agrosentinela.external.registry import APELIDOS

    for apelido, alvo in APELIDOS.items():
        assert alvo in CONECTORES, f"apelido {apelido} aponta para {alvo}, inexistente"
        assert obter_conector(apelido, offline=True) is not None


def test_conector_desconhecido_orienta_em_vez_de_explodir_em_silencio():
    try:
        obter_conector("fonte_que_nao_existe")
    except KeyError as exc:
        assert "Disponíveis" in str(exc), (
            "o erro deveria listar os conectores disponíveis"
        )
    else:
        raise AssertionError("conector inexistente deveria levantar KeyError")


# ==========================================================================
# Degradação graciosa
# ==========================================================================

@pytest.mark.parametrize("chave", sorted(set(CONECTORES)))
def test_conector_offline_nao_quebra_e_se_rotula(chave):
    """
    Sem rede, nenhum conector pode levantar exceção nem mentir sobre a
    origem do dado. Este é o teste que garante que o aplicativo abre em
    qualquer máquina, inclusive na do avaliador.
    """
    conector = obter_conector(chave, offline=True)
    resultado = conector.obter(**conector._params_sonda())
    assert isinstance(resultado.dados, pd.DataFrame)
    assert resultado.origem == ORIGEM_OFFLINE
    assert resultado.selo.startswith("⚪")
    assert not resultado.ao_vivo
    assert resultado.mensagem, "resultado offline sem explicação ao usuário"


def test_conectores_de_observacao_nao_inventam_zero():
    """
    Fogo e chuva medida em solo: sem rede, a resposta certa é "não sei", não
    "zero". Um zero falso esconderia justamente o evento que importa.
    """
    for chave in ("queimadas_inpe", "cemaden"):
        resultado = obter_conector(chave, offline=True).obter(uf="MT")
        assert resultado.vazio, (
            f"{chave} devolveu dado inventado no modo offline"
        )


# ==========================================================================
# Zarc — janela de plantio
# ==========================================================================

def test_zarc_dentro_da_janela_atenua():
    r = avaliar_plantio("SOJA", "Centro-Oeste", date(2026, 11, 5))
    assert r["avaliavel"] and r["dentro_janela"]
    assert r["fator"] < 1.0
    assert "Zarc" in r["explicacao"]


def test_zarc_fora_da_janela_agrava_proporcionalmente():
    perto = avaliar_plantio("SOJA", "Centro-Oeste", date(2027, 1, 5))
    longe = avaliar_plantio("SOJA", "Centro-Oeste", date(2027, 3, 1))
    assert perto["fator"] > 1.0
    assert longe["fator"] >= perto["fator"]
    assert longe["decendios_fora"] > perto["decendios_fora"]


def test_zarc_mede_contra_a_safra_mais_proxima():
    """
    Um plantio em 20/01 contra a janela out–dez está 3 decêndios atrasado em
    relação à safra corrente, não 25 decêndios adiantado para a próxima.
    """
    r = avaliar_plantio("SOJA", "Centro-Oeste", date(2027, 1, 20))
    assert r["decendios_fora"] <= 6


def test_zarc_silencioso_para_perene_e_pecuaria():
    for cultura in ("CAFE", "CANA", "PASTAGEM", "BOVINOS"):
        r = avaliar_plantio(cultura, "Sudeste", date(2026, 10, 1))
        assert not r["avaliavel"]
        assert r["fator"] == 1.0
        assert r["explicacao"] == ""


def test_janela_texto_legivel():
    assert janela_texto("SOJA", "Centro-Oeste") == "01/10 a 20/12"
    assert "sem janela" in janela_texto("CAFE", "Sudeste")


# ==========================================================================
# Geometria (WKT)
# ==========================================================================

def test_centroide_de_poligono_quadrado():
    wkt = "POLYGON((-55.72 -12.55,-55.71 -12.55,-55.71 -12.56,-55.72 -12.56,-55.72 -12.55))"
    centro = centroide_de_wkt(wkt)
    assert centro is not None
    lat, lon = centro
    assert -12.57 < lat < -12.54
    assert -55.73 < lon < -55.70


def test_centroide_rejeita_coordenada_fora_do_brasil():
    assert centroide_de_wkt("POLYGON((2.3 48.8,2.4 48.8,2.4 48.9,2.3 48.9,2.3 48.8))") is None
    assert centroide_de_wkt("") is None
    assert centroide_de_wkt("NAO É WKT") is None


def test_area_de_poligono_conhecido():
    """Um grau de longitude a -12° vale ~108,8 km; 0,01° x 0,01° ≈ 108 ha."""
    wkt = "POLYGON((-55.72 -12.55,-55.71 -12.55,-55.71 -12.56,-55.72 -12.56,-55.72 -12.55))"
    area = area_aproximada_ha(wkt)
    assert 90 < area < 130, f"área calculada implausível: {area} ha"


def test_distancia_conhecida():
    """Sorriso (MT) a Sinop (MT): cerca de 80 km em linha reta."""
    d = distancia_km(-12.55, -55.72, -11.86, -55.50)
    assert 70 < d < 95


# ==========================================================================
# Anomalia, proteção e perda
# ==========================================================================

def test_anomalia_distingue_seca_de_falta_de_informacao():
    """
    Zero milímetro previsto **é** informação — e é a mais grave. Confundi-la
    com ausência de dado apagaria o alerta de seca. Defeito real, corrigido.
    """
    assert classificar_anomalia(anomalia_chuva(0.0, 30.0)) == "muito abaixo da média"
    assert classificar_anomalia(anomalia_chuva(None, 30.0)) == "sem referência"
    assert classificar_anomalia(anomalia_chuva(50.0, None)) == "sem referência"
    assert classificar_anomalia(anomalia_chuva(95.0, 26.0)) == "muito acima da média"
    assert classificar_anomalia(anomalia_chuva(30.0, 30.0)) == "dentro da média"


def test_protecao_soma_publica_e_privada():
    """
    "Sem Proagro" não é sinônimo de "desprotegido": o município pode estar
    coberto por seguro privado subvencionado. Confundir os dois levaria a
    solução a recomendar contratação onde ela já existe.
    """
    deserto = classificar_protecao(0.02, 0.01)
    madura = classificar_protecao(0.45, 0.30)
    assert deserto["nivel"] == "baixa"
    assert madura["nivel"] == "alta"
    assert madura["cobertura_total"] <= 1.0


def test_valor_da_perda_declara_a_base_do_preco():
    r = valor_da_perda("soja", area_ha=100, rendimento_kg_ha=3400, perda_pct=0.2)
    assert r["perda_kg"] == pytest.approx(68000, abs=1)
    assert r["unidade"] == "saca de 60 kg"
    assert r["perda_reais"] > 0
    assert r["base_preco"] in {"consultado", "referência", "indisponível"}


def test_perda_nao_passa_de_cem_por_cento():
    total = valor_da_perda("soja", 100, 3400, 1.0)
    exagerado = valor_da_perda("soja", 100, 3400, 3.0)
    assert exagerado["perda_kg"] == total["perda_kg"]


# ==========================================================================
# Esquemas novos
# ==========================================================================

def test_conjuntos_opcionais_registrados():
    for nome in DATASETS_OPCIONAIS:
        assert nome in DATASETS_POR_NOME, f"{nome} não registrado em DATASETS"


def test_glebas_tem_conferencia_de_area():
    """A divergência entre área declarada e área desenhada é um indicador de
    qualidade, e por isso precisa existir no esquema."""
    assert "area_gleba_ha" in GLEBAS_COLS
    assert "area_wkt_ha" in GLEBAS_COLS
    assert "divergencia_area_pct" in GLEBAS_COLS


def test_exposicao_separa_devedor_de_vencido():
    assert "saldo_devedor" in EXPOSICAO_COLS
    assert "saldo_vencido" in EXPOSICAO_COLS
    assert "renegociada" in EXPOSICAO_COLS


def test_contexto_externo_guarda_a_procedencia():
    """Sem esta coluna, não há como saber se um número veio da rede ou da
    tabela embutida — e o painel deixaria de ser confiável."""
    assert "origem_contexto" in CONTEXTO_COLS
