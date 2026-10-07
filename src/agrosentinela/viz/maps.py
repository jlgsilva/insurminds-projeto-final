"""
Mapas da aplicação.

Compatibilidade: a API de mapas do Plotly mudou de ``scatter_mapbox`` para
``scatter_map`` (MapLibre) na versão 6. As funções abaixo escolhem em tempo
de execução a API disponível, de modo que o aplicativo funcione com as duas
gerações da biblioteca **sem exigir token de mapa** — requisito para rodar
na camada gratuita do Streamlit Cloud.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .theme import (
    CORES_CANAL,
    CORES_SEVERIDADE,
    ORDEM_SEVERIDADE,
    ROTULO_SEVERIDADE,
)
from .charts import vazio

# Centro aproximado do território brasileiro
CENTRO_BR = {"lat": -14.5, "lon": -52.0}
ZOOM_BR = 3.1

_USA_MAPLIBRE = hasattr(px, "scatter_map")


def _preparar(df: pd.DataFrame, *colunas_obrigatorias: str) -> pd.DataFrame | None:
    """
    Valida o conjunto antes de desenhar e devolve ``None`` se não der para
    desenhar.

    Existe por uma razão aprendida na prática: ``df.dropna(subset=[...])``
    levanta ``KeyError`` quando a coluna **não existe**, e essa exceção sobe
    até o Streamlit e derruba a página inteira com um *traceback* — em vez de
    mostrar "este mapa não está disponível" e deixar o resto da página
    funcionando.

    Um mapa é um enfeite em relação ao dado; ele nunca deve ser capaz de
    impedir alguém de ver o dado.
    """
    if df is None or df.empty:
        return None
    faltando = [c for c in colunas_obrigatorias if c not in df.columns]
    if faltando:
        return None
    base = df.dropna(subset=list(colunas_obrigatorias))
    return None if base.empty else base


def _sem_coordenada(o_que: str = "estes dados") -> go.Figure:
    return vazio(
        f"Sem coordenadas para {o_que}.\n"
        "Verifique se a tabela de municípios foi carregada."
    )


def _scatter(**kwargs: Any) -> go.Figure:
    """Chama ``px.scatter_map`` ou ``px.scatter_mapbox``, conforme a versão."""
    estilo = kwargs.pop("estilo", "carto-positron")
    if _USA_MAPLIBRE:
        return px.scatter_map(map_style=estilo, **kwargs)
    return px.scatter_mapbox(mapbox_style=estilo, **kwargs)


def _densidade(**kwargs: Any) -> go.Figure:
    estilo = kwargs.pop("estilo", "carto-positron")
    if hasattr(px, "density_map"):
        return px.density_map(map_style=estilo, **kwargs)
    return px.density_mapbox(mapbox_style=estilo, **kwargs)


def _finalizar(fig: go.Figure, altura: int = 520, titulo: str = "") -> go.Figure:
    fig.update_layout(
        height=altura,
        margin=dict(l=0, r=0, t=38 if titulo else 0, b=0),
        title=titulo,
        legend=dict(orientation="h", yanchor="bottom", y=0.01, xanchor="left", x=0.01,
                    bgcolor="rgba(255,255,255,.75)"),
        separators=",.",
    )
    return fig


# --------------------------------------------------------------------------
# Mapas
# --------------------------------------------------------------------------

def mapa_alertas(df: pd.DataFrame, altura: int = 560) -> go.Figure:
    """Bolhas por município: tamanho = exposição, cor = severidade máxima."""
    base = _preparar(df, "lat", "lon", "cd_ibge", "municipio", "uf")
    if base is None:
        return _sem_coordenada("os alertas desta execução")

    agg = (
        base.groupby(["cd_ibge", "municipio", "uf", "lat", "lon"], as_index=False)
        .agg(
            alertas=("id", "count"),
            exposicao=("valor_credito", "sum"),
            area_ha=("area_ha", "sum"),
            score=("score", "max"),
            peso_sev=("severidade_peso", "max"),
            eventos=("evento_nome", lambda s: ", ".join(sorted(set(s))[:3])),
        )
    )
    inverso = {4: "critico", 3: "alerta", 2: "atencao", 1: "informativo"}
    agg["severidade"] = agg["peso_sev"].map(inverso).fillna("informativo")
    agg["rotulo_sev"] = agg["severidade"].map(ROTULO_SEVERIDADE)
    agg["exposicao_mi"] = (agg["exposicao"] / 1e6).round(2)
    agg["local"] = agg["municipio"] + " - " + agg["uf"]

    fig = _scatter(
        data_frame=agg, lat="lat", lon="lon",
        size="exposicao", size_max=42,
        color="rotulo_sev",
        color_discrete_map={ROTULO_SEVERIDADE[k]: v for k, v in CORES_SEVERIDADE.items()},
        category_orders={"rotulo_sev": [ROTULO_SEVERIDADE[s] for s in ORDEM_SEVERIDADE]},
        hover_name="local",
        custom_data=["alertas", "exposicao_mi", "area_ha", "score", "eventos"],
        zoom=ZOOM_BR, center=CENTRO_BR,
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{hovertext}</b><br>"
            "Alertas: %{customdata[0]}<br>"
            "Exposição: R$ %{customdata[1]} mi<br>"
            "Área: %{customdata[2]:,.0f} ha<br>"
            "Score máximo: %{customdata[3]:.0f}<br>"
            "Eventos: %{customdata[4]}<extra></extra>"
        )
    )
    return _finalizar(fig, altura)


def mapa_carteira(df: pd.DataFrame, altura: int = 560) -> go.Figure:
    """Distribuição da carteira monitorada, colorida pela cultura dominante."""
    base = _preparar(df, "lat", "lon", "cd_ibge", "municipio", "uf")
    if base is None:
        return _sem_coordenada("a carteira")

    agg = (
        base.groupby(["cd_ibge", "municipio", "uf", "lat", "lon"], as_index=False)
        .agg(
            operacoes=("ref_bacen", "count"),
            valor=("valor_credito", "sum"),
            area_ha=("area_ha", "sum"),
            cobertura=("tem_cobertura", "mean"),
            cultura=("cultura", lambda s: s.value_counts().index[0] if len(s) else "—"),
        )
    )
    agg["valor_mi"] = (agg["valor"] / 1e6).round(2)
    agg["cobertura_pct"] = (agg["cobertura"] * 100).round(1)
    agg["local"] = agg["municipio"] + " - " + agg["uf"]

    fig = _scatter(
        data_frame=agg, lat="lat", lon="lon", size="valor", size_max=40,
        color="cultura", hover_name="local",
        custom_data=["operacoes", "valor_mi", "area_ha", "cobertura_pct", "cultura"],
        zoom=ZOOM_BR, center=CENTRO_BR,
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{hovertext}</b><br>"
            "Operações: %{customdata[0]}<br>"
            "Valor: R$ %{customdata[1]} mi<br>"
            "Área: %{customdata[2]:,.0f} ha<br>"
            "Com cobertura: %{customdata[3]}%<br>"
            "Cultura principal: %{customdata[4]}<extra></extra>"
        )
    )
    return _finalizar(fig, altura)


def mapa_indicador(
    df: pd.DataFrame,
    coluna: str,
    rotulo: str,
    *,
    escala: str = "RdYlBu_r",
    altura: int = 560,
) -> go.Figure:
    """Mapa de um indicador meteorológico por município."""
    base = _preparar(df, "lat", "lon", coluna)
    if base is None:
        return vazio(
            f"Indicador «{rotulo}» indisponível.\n"
            "Falta a coluna, a coordenada do município, ou não há valores."
        )

    base = base.copy()
    if "municipio" in base.columns:
        base["local"] = (base["municipio"].astype(str) + " - "
                         + base.get("uf", "").astype(str))
    else:
        base["local"] = base.get("cd_ibge", "").astype(str)
    fig = _scatter(
        data_frame=base, lat="lat", lon="lon", color=coluna,
        color_continuous_scale=escala, size_max=26,
        size=[12] * len(base),
        hover_name="local", custom_data=[coluna],
        zoom=ZOOM_BR, center=CENTRO_BR,
    )
    fig.update_traces(
        hovertemplate="<b>%{hovertext}</b><br>" + rotulo + ": %{customdata[0]:,.1f}<extra></extra>"
    )
    fig.update_layout(coloraxis_colorbar=dict(title=rotulo, thickness=12))
    return _finalizar(fig, altura)


def mapa_densidade_sinistros(df: pd.DataFrame, altura: int = 520) -> go.Figure:
    """Mapa de calor do acionamento histórico do Proagro."""
    base = _preparar(df, "lat", "lon", "n_cop")
    if base is None:
        return _sem_coordenada("o histórico do Proagro")
    fig = _densidade(
        data_frame=base, lat="lat", lon="lon", z="n_cop", radius=26,
        center=CENTRO_BR, zoom=ZOOM_BR,
        color_continuous_scale=["#e0f2fe", "#fbbf24", "#ea580c", "#7f1d1d"],
    )
    fig.update_layout(coloraxis_colorbar=dict(title="Pedidos de<br>cobertura", thickness=12))
    return _finalizar(fig, altura)


# ==========================================================================
# Mapas dos conjuntos enriquecidos
#
# Regra de projeto: **sempre que o dado tem coordenada, ele aparece no mapa**.
# Tabela é para conferir; mapa é para decidir. Quem trabalha com território
# — extensionista, perito, gerente de agência, gestor público — pensa em
# mapa, e obrigar essas pessoas a reconstruir mentalmente a geografia a
# partir de uma lista de municípios é jogar fora a melhor propriedade do
# dado do Sicor: ele é georreferenciado na origem.
# ==========================================================================

def mapa_glebas(df: pd.DataFrame, altura: int = 560,
                colorir_por: str = "cultura") -> go.Figure:
    """
    Talhões financiados, no centroide do **próprio polígono**.

    A diferença para ``mapa_carteira`` é o que este projeto tem de mais
    concreto: ali cada ponto é o centroide do município; aqui é a lavoura.
    Em municípios como Ribas do Rio Pardo ou Altamira, a distância entre os
    dois passa de 80 km — o bastante para consultar uma frente de chuva que
    não está sobre a lavoura.
    """
    base = _preparar(df, "lat", "lon")
    if base is None:
        return vazio(
            "Sem geometria de glebas.\n"
            "Rode: python etl/06_build_glebas.py"
        )
    base = base.copy()

    base["area"] = pd.to_numeric(base.get("area_gleba_ha"), errors="coerce").fillna(1.0)
    cor = colorir_por if colorir_por in base.columns else None
    fig = _scatter(
        data_frame=base, lat="lat", lon="lon",
        color=cor, size="area", size_max=24,
        hover_name=cor if cor else None,
        custom_data=["ref_bacen", "nu_gleba", "area_gleba_ha",
                     "area_wkt_ha", "divergencia_area_pct"],
        zoom=ZOOM_BR, center=CENTRO_BR, opacity=0.75,
    )
    fig.update_traces(
        hovertemplate=(
            "<b>Gleba %{customdata[1]}</b><br>"
            "Operação: %{customdata[0]}<br>"
            "Área declarada: %{customdata[2]:,.1f} ha<br>"
            "Área do polígono: %{customdata[3]:,.1f} ha<br>"
            "Divergência: %{customdata[4]:,.1f}%<extra></extra>"
        )
    )
    return _finalizar(fig, altura)


def mapa_exposicao(df: pd.DataFrame, altura: int = 560,
                   coluna: str = "saldo_devedor") -> go.Figure:
    """
    Exposição financeira por município: onde está o **dinheiro** em risco.

    É o mapa que a área de crédito abre primeiro — e o que converte a
    conversa de hectares para reais.
    """
    base = _preparar(df, "lat", "lon", coluna)
    if base is None:
        return vazio(
            "Sem dados de exposição financeira.\n"
            "Rode: python etl/07_build_exposicao.py"
        )
    base = base.copy()

    base[coluna] = pd.to_numeric(base[coluna], errors="coerce").fillna(0.0)
    base = base[base[coluna] > 0]
    if base.empty:
        return vazio("Nenhuma exposição positiva a exibir")
    base["local"] = base["municipio"].astype(str) + " - " + base["uf"].astype(str)

    vencido = base["saldo_vencido"] if "saldo_vencido" in base.columns else 0.0
    base["_vencido"] = pd.to_numeric(vencido, errors="coerce").fillna(0.0)
    base["_inad"] = (base["_vencido"] / base[coluna].replace(0, float("nan"))).fillna(0.0)

    fig = _scatter(
        data_frame=base, lat="lat", lon="lon",
        size=coluna, color="_inad", size_max=34,
        color_continuous_scale=["#15803d", "#f59e0b", "#b91c1c"],
        range_color=(0, 0.35),
        hover_name="local",
        custom_data=[coluna, "_vencido", "_inad"],
        zoom=ZOOM_BR, center=CENTRO_BR, opacity=0.8,
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{hovertext}</b><br>"
            "Saldo devedor: R$ %{customdata[0]:,.0f}<br>"
            "Saldo vencido: R$ %{customdata[1]:,.0f}<br>"
            "Inadimplência: %{customdata[2]:.1%}<extra></extra>"
        )
    )
    fig.update_layout(coloraxis_colorbar=dict(title="Inadim-<br>plência", thickness=12))
    return _finalizar(fig, altura)


def mapa_cobertura(df: pd.DataFrame, altura: int = 560) -> go.Figure:
    """
    Mapa da **proteção**: onde a lavoura financiada está descoberta.

    Soma a cobertura pública do Sicor com a penetração do seguro privado
    (PSR/MAPA). Verde é praça madura; vermelho é deserto de proteção. É
    simultaneamente um mapa de risco sistêmico (para política pública e
    resseguro) e um mapa de oportunidade comercial (para seguradora e
    corretora) — as duas leituras saem do mesmo dado.
    """
    base = _preparar(df, "lat", "lon")
    if base is None:
        return _sem_coordenada("o mapa de proteção")
    base = base.copy()
    coluna = next((c for c in ("cobertura_total", "cobertura_municipio",
                               "pct_cobertura") if c in base.columns), None)
    if coluna is None:
        return vazio("Sem coluna de proteção neste conjunto")

    base[coluna] = pd.to_numeric(base[coluna], errors="coerce").fillna(0.0)
    base["local"] = base["municipio"].astype(str) + " - " + base["uf"].astype(str)
    tamanho = ("area_municipio" if "area_municipio" in base.columns
               else ("valor_credito" if "valor_credito" in base.columns else None))

    fig = _scatter(
        data_frame=base, lat="lat", lon="lon", color=coluna,
        size=tamanho, size_max=30,
        color_continuous_scale=["#b91c1c", "#f59e0b", "#15803d"],
        range_color=(0, 1),
        hover_name="local", custom_data=[coluna],
        zoom=ZOOM_BR, center=CENTRO_BR, opacity=0.82,
    )
    fig.update_traces(
        hovertemplate="<b>%{hovertext}</b><br>Proteção: %{customdata[0]:.0%}"
                      "<extra></extra>"
    )
    fig.update_layout(coloraxis_colorbar=dict(title="Proteção", thickness=12,
                                              tickformat=".0%"))
    return _finalizar(fig, altura)


def mapa_mensagens(df: pd.DataFrame, altura: int = 520) -> go.Figure:
    """
    Onde as mensagens foram entregues, colorido por canal.

    Serve a uma pergunta de auditoria que nenhuma tabela responde bem:
    *a comunicação chegou onde o risco está?* Comparado lado a lado com o
    mapa de alertas, expõe cobertura desigual na hora.
    """
    base = _preparar(df, "lat", "lon")
    if base is None:
        return vazio(
            "Nenhuma mensagem individual com coordenada.\n"
            "Os boletins institucionais consolidam vários municípios."
        )
    base = base.copy()
    cor = "canal" if "canal" in base.columns else None
    fig = _scatter(
        data_frame=base, lat="lat", lon="lon", color=cor,
        color_discrete_map=CORES_CANAL if cor else None,
        size=[13] * len(base), size_max=20,
        hover_name="municipio" if "municipio" in base.columns else None,
        custom_data=[c for c in ("canal", "persona_nome", "severidade")
                     if c in base.columns],
        zoom=ZOOM_BR, center=CENTRO_BR, opacity=0.85,
    )
    return _finalizar(fig, altura)


def mapa_focos_calor(df: pd.DataFrame, altura: int = 520) -> go.Figure:
    """
    Focos de calor do INPE, um ponto por foco.

    Fogo é evento coberto pelo Proagro e o mais subnotificado em pastagem e
    cana. Também importa o fogo **vizinho**: a queima de resteva no imóvel ao
    lado é causa frequente de perda em lavoura segurada — e isso só se
    enxerga no mapa.
    """
    base = _preparar(df, "lat", "lon")
    if base is None:
        return vazio("Monitoramento de fogo indisponível no momento")
    base = base.copy()
    fig = _densidade(
        data_frame=base, lat="lat", lon="lon", radius=16,
        center=CENTRO_BR, zoom=ZOOM_BR,
        color_continuous_scale=["#fef3c7", "#f59e0b", "#dc2626", "#450a0a"],
    )
    fig.update_layout(coloraxis_colorbar=dict(title="Focos", thickness=12))
    return _finalizar(fig, altura)


def disponivel() -> dict[str, Any]:
    """Informação de diagnóstico exibida na página de documentação."""
    return {
        "api_de_mapas": "plotly.express.scatter_map (MapLibre)" if _USA_MAPLIBRE
        else "plotly.express.scatter_mapbox",
        "token_necessario": False,
        "estilo_padrao": "carto-positron",
    }
