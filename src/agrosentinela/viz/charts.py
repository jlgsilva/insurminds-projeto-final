"""
Gráficos da aplicação (Plotly).

Todas as funções recebem um DataFrame já agregado e devolvem uma figura
pronta, com layout consistente: sem linhas de grade verticais, rótulos em
português, valores em padrão brasileiro no *hover* e altura previsível.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .theme import (
    CORES_CANAL,
    CORES_EVENTO,
    CORES_SEVERIDADE,
    ORDEM_SEVERIDADE,
    PALETA,
    ROTULO_SEVERIDADE,
)

LAYOUT_BASE: dict[str, Any] = {
    "margin": dict(l=8, r=8, t=44, b=8),
    "hoverlabel": dict(font_size=12),
    "font": dict(size=12),
    "separators": ",.",
    "legend": dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
}


def _aplicar(fig: go.Figure, titulo: str | None = None, altura: int = 330) -> go.Figure:
    fig.update_layout(**LAYOUT_BASE, height=altura, title=titulo or "")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,.18)")
    return fig


def vazio(mensagem: str = "Sem dados para exibir") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=mensagem, showarrow=False, font=dict(size=14, color="#94a3b8"),
        xref="paper", yref="paper", x=0.5, y=0.5,
    )
    fig.update_layout(height=240, margin=dict(l=8, r=8, t=8, b=8),
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


# --------------------------------------------------------------------------
# Alertas
# --------------------------------------------------------------------------

def alertas_por_severidade(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return vazio("Nenhum alerta nesta execução")
    cont = (
        df["severidade"].value_counts()
        .reindex(ORDEM_SEVERIDADE).fillna(0).astype(int).reset_index()
    )
    cont.columns = ["severidade", "alertas"]
    cont["rotulo"] = cont["severidade"].map(ROTULO_SEVERIDADE)
    fig = px.bar(
        cont, x="alertas", y="rotulo", orientation="h", text="alertas",
        color="severidade", color_discrete_map=CORES_SEVERIDADE,
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(showlegend=False, yaxis_title="", xaxis_title="alertas")
    return _aplicar(fig, "Alertas por severidade", 280)


def alertas_por_evento(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return vazio("Nenhum alerta nesta execução")
    agg = (
        df.groupby(["evento", "evento_nome", "severidade"], as_index=False)
        .agg(alertas=("id", "count"))
    )
    agg["rotulo_sev"] = agg["severidade"].map(ROTULO_SEVERIDADE)
    fig = px.bar(
        agg.sort_values("alertas", ascending=True),
        x="alertas", y="evento_nome", color="rotulo_sev", orientation="h",
        color_discrete_map={ROTULO_SEVERIDADE[k]: v for k, v in CORES_SEVERIDADE.items()},
        category_orders={"rotulo_sev": [ROTULO_SEVERIDADE[s] for s in ORDEM_SEVERIDADE]},
    )
    fig.update_layout(yaxis_title="", xaxis_title="alertas", legend_title="")
    return _aplicar(fig, "Alertas por evento climático", 340)


def exposicao_por_uf(df: pd.DataFrame, coluna_valor: str = "valor_credito") -> go.Figure:
    if df.empty:
        return vazio("Sem exposição para exibir")
    agg = (
        df.groupby("uf", as_index=False)
        .agg(exposicao=(coluna_valor, "sum"), alertas=("id", "count"))
        .sort_values("exposicao", ascending=True)
        .tail(18)
    )
    agg["exposicao_mi"] = (agg["exposicao"] / 1e6).round(1)
    fig = px.bar(
        agg, x="exposicao_mi", y="uf", orientation="h", text="exposicao_mi",
        custom_data=["alertas"],
    )
    fig.update_traces(
        marker_color=PALETA[0], textposition="outside", cliponaxis=False,
        hovertemplate="UF %{y}<br>Exposição: R$ %{x} mi<br>Alertas: %{customdata[0]}<extra></extra>",
    )
    fig.update_layout(yaxis_title="", xaxis_title="R$ milhões")
    return _aplicar(fig, "Exposição sinalizada por UF", 380)


def matriz_evento_cultura(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return vazio("Sem alertas para cruzar")
    piv = (
        df.pivot_table(index="produto", columns="evento_nome", values="id",
                       aggfunc="count", fill_value=0)
        .astype(int)
    )
    piv = piv.loc[piv.sum(axis=1).sort_values(ascending=False).head(12).index]
    fig = px.imshow(
        piv, text_auto=True, aspect="auto",
        color_continuous_scale=["#f8fafc", "#fcd34d", "#ea580c", "#7f1d1d"],
    )
    fig.update_layout(xaxis_title="", yaxis_title="", coloraxis_showscale=False)
    fig.update_xaxes(tickangle=-25)
    return _aplicar(fig, "Alertas por cultura × evento", 420)


def distribuicao_score(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return vazio("Sem alertas")
    fig = px.histogram(
        df, x="score", color="severidade", nbins=24,
        color_discrete_map=CORES_SEVERIDADE,
        category_orders={"severidade": ORDEM_SEVERIDADE},
    )
    fig.update_layout(xaxis_title="score de risco (0–100)", yaxis_title="alertas",
                      legend_title="", bargap=0.06)
    return _aplicar(fig, "Distribuição do score de risco", 300)


def fases_afetadas(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return vazio("Sem alertas")
    agg = (
        df.groupby("fase_nome", as_index=False)
        .agg(alertas=("id", "count"), exposicao=("valor_credito", "sum"))
        .sort_values("alertas", ascending=True)
    )
    agg["exposicao_mi"] = (agg["exposicao"] / 1e6).round(1)
    fig = px.bar(agg, x="alertas", y="fase_nome", orientation="h",
                 custom_data=["exposicao_mi"])
    fig.update_traces(
        marker_color=PALETA[2],
        hovertemplate="%{y}<br>Alertas: %{x}<br>Exposição: R$ %{customdata[0]} mi<extra></extra>",
    )
    fig.update_layout(yaxis_title="", xaxis_title="alertas")
    return _aplicar(fig, "Fase produtiva das operações alertadas", 320)


# --------------------------------------------------------------------------
# Clima
# --------------------------------------------------------------------------

def serie_climatica(df: pd.DataFrame, titulo: str = "Previsão diária") -> go.Figure:
    if df.empty:
        return vazio("Sem série meteorológica")
    d = df.copy()
    d["data"] = pd.to_datetime(d["data"])
    d = d.sort_values("data")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=d["data"], y=d["precipitacao"], name="Chuva (mm)",
        marker_color="#60a5fa", yaxis="y",
        hovertemplate="%{x|%d/%m}<br>Chuva: %{y:.1f} mm<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=d["data"], y=d["tmax"], name="T. máxima (°C)", mode="lines+markers",
        line=dict(color="#dc2626", width=2), yaxis="y2",
        hovertemplate="%{x|%d/%m}<br>Máx: %{y:.1f} °C<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=d["data"], y=d["tmin"], name="T. mínima (°C)", mode="lines+markers",
        line=dict(color="#2563eb", width=2), yaxis="y2",
        hovertemplate="%{x|%d/%m}<br>Mín: %{y:.1f} °C<extra></extra>",
    ))
    if "et0" in d.columns:
        fig.add_trace(go.Scatter(
            x=d["data"], y=d["et0"], name="ET0 (mm)", mode="lines",
            line=dict(color="#a16207", width=1.5, dash="dot"), yaxis="y",
            hovertemplate="%{x|%d/%m}<br>ET0: %{y:.1f} mm<extra></extra>",
        ))

    fig.update_layout(
        **LAYOUT_BASE, height=380, title=titulo,
        yaxis=dict(title="mm", side="left", gridcolor="rgba(128,128,128,.18)"),
        yaxis2=dict(title="°C", overlaying="y", side="right", showgrid=False),
        barmode="overlay", hovermode="x unified",
    )
    return fig


def barras_indicadores(valores: dict[str, Any], chaves: list[str], titulo: str) -> go.Figure:
    dados = [(k, float(valores[k])) for k in chaves
             if k in valores and valores[k] is not None]
    if not dados:
        return vazio("Sem indicadores")
    d = pd.DataFrame(dados, columns=["indicador", "valor"])
    fig = px.bar(d, x="valor", y="indicador", orientation="h", text="valor")
    fig.update_traces(marker_color=PALETA[4], textposition="outside", cliponaxis=False)
    fig.update_layout(yaxis_title="", xaxis_title="")
    return _aplicar(fig, titulo, 60 + 34 * len(d))


# --------------------------------------------------------------------------
# Carteira e Proagro
# --------------------------------------------------------------------------

def composicao_carteira(df: pd.DataFrame, dimensao: str = "cultura") -> go.Figure:
    if df.empty or dimensao not in df.columns:
        return vazio("Sem carteira carregada")
    agg = (
        df.groupby(dimensao, as_index=False)
        .agg(valor=("valor_credito", "sum"), operacoes=("ref_bacen", "count"))
        .sort_values("valor", ascending=False)
        .head(14)
    )
    fig = px.treemap(
        agg, path=[dimensao], values="valor", color="valor",
        color_continuous_scale=["#dcfce7", "#22c55e", "#15803d", "#14532d"],
        custom_data=["operacoes"],
    )
    fig.update_traces(
        texttemplate="%{label}<br>R$ %{value:,.0f}",
        hovertemplate="%{label}<br>Valor: R$ %{value:,.2f}<br>Operações: %{customdata[0]}<extra></extra>",
    )
    fig.update_layout(margin=dict(l=4, r=4, t=42, b=4), height=400,
                      title=f"Carteira por {dimensao}", coloraxis_showscale=False,
                      separators=",.")
    return fig


def cobertura_por_programa(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return vazio("Sem carteira carregada")
    agg = (
        df.assign(programa_curto=df["programa"].astype(str).str.split(" - ").str[0])
        .groupby("programa_curto", as_index=False)
        .agg(valor=("valor_credito", "sum"), cobertura=("tem_cobertura", "mean"),
             operacoes=("ref_bacen", "count"))
        .sort_values("valor", ascending=True)
    )
    agg["cobertura_pct"] = (agg["cobertura"] * 100).round(1)
    fig = px.bar(
        agg, x="cobertura_pct", y="programa_curto", orientation="h",
        text="cobertura_pct", custom_data=["operacoes"],
    )
    fig.update_traces(
        marker_color="#0891b2", textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br>Cobertura: %{x}%<br>Operações: %{customdata[0]}<extra></extra>",
    )
    fig.update_layout(yaxis_title="", xaxis_title="% das operações com cobertura declarada",
                      xaxis_range=[0, 105])
    return _aplicar(fig, "Cobertura de risco por programa de crédito", 340)


def sinistralidade_evento(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return vazio("Sem histórico de Proagro")
    agg = (
        df.groupby("evento_proagro", as_index=False)
        .agg(cop=("n_cop", "sum"), rcp=("n_rcp", "sum"),
             indenizado=("valor_indenizado", "sum"))
        .sort_values("cop", ascending=True)
    )
    fig = go.Figure()
    fig.add_trace(go.Bar(y=agg["evento_proagro"], x=agg["cop"], name="Pedidos de cobertura",
                         orientation="h", marker_color="#f59e0b"))
    fig.add_trace(go.Bar(y=agg["evento_proagro"], x=agg["rcp"], name="Comprovações de perda",
                         orientation="h", marker_color="#b91c1c"))
    fig.update_layout(barmode="group", yaxis_title="", xaxis_title="ocorrências")
    return _aplicar(fig, "Acionamento histórico do Proagro por evento", 400)


def serie_credito_anual(df: pd.DataFrame, por: str = "cultura", top: int = 6) -> go.Figure:
    if df.empty:
        return vazio("Sem série histórica")
    maiores = (
        df.groupby(por)["valor_credito"].sum().sort_values(ascending=False).head(top).index
    )
    d = df[df[por].isin(maiores)].groupby(["ano", por], as_index=False)["valor_credito"].sum()
    d["valor_bi"] = (d["valor_credito"] / 1e9).round(3)
    fig = px.line(d, x="ano", y="valor_bi", color=por, markers=True,
                  color_discrete_sequence=PALETA)
    fig.update_layout(yaxis_title="R$ bilhões", xaxis_title="", legend_title="")
    return _aplicar(fig, f"Evolução da contratação por {por}", 360)


# --------------------------------------------------------------------------
# Comunicação
# --------------------------------------------------------------------------

def mensagens_por_persona(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return vazio("Nenhuma mensagem gerada")
    agg = (
        df.groupby(["persona", "canal"], as_index=False)
        .agg(mensagens=("id", "count"))
        .sort_values("mensagens", ascending=True)
    )
    fig = px.bar(agg, x="mensagens", y="persona", color="canal", orientation="h",
                 color_discrete_map=CORES_CANAL)
    fig.update_layout(yaxis_title="", xaxis_title="mensagens", legend_title="canal")
    return _aplicar(fig, "Mensagens por persona e canal", 380)


def funil_comunicacao(
    operacoes: int, alertas: int, mensagens: int, entregues: int
) -> go.Figure:
    fig = go.Figure(go.Funnel(
        y=["Operações monitoradas", "Alertas gerados", "Mensagens redigidas",
           "Entregas simuladas"],
        x=[operacoes, alertas, mensagens, entregues],
        textinfo="value+percent initial",
        marker=dict(color=["#0f766e", "#ea580c", "#2563eb", "#15803d"]),
    ))
    fig.update_layout(**LAYOUT_BASE, height=330, title="Funil de comunicação proativa")
    return fig


def custo_por_canal(df: pd.DataFrame) -> go.Figure:
    if df.empty or "custo_estimado_R$" not in df.columns:
        return vazio("Sem envios simulados")
    agg = (
        df.groupby("canal", as_index=False)
        .agg(custo=("custo_estimado_R$", "sum"), envios=("id", "count"))
        .sort_values("custo", ascending=True)
    )
    fig = px.bar(agg, x="custo", y="canal", orientation="h", custom_data=["envios"],
                 color="canal", color_discrete_map=CORES_CANAL)
    fig.update_traces(
        hovertemplate="%{y}<br>Custo: R$ %{x:.4f}<br>Envios: %{customdata[0]}<extra></extra>"
    )
    fig.update_layout(showlegend=False, yaxis_title="",
                      xaxis_title="custo equivalente de envio real (R$)")
    return _aplicar(fig, "Custo simulado por canal", 300)


def uso_llm(por_tarefa: list[dict[str, Any]]) -> go.Figure:
    if not por_tarefa:
        return vazio("Nenhuma chamada ao modelo nesta execução")
    d = pd.DataFrame(por_tarefa).sort_values("tokens", ascending=True)
    fig = px.bar(d, x="tokens", y="tarefa", orientation="h",
                 custom_data=["chamadas", "cache", "latencia_s"])
    fig.update_traces(
        marker_color=PALETA[3],
        hovertemplate=("%{y}<br>Tokens: %{x}<br>Chamadas: %{customdata[0]}"
                       "<br>Do cache: %{customdata[1]}<br>Latência: %{customdata[2]} s<extra></extra>"),
    )
    fig.update_layout(yaxis_title="", xaxis_title="tokens")
    return _aplicar(fig, "Consumo de IA generativa por tarefa", 60 + 34 * len(d))
