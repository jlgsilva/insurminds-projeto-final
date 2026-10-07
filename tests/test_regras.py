"""Testes do motor de regras e do avaliador seguro de expressões."""

from __future__ import annotations

import pytest

from agrosentinela.rules.engine import (
    AvaliadorSeguro,
    ExpressaoInvalida,
    MotorRegras,
    avaliar_expressao,
)


# ==========================================================================
# Avaliador seguro
# ==========================================================================

def test_expressoes_basicas():
    ctx = {"a": 10, "b": 3, "texto": "SOJA", "flag": True}
    assert avaliar_expressao("a > b", ctx)
    assert avaliar_expressao("a >= 10 and b <= 3", ctx)
    assert avaliar_expressao("texto in ['SOJA', 'MILHO']", ctx)
    assert avaliar_expressao("flag", ctx)
    assert avaliar_expressao("not flag", ctx) is False
    assert avaliar_expressao("a - b == 7", ctx)
    assert avaliar_expressao("max(a, b) == 10", ctx)


def test_indicador_ausente_nao_dispara():
    """Indicador que não existe no contexto não pode fazer a regra disparar."""
    assert avaliar_expressao("inexistente >= 10", {}) is False
    assert avaliar_expressao("inexistente >= 10 or 1 == 1", {}) is True


def test_bloqueia_construcoes_perigosas():
    for expressao in (
        "__import__('os').system('ls')",
        "open('/etc/passwd').read()",
        "[x for x in range(10)]",
        "lambda: 1",
        "a.__class__",
    ):
        with pytest.raises(ExpressaoInvalida):
            AvaliadorSeguro({"a": 1}).avaliar(expressao)


def test_registra_nomes_usados():
    av = AvaliadorSeguro({"prec_7d": 150, "tmin_min": 2})
    av.avaliar("prec_7d >= 120 and tmin_min <= 5")
    assert av.nomes_usados == {"prec_7d", "tmin_min"}


# ==========================================================================
# Motor
# ==========================================================================

@pytest.fixture(scope="module")
def motor() -> MotorRegras:
    return MotorRegras()


def test_carrega_regras(motor):
    assert len(motor.regras) >= 10
    ids = {r.id for r in motor.regras}
    assert len(ids) == len(motor.regras), "IDs de regra devem ser únicos"
    for r in motor.regras:
        assert r.quando, f"Regra {r.id} sem condição"
        assert r.acao, f"Regra {r.id} sem ação recomendada"
        assert r.personas, f"Regra {r.id} sem persona destinatária"


def test_seca_dispara_e_escala(motor):
    base = {
        "dias_secos_consecutivos": 12,
        "balanco_hidrico_14d": -40,
        "fase": "floracao",
        "sensibilidade_fase": 2.0,
        "irrigada": False,
        "valor_credito": 300_000,
        "tem_cobertura": True,
    }
    leve = motor.avaliar(base)
    assert any(a.regra_id == "R-SEC-01" for a in leve)
    sev_leve = next(a for a in leve if a.regra_id == "R-SEC-01").severidade

    grave = motor.avaliar({**base, "dias_secos_consecutivos": 28, "balanco_hidrico_14d": -95})
    sev_grave = next(a for a in grave if a.regra_id == "R-SEC-01").severidade
    assert sev_grave == "critico"
    assert sev_grave != sev_leve


def test_geada_critica(motor):
    ctx = {"tmin_min": -1.0, "dias_tmin_le_3": 3, "fase": "floracao",
           "sensibilidade_fase": 2.2, "valor_credito": 500_000, "tem_cobertura": True,
           "cultura": "TRIGO"}
    acionamentos = motor.avaliar(ctx)
    geada = [a for a in acionamentos if a.regra_id.startswith("R-GEA")]
    assert geada, "Geada com mínima negativa deve disparar"
    assert geada[0].severidade == "critico"


def test_sem_cobertura_aciona_regra_generica(motor):
    ctx = {"tmin_min": 0.0, "dias_tmin_le_3": 2, "fase": "floracao",
           "sensibilidade_fase": 2.0, "tem_cobertura": False,
           "valor_credito": 400_000}
    ids = {a.regra_id for a in motor.avaliar(ctx)}
    assert "R-COB-01" in ids


def test_nada_dispara_em_tempo_bom(motor):
    ctx = {
        "dias_secos_consecutivos": 2, "balanco_hidrico_14d": 20, "prec_7d": 25,
        "prec_max_24h": 12, "tmin_min": 18, "tmax_max": 29, "rajada_max": 22,
        "prob_granizo": 0, "dias_tmax_ge_35": 0, "dias_com_chuva_7d": 2,
        "umidade_media": 62, "fase": "vegetativo", "sensibilidade_fase": 1.0,
        "tem_cobertura": True, "valor_credito": 120_000,
        "dias_para_vencimento": 300, "dias_para_colheita": 90,
        "exposicao_municipio": 1_000_000, "freq_evento_municipio": 0.05,
        "irrigada": False,
    }
    assert motor.avaliar(ctx) == []


def test_score_no_intervalo_e_crescente(motor):
    baixo = motor.avaliar({
        "dias_secos_consecutivos": 11, "balanco_hidrico_14d": -31,
        "fase": "vegetativo", "sensibilidade_fase": 1.0,
        "valor_credito": 20_000, "tem_cobertura": True,
        "freq_evento_municipio": 0.0, "irrigada": True,
    })
    alto = motor.avaliar({
        "dias_secos_consecutivos": 30, "balanco_hidrico_14d": -110,
        "fase": "floracao", "sensibilidade_fase": 2.2,
        "valor_credito": 4_000_000, "tem_cobertura": False,
        "freq_evento_municipio": 0.6, "irrigada": False,
    })
    assert baixo and alto
    s_baixo = max(a.score for a in baixo)
    s_alto = max(a.score for a in alto)
    assert 0 <= s_baixo <= 100 and 0 <= s_alto <= 100
    assert s_alto > s_baixo


def test_acionamento_tem_rastro(motor):
    acionamentos = motor.avaliar({
        "prec_7d": 200, "prec_max_24h": 60, "fase": "colheita",
        "sensibilidade_fase": 2.0, "valor_credito": 250_000, "tem_cobertura": True,
    })
    assert acionamentos
    a = acionamentos[0]
    assert a.regra_id and a.explicacao
    assert a.indicadores_usados, "O acionamento deve registrar os indicadores que o dispararam"
    assert "R-" in a.explicacao


def test_supressao():
    from datetime import datetime, timedelta

    motor = MotorRegras()
    agora = datetime(2026, 9, 11, 10, 0)
    chave = "OP-123|whatsapp"

    suprimir, _ = motor.deve_suprimir(chave=chave, severidade="alerta", historico={}, agora=agora)
    assert suprimir is False

    recente = {chave: agora - timedelta(hours=2)}
    suprimir, motivo = motor.deve_suprimir(
        chave=chave, severidade="alerta", historico=recente, agora=agora
    )
    assert suprimir and "última" in motivo.lower() or suprimir

    antigo = {chave: agora - timedelta(hours=100)}
    suprimir, _ = motor.deve_suprimir(
        chave=chave, severidade="alerta", historico=antigo, agora=agora
    )
    assert suprimir is False

    suprimir, motivo = motor.deve_suprimir(
        chave=chave, severidade="informativo", historico={}, agora=agora
    )
    assert suprimir, "Severidade abaixo do mínimo global deve ser suprimida"

    suprimir, motivo = motor.deve_suprimir(
        chave=chave, severidade="alerta", historico={}, agora=agora, enviados_hoje=9
    )
    assert suprimir and "diário" in motivo.lower()


def test_resumo_para_interface(motor):
    resumo = motor.resumo()
    assert len(resumo) == len(motor.regras)
    assert {"id", "nome", "condição", "personas"} <= set(resumo[0])
