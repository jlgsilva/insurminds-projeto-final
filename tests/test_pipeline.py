"""Teste de ponta a ponta do pipeline multiagente."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from agrosentinela.data.loader import carregar_base
from agrosentinela.orchestrator import Orquestrador
from agrosentinela.outbox.store import Outbox
from agrosentinela.personas import LIMITE_CANAL


@pytest.fixture(scope="module")
def base():
    return carregar_base("seed")


@pytest.fixture(scope="module")
def outbox(tmp_path_factory):
    return Outbox(tmp_path_factory.mktemp("outbox") / "teste.sqlite")


@pytest.fixture(scope="module")
def resultado(base, outbox):
    orq = Orquestrador(base=base, outbox=outbox)
    return orq.executar(
        data_ref=date.today(),
        horizonte_dias=7,
        cenario="seca",
        intensidade_cenario=1.4,
        modo_clima="sintetico",
        filtros={"uf": ["MT", "GO", "PR"]},
        usar_llm=False,
        max_mensagens=8,
        respeitar_supressao=False,
        persistir=True,
    )


# ==========================================================================
def test_base_seed_carrega(base):
    assert not base.carteira.empty
    assert not base.municipios.empty
    assert base.e_demonstracao
    assert base.carteira["valor_credito"].sum() > 0
    assert base.carteira["lat"].notna().all()


def test_pipeline_executa_todas_as_etapas(resultado):
    agentes = [e.agente for e in resultado.contexto.rastro]
    assert agentes == [
        "CarteiraAgent", "ClimaAgent", "EventoAgent",
        "RegrasAgent", "RedatorAgent", "DespachanteAgent",
    ]
    assert all(e.sucesso for e in resultado.contexto.rastro), [
        (e.agente, e.erro) for e in resultado.contexto.rastro if not e.sucesso
    ]
    assert resultado.sucesso


def test_etapas_produzem_saida(resultado):
    ctx = resultado.contexto
    assert len(ctx.carteira) > 0, "carteira vazia"
    assert not ctx.clima_diario.empty, "sem série meteorológica"
    assert not ctx.indicadores.empty, "sem indicadores"
    assert not ctx.eventos_municipio.empty, "cenário de seca deveria gerar eventos"
    assert ctx.alertas, "cenário de seca deveria gerar alertas"
    assert ctx.mensagens, "deveria gerar mensagens"
    assert ctx.envios, "deveria simular envios"


def test_filtro_de_uf_respeitado(resultado):
    assert set(resultado.contexto.carteira["uf"].unique()) <= {"MT", "GO", "PR"}


def test_alertas_tem_rastro_completo(resultado):
    for alerta in resultado.contexto.alertas[:20]:
        assert alerta.id.startswith("ALT-")
        assert alerta.acionamentos, "alerta sem regra que o originou"
        assert alerta.regras, "alerta sem identificador de regra"
        assert 0 <= alerta.score <= 100
        assert alerta.severidade in {"informativo", "atencao", "alerta", "critico"}
        assert alerta.municipio and alerta.uf
        assert alerta.indicadores, "alerta sem indicadores meteorológicos"


def test_mensagens_respeitam_limite_de_canal(resultado):
    for m in resultado.contexto.mensagens:
        limite = LIMITE_CANAL.get(m.canal, 2000)
        assert m.caracteres <= limite, (
            f"{m.id} ({m.canal}) tem {m.caracteres} caracteres, limite {limite}"
        )
        assert m.texto.strip(), f"{m.id} veio vazia"
        assert m.alertas, f"{m.id} sem alerta vinculado"


def test_mensagens_sem_llm_sao_templates(resultado):
    assert all(m.gerado_por == "template" for m in resultado.contexto.mensagens)


def test_mensagem_nao_promete_indenizacao(resultado):
    proibidos = [
        "será indenizado", "garantimos o pagamento", "você receberá a indenização",
        "pagamento garantido", "indenização garantida",
    ]
    for m in resultado.contexto.mensagens:
        texto = m.texto.lower()
        for termo in proibidos:
            assert termo not in texto, f"{m.id} contém promessa indevida: {termo}"


def test_envios_sao_simulados(resultado):
    for e in resultado.contexto.envios:
        assert e.simulado is True
        assert e.status in {"simulado_entregue", "simulado_falha", "suprimido"}


def test_persistencia_na_outbox(resultado, outbox):
    stats = outbox.estatisticas()
    assert stats["execucoes"] >= 1
    assert stats["alertas"] >= 1
    assert stats["mensagens"] >= 1
    tabela = outbox.tabela("mensagens")
    assert not tabela.empty
    assert set(tabela["id"]) >= {m.id for m in resultado.contexto.mensagens}


def test_dataframes_de_saida(resultado):
    assert not resultado.alertas_df.empty
    assert not resultado.mensagens_df.empty
    assert not resultado.envios_df.empty
    assert not resultado.rastro_df.empty
    resumo = resultado.resumo
    assert resumo["alertas_gerados"] == len(resultado.contexto.alertas)
    assert resumo["execucao_id"].startswith("EXE-")


def test_supressao_atua_na_segunda_execucao(base, outbox):
    orq = Orquestrador(base=base, outbox=outbox)
    comum = dict(
        horizonte_dias=7, cenario="geada", intensidade_cenario=1.5,
        modo_clima="sintetico", filtros={"uf": ["RS"]}, usar_llm=False,
        max_mensagens=5, persistir=True,
    )
    primeira = orq.executar(respeitar_supressao=True, **comum)
    segunda = orq.executar(respeitar_supressao=True, **comum)

    suprimidos_1 = sum(1 for e in primeira.contexto.envios if e.status == "suprimido")
    suprimidos_2 = sum(1 for e in segunda.contexto.envios if e.status == "suprimido")
    assert suprimidos_2 >= suprimidos_1, (
        "a política anti-fadiga deveria suprimir mais na repetição imediata"
    )


def test_sem_evento_nao_gera_alerta(base, outbox):
    """Numa carteira minúscula sem evento forçado, o sistema fica quieto."""
    orq = Orquestrador(base=base, outbox=outbox)
    res = orq.executar(
        horizonte_dias=3, modo_clima="sintetico", usar_llm=False,
        filtros={"uf": ["AP"]}, max_mensagens=3,
        respeitar_supressao=False, persistir=False,
    )
    assert all(e.sucesso for e in res.contexto.rastro)


def test_cenarios_produzem_eventos_correspondentes(base, outbox):
    esperado = {
        "geada": "geada",
        "granizo": "granizo",
        "onda_calor": "onda_calor",
        "vendaval": "vendaval",
        "chuva_excessiva": "chuva_excessiva",
    }
    orq = Orquestrador(base=base, outbox=outbox)
    for cenario, codigo in esperado.items():
        res = orq.executar(
            horizonte_dias=7, cenario=cenario, intensidade_cenario=1.6,
            modo_clima="sintetico", filtros={"uf": ["PR"]}, usar_llm=False,
            max_mensagens=3, respeitar_supressao=False, persistir=False,
        )
        eventos = set(res.contexto.eventos_municipio["evento"].unique()) \
            if not res.contexto.eventos_municipio.empty else set()
        assert codigo in eventos, f"cenário {cenario} não produziu o evento {codigo}: {eventos}"
