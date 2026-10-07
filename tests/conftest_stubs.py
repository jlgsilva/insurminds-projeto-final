"""
Dublês de ``streamlit`` e ``plotly`` para exercitar as páginas sem interface.

Por que isto existe
-------------------
As páginas do Streamlit só eram testadas abrindo o navegador e clicando. Um
erro como `KeyError: ['lat', 'lon']` — causado por uma junção do pandas que
renomeia colunas em silêncio — só aparecia quando alguém clicava naquela aba
específica, com aqueles dados específicos. Foi assim que a página de dados
externos chegou quebrada à máquina do usuário.

Estes dublês executam **todo o código de cada página**, de cima a baixo, com
os dados reais. Não verificam aparência nenhuma: verificam que o código roda.
É barato, é determinístico e pega a classe de defeito que mais incomoda —
a página que morre com um *traceback* em vez de mostrar o dado.

Os dublês são usados sempre, mesmo quando o Streamlit de verdade está
instalado: rodar a biblioteca real fora de um contexto de execução produz
avisos e comportamentos que variam com a versão, e o objetivo aqui é testar
*o nosso* código.
"""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager
from typing import Any


class _Falso:
    """Objeto que aceita qualquer chamada, atributo e uso como contexto."""

    def __init__(self, nome: str = "") -> None:
        self._nome = nome

    def __call__(self, *args: Any, **kwargs: Any) -> "_Falso":
        return _Falso(self._nome)

    def __getattr__(self, nome: str) -> "_Falso":
        return _Falso(f"{self._nome}.{nome}")

    def __enter__(self) -> "_Falso":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def __iter__(self):
        return iter([])

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:  # pragma: no cover
        return f"<falso {self._nome}>"


class _EstadoSessao(dict):
    """``st.session_state`` — dicionário que também aceita atributos."""

    def __getattr__(self, nome: str) -> Any:
        return self.get(nome)

    def __setattr__(self, nome: str, valor: Any) -> None:
        self[nome] = valor


class _ParouAPagina(Exception):
    """Levantada por ``st.stop()`` — é fluxo normal, não erro."""


def _modulo_streamlit() -> types.ModuleType:
    st = types.ModuleType("streamlit")
    st.session_state = _EstadoSessao()

    # --- widgets: devolvem o valor padrão, como um usuário que não mexeu ---
    def selectbox(rotulo, opcoes, index=0, **kw):
        opcoes = list(opcoes)
        if not opcoes:
            return None
        i = index if isinstance(index, int) and 0 <= index < len(opcoes) else 0
        return opcoes[i]

    def multiselect(rotulo, opcoes, default=None, **kw):
        return list(default or [])

    def radio(rotulo, options, index=0, **kw):
        options = list(options)
        return options[index] if options else None

    def slider(rotulo, minimo=0, maximo=1, valor=None, passo=None, **kw):
        return valor if valor is not None else minimo

    def number_input(rotulo, minimo=0, maximo=None, valor=0, **kw):
        return valor

    def columns(spec, **kw):
        n = spec if isinstance(spec, int) else len(spec)
        return [_Falso(f"col{i}") for i in range(n)]

    def tabs(rotulos):
        return [_Falso(f"tab{i}") for i, _ in enumerate(rotulos)]

    def stop():
        raise _ParouAPagina()

    @contextmanager
    def _contexto(*a, **k):
        yield _Falso("contexto")

    st.selectbox = selectbox
    st.multiselect = multiselect
    st.radio = radio
    st.slider = slider
    st.select_slider = slider
    st.number_input = number_input
    st.text_input = lambda *a, **k: k.get("value", "")
    st.text_area = lambda *a, **k: k.get("value", "")
    st.checkbox = lambda *a, **k: bool(k.get("value", False))
    st.toggle = st.checkbox
    st.button = lambda *a, **k: False
    st.download_button = lambda *a, **k: False
    st.form_submit_button = lambda *a, **k: False
    st.chat_input = lambda *a, **k: None
    st.file_uploader = lambda *a, **k: None
    st.columns = columns
    st.tabs = tabs
    st.stop = stop
    st.expander = _contexto
    st.container = _contexto
    st.form = _contexto
    st.status = _contexto
    st.spinner = _contexto
    st.chat_message = _contexto
    st.sidebar = _Falso("sidebar")
    st.sidebar.__enter__ = lambda *a: _Falso("sidebar")   # type: ignore[attr-defined]
    st.sidebar.__exit__ = lambda *a: False                # type: ignore[attr-defined]
    st.rerun = lambda *a, **k: None
    st.cache_data = lambda *a, **k: (lambda f: f) if not callable(a[0] if a else None) else a[0]
    st.cache_resource = st.cache_data
    st.set_page_config = lambda *a, **k: None
    st.column_config = _Falso("column_config")
    st.components = types.SimpleNamespace(v1=_Falso("components.v1"))
    st.query_params = _EstadoSessao()
    st.secrets = _EstadoSessao()
    st.context = _Falso("context")

    for nome in (
        "markdown", "write", "caption", "title", "header", "subheader",
        "info", "warning", "error", "success", "divider", "dataframe",
        "table", "json", "code", "metric", "plotly_chart", "pyplot",
        "altair_chart", "bar_chart", "line_chart", "area_chart", "map",
        "image", "progress", "toast", "balloons", "empty", "help", "page_link",
    ):
        setattr(st, nome, (lambda *a, **k: None))

    return st


def _modulo_plotly() -> tuple[types.ModuleType, types.ModuleType, types.ModuleType]:
    px = types.ModuleType("plotly.express")
    go = types.ModuleType("plotly.graph_objects")

    class Figure:
        def __init__(self, *a: Any, **k: Any) -> None:
            self.data = []

        def update_traces(self, *a: Any, **k: Any) -> "Figure":
            return self

        def update_layout(self, *a: Any, **k: Any) -> "Figure":
            return self

        def add_trace(self, *a: Any, **k: Any) -> "Figure":
            return self

        def add_annotation(self, *a: Any, **k: Any) -> "Figure":
            return self

        def update_xaxes(self, *a: Any, **k: Any) -> "Figure":
            return self

        def update_yaxes(self, *a: Any, **k: Any) -> "Figure":
            return self

    for nome in ("Figure", "Scatter", "Scattergl", "Bar", "Heatmap", "Indicator",
                 "Table", "Funnel", "Pie", "Box", "Violin", "Histogram",
                 "Scattermap", "Scattermapbox", "Densitymap", "Choropleth",
                 "Sunburst", "Treemap", "Waterfall", "Sankey"):
        setattr(go, nome, Figure)
    go.layout = types.SimpleNamespace(
        Margin=lambda **k: None, Legend=lambda **k: None,
        XAxis=lambda **k: None, YAxis=lambda **k: None,
    )

    def _grafico(*a: Any, **k: Any) -> Figure:
        # Reproduz a exigência do Plotly de que as colunas existam: é
        # justamente esse tipo de erro que queremos capturar aqui.
        quadro = k.get("data_frame")
        if quadro is not None:
            for chave in ("x", "y", "lat", "lon", "color", "size", "z"):
                valor = k.get(chave)
                if isinstance(valor, str) and valor not in quadro.columns:
                    raise KeyError(
                        f"coluna '{valor}' ausente (argumento {chave})"
                    )
        return Figure()

    for nome in ("scatter", "scatter_map", "scatter_mapbox", "density_map",
                 "density_mapbox", "bar", "line", "area", "pie", "histogram",
                 "box", "violin", "imshow", "treemap", "sunburst", "funnel",
                 "scatter_geo", "choropleth", "choropleth_map"):
        setattr(px, nome, _grafico)
    px.colors = types.SimpleNamespace(
        sequential=types.SimpleNamespace(**{n: ["#000", "#fff"] for n in
                                            ("Blues", "Reds", "YlOrBr", "Greens",
                                             "Teal", "Purples", "YlGn", "OrRd")}),
        qualitative=types.SimpleNamespace(Set2=["#000"], Plotly=["#000"]),
        diverging=types.SimpleNamespace(RdYlBu=["#000"], RdYlGn=["#000"]),
    )

    plotly = types.ModuleType("plotly")
    plotly.express = px
    plotly.graph_objects = go
    return plotly, px, go


def instalar_dubles() -> None:
    """Registra os dublês em ``sys.modules`` (idempotente)."""
    if isinstance(sys.modules.get("streamlit"), types.ModuleType) and \
            getattr(sys.modules["streamlit"], "_e_duble", False):
        return

    st = _modulo_streamlit()
    st._e_duble = True
    sys.modules["streamlit"] = st

    plotly, px, go = _modulo_plotly()
    sys.modules["plotly"] = plotly
    sys.modules["plotly.express"] = px
    sys.modules["plotly.graph_objects"] = go
