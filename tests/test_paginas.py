"""
Executa **todas as páginas do aplicativo** de cima a baixo, com dados reais.

Este é o teste que faltava. As páginas do Streamlit só eram verificadas
abrindo o navegador e clicando aba por aba; um erro em uma delas — como a
junção do pandas que apagava as colunas `lat`/`lon` e derrubava a página de
dados externos com `KeyError` — só aparecia na máquina de quem estava
avaliando, no pior momento possível.

Aqui cada página é executada com dublês de `streamlit` e `plotly`
(`conftest_stubs.py`). Nada de aparência é verificado: o que se verifica é
que o código **roda até o fim** sobre os dados que realmente existem.

O dublê do Plotly é deliberadamente severo: ele levanta `KeyError` quando um
gráfico referencia uma coluna inexistente, exatamente como a biblioteca real
faria ao desenhar.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tests"))

from conftest_stubs import _ParouAPagina, instalar_dubles  # noqa: E402

instalar_dubles()

sys.path.insert(0, str(RAIZ / "src"))


def paginas() -> list[Path]:
    arquivos = sorted((RAIZ / "pages").glob("*.py"))
    return [RAIZ / "app.py", *arquivos]


def _executar(caminho: Path) -> None:
    """Executa o arquivo como script, isolando o espaço de nomes."""
    codigo = compile(caminho.read_text(encoding="utf-8"), str(caminho), "exec")
    espaco = {"__name__": "__main__", "__file__": str(caminho)}
    try:
        exec(codigo, espaco)  # noqa: S102 — é exatamente o que o Streamlit faz
    except _ParouAPagina:
        pass                  # `st.stop()` é fluxo normal, não falha


def test_encontra_todas_as_paginas():
    nomes = [p.name for p in paginas()]
    assert "app.py" in nomes
    assert len(nomes) >= 11, f"páginas encontradas: {nomes}"


def test_app_executa_sem_erro():
    _executar(RAIZ / "app.py")


def test_pagina_painel_executivo():
    _executar(RAIZ / "pages" / "1_📊_Painel_Executivo.py")


def test_pagina_mapa_de_risco():
    _executar(RAIZ / "pages" / "2_🗺️_Mapa_de_Risco.py")


def test_pagina_radar_climatico():
    _executar(RAIZ / "pages" / "3_🌦️_Radar_Climático.py")


def test_pagina_motor_de_regras():
    _executar(RAIZ / "pages" / "4_⚙️_Motor_de_Regras.py")


def test_pagina_central_de_comunicacao():
    _executar(RAIZ / "pages" / "5_💬_Central_de_Comunicação.py")


def test_pagina_copiloto():
    _executar(RAIZ / "pages" / "6_🤖_Copiloto_IA.py")


def test_pagina_microdados_sicor():
    _executar(RAIZ / "pages" / "7_🗃️_Microdados_SICOR.py")


def test_pagina_proagro():
    _executar(RAIZ / "pages" / "8_🛡️_Proagro_e_Sinistralidade.py")


def test_pagina_documentacao():
    _executar(RAIZ / "pages" / "9_📚_Documentação.py")


def test_pagina_dados_externos():
    """
    A página que quebrou em produção. O defeito: juntar `contexto_externo`
    com `municipios` produzia `lat_x`/`lat_y` e a coluna `lat` sumia.
    """
    _executar(RAIZ / "pages" / "10_🌐_Dados_Externos.py")


def test_pagina_ingestao_apolices():
    _executar(RAIZ / "pages" / "11_📄_Ingestão_de_Apólices.py")


def test_pagina_comparador_apolices():
    _executar(RAIZ / "pages" / "12_⚖️_Comparador_de_Apólices.py")


def test_pagina_consulta_apolices():
    _executar(RAIZ / "pages" / "13_💬_Consulta_às_Apólices.py")


# ==========================================================================
# Com uma execução carregada
#
# Metade das páginas para em `st.stop()` enquanto não houve execução — e é
# justamente a outra metade do código, a que desenha alertas, mensagens e
# mapas, que o usuário vê depois de clicar em «Executar pipeline». Sem esta
# segunda bateria, o teste acima daria uma falsa sensação de cobertura.
# ==========================================================================

def _com_execucao() -> None:
    """Roda o pipeline de verdade e deixa o resultado na sessão."""
    import streamlit as st

    if st.session_state.get("resultado") is not None:
        return
    from agrosentinela.data.loader import carregar_base
    from agrosentinela.orchestrator import Orquestrador

    resultado = Orquestrador(base=carregar_base()).executar(
        horizonte_dias=7, cenario="seca", intensidade_cenario=1.4,
        modo_clima="sintetico", usar_llm=False, max_mensagens=10,
        persistir=False, respeitar_supressao=False,
    )
    st.session_state["resultado"] = resultado


def _executar_com_resultado(nome: str) -> None:
    _com_execucao()
    _executar(RAIZ / "pages" / nome)


def test_painel_executivo_com_alertas():
    _executar_com_resultado("1_📊_Painel_Executivo.py")


def test_mapa_de_risco_com_alertas():
    _executar_com_resultado("2_🗺️_Mapa_de_Risco.py")


def test_radar_climatico_com_alertas():
    _executar_com_resultado("3_🌦️_Radar_Climático.py")


def test_motor_de_regras_com_alertas():
    _executar_com_resultado("4_⚙️_Motor_de_Regras.py")


def test_central_de_comunicacao_com_mensagens():
    _executar_com_resultado("5_💬_Central_de_Comunicação.py")


def test_copiloto_com_execucao():
    _executar_com_resultado("6_🤖_Copiloto_IA.py")


def test_app_com_execucao():
    _com_execucao()
    _executar(RAIZ / "app.py")
