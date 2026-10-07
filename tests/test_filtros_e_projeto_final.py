"""
Testes dos filtros da interface e da prévia do Projeto Final (D&O).

O que estes testes protegem:

* **Nenhum filtro esconde dado em silêncio.** Seleção vazia mostra tudo, e um
  valor nulo numa faixa numérica é mantido — "não sei o valor" não é o mesmo
  que "está fora do intervalo", e tratar os dois igual é como se perde um
  alerta sem ninguém perceber.
* **O comparador de apólices é aritmética conferível.** Escore, lacunas e
  diferenças têm de ser reproduzíveis à mão a partir do peso e do nível de
  cada cláusula; nada aqui pode depender de modelo de linguagem.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from agrosentinela import filtros as F
from agrosentinela.projeto_final import clausulas as cl
from agrosentinela.projeto_final import comparador as cp


# ==========================================================================
# Catálogo de filtros
# ==========================================================================

def test_todo_filtro_declara_o_porque():
    """
    Filtro sem justificativa escrita é filtro que ninguém consegue discutir —
    e, na prática, é filtro que acaba existindo só porque a coluna existia.
    """
    for f in F.FILTROS:
        assert f.porque.strip(), f"filtro {f.chave} sem justificativa"
        assert f.rotulo.strip()
        assert f.tipo in (F.TIPO_MULTI, F.TIPO_FAIXA, F.TIPO_BOOL, F.TIPO_ESCOLHA)
        assert f.grupo in F.GRUPOS


def test_chaves_de_filtro_sao_unicas():
    chaves = [f.chave for f in F.FILTROS]
    assert len(chaves) == len(set(chaves))


def test_os_quatro_cortes_decisivos_existem():
    """
    Cobertura, fase fenológica, janela de ação e aderência ao Zarc são os
    cortes que separam um painel útil de um painel bonito.
    """
    essenciais = {f.chave for f in F.essenciais()}
    assert {"tem_cobertura", "fase", "janela_acao_h",
            "dentro_janela_zarc"} <= essenciais


def test_somente_filtros_com_variacao_sao_oferecidos():
    """Filtro de uma opção só ocupa espaço e não filtra nada."""
    df = pd.DataFrame({
        "uf": ["MT", "MT", "MT"],          # constante — não deve aparecer
        "severidade": ["critico", "alerta", "atencao"],
        "score": [10.0, 50.0, 90.0],
    })
    chaves = {f.chave for f in F.aplicaveis(df)}
    assert "severidade" in chaves
    assert "score" in chaves
    assert "uf" not in chaves


# ==========================================================================
# Aplicação
# ==========================================================================

@pytest.fixture
def alertas():
    return pd.DataFrame({
        "severidade": ["critico", "alerta", "atencao", "informativo"],
        "uf": ["MT", "PR", "MT", "BA"],
        "tem_cobertura": [True, False, False, True],
        "score": [95.0, 70.0, 45.0, 20.0],
        "area_ha": [100.0, 250.0, None, 80.0],
        "dentro_janela_zarc": [True, False, None, True],
    })


def test_selecao_vazia_nao_filtra_nada(alertas):
    assert len(F.aplicar(alertas, {})) == len(alertas)
    assert len(F.aplicar(alertas, {"severidade": []})) == len(alertas)
    assert len(F.aplicar(alertas, {"tem_cobertura": None})) == len(alertas)


def test_multi_e_bool_combinam(alertas):
    sel = {"severidade": ["critico", "alerta"], "tem_cobertura": False}
    saida = F.aplicar(alertas, sel)
    assert len(saida) == 1
    assert saida.iloc[0]["uf"] == "PR"


def test_faixa_preserva_o_desconhecido(alertas):
    """
    A linha com ``area_ha`` nula continua visível: omitir silenciosamente o
    desconhecido é exatamente como se perde um alerta.
    """
    saida = F.aplicar(alertas, {"area_ha": (200.0, 300.0)})
    assert len(saida) == 2                     # a de 250 ha e a de área nula
    assert saida["area_ha"].isna().sum() == 1


def test_faixa_e_inclusiva_nas_pontas(alertas):
    saida = F.aplicar(alertas, {"score": (45.0, 95.0)})
    assert set(saida["score"]) == {45.0, 70.0, 95.0}


def test_bool_com_nulo_nao_e_falso(alertas):
    """``None`` em coluna booleana é 'não avaliado', não 'não'."""
    saida = F.aplicar(alertas, {"dentro_janela_zarc": False})
    assert len(saida) == 1
    assert saida.iloc[0]["uf"] == "PR"


def test_coluna_inexistente_e_ignorada(alertas):
    assert len(F.aplicar(alertas, {"instituicao": ["Banco X"]})) == len(alertas)


def test_resumo_descreve_os_filtros_ativos(alertas):
    texto = F.resumo({"severidade": ["critico"], "tem_cobertura": False,
                      "score": (50.0, 100.0)})
    assert len(texto) == 3
    assert any("Crítico" in t for t in texto)
    assert any("não" in t for t in texto)
    assert F.ativos({}) == 0


# ==========================================================================
# Projeto Final — taxonomia
# ==========================================================================

def test_toda_clausula_declara_peso_e_pergunta():
    for c in cl.CLAUSULAS:
        assert 1 <= c.peso <= 5, f"{c.codigo} com peso fora da escala"
        assert c.porque_importa.strip(), f"{c.codigo} sem justificativa"
        assert c.pergunta.strip(), f"{c.codigo} sem pergunta de verificação"
        assert c.grupo in cl.GRUPOS_CLAUSULA


def test_codigos_de_clausula_unicos():
    codigos = [c.codigo for c in cl.CLAUSULAS]
    assert len(codigos) == len(set(codigos))


def test_clausulas_que_decidem_sinistro_estao_marcadas():
    """
    Custos de defesa, adiantamento, retroatividade e a exclusão de dolo são
    as que mais mudam o resultado prático de uma apólice de D&O.
    """
    criticas = {c.codigo for c in cl.criticas()}
    assert {"DEF-01", "DEF-02", "TMP-01", "EXC-01", "LIM-01"} <= criticas


# ==========================================================================
# Projeto Final — comparação
# ==========================================================================

@pytest.fixture
def comparacao():
    return cp.comparar(cp.exemplos())


def test_escore_e_reproduzivel_a_mao():
    """
    O escore tem de ser refazível com peso × nível — se não for, ninguém
    consegue conferir uma recomendação de cobertura.
    """
    apolice = cp.Apolice(
        identificador="Teste", seguradora="X",
        avaliacoes={c.codigo: "ampla" for c in cl.CLAUSULAS},
    )
    assert apolice.escore() == 100.0
    vazia = cp.Apolice(identificador="Vazia", seguradora="X")
    assert vazia.escore() == 0.0


def test_clausula_nao_informada_conta_como_ausente():
    """Silêncio contratual não é neutro — é resolvido contra o segurado."""
    parcial = cp.Apolice(identificador="P", seguradora="X",
                         avaliacoes={"DEF-01": "ampla"})
    assert parcial.nivel("DEF-02") == "ausente"
    assert parcial.pontos(cl.CLAUSULAS_POR_CODIGO["DEF-02"]) == 0.0


def test_exemplo_demonstra_leitura_divergente(comparacao):
    """
    O conjunto de exemplo foi desenhado justamente para o caso em que um
    ranking simples levaria à decisão errada. Se isso deixar de valer, a
    página perde o argumento — por isso é teste, e não comentário.
    """
    assert comparacao.divergencia_de_leitura
    assert comparacao.vencedora_geral.identificador != \
        comparacao.vencedora_criticas.identificador


def test_lacunas_apontam_a_melhor_alternativa(comparacao):
    assert comparacao.lacunas
    for lacuna in comparacao.lacunas:
        assert lacuna.gravidade in {"critica", "alta", "media"}
        assert lacuna.pontos_perdidos >= 0
        linha = lacuna.to_row()
        assert linha["por que importa"]


def test_diferencas_ignoram_clausulas_iguais():
    """
    Mostrar as trinta linhas iguais junto das seis diferentes é a maneira
    mais eficiente de esconder as seis.
    """
    iguais = [
        cp.Apolice(identificador=nome, seguradora="X",
                   avaliacoes={c.codigo: "padrao" for c in cl.CLAUSULAS})
        for nome in ("A", "B")
    ]
    assert cp.diferencas_relevantes(cp.comparar(iguais)) == []


def test_bloco_de_fatos_traz_o_aviso(comparacao):
    """
    Mesmo contrato do Desafio 5: o LLM redige a partir daqui e não pode
    acrescentar número nenhum — e o aviso de que não é parecer jurídico
    viaja junto com os fatos.
    """
    fatos = comparacao.bloco_de_fatos()
    assert "aviso" in fatos
    assert "parecer" in fatos["aviso"].lower()
    assert fatos["apolices"]
    assert set(fatos["escores_por_grupo"]) == {
        a.identificador for a in comparacao.apolices
    }


def test_comparar_uma_apolice_nao_quebra():
    unica = cp.comparar(cp.exemplos()[:1])
    assert unica.lacunas == []
    assert unica.vencedora_geral is not None
    assert not unica.divergencia_de_leitura


def test_matriz_tem_uma_linha_por_clausula(comparacao):
    matriz = cp.matriz_comparativa(comparacao.apolices)
    assert len(matriz) == len(cl.CLAUSULAS)
    for a in comparacao.apolices:
        assert a.identificador in matriz[0]


def test_apolices_de_exemplo_sao_ficticias():
    """Nenhum dado de seguradora real entra no repositório."""
    for a in cp.exemplos():
        assert "Fictícia" in a.seguradora
        assert a.fonte == "exemplo didático"
