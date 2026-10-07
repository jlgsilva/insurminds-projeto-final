#!/usr/bin/env python3
"""
Gera os diagramas do relatório técnico (SVG e PNG).

    python scripts/gerar_diagramas.py

Saída em ``Desafio5_Artefatos/diagramas/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "Desafio5_Artefatos" / "diagramas"
SAIDA.mkdir(parents=True, exist_ok=True)

VERDE = "#15803d"
VERDE_CLARO = "#dcfce7"
AZUL = "#1d4ed8"
AZUL_CLARO = "#dbeafe"
LARANJA = "#ea580c"
LARANJA_CLARO = "#ffedd5"
ROXO = "#7c3aed"
ROXO_CLARO = "#ede9fe"
CINZA = "#475569"
CINZA_CLARO = "#f1f5f9"
TINTA = "#0f172a"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.linewidth": 0,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.25,
})


def _caixa(ax, x, y, w, h, titulo, subtitulo="", cor=VERDE, fundo=VERDE_CLARO,
           tamanho_titulo=10, tamanho_sub=7.6):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.035",
        linewidth=1.7, edgecolor=cor, facecolor=fundo, zorder=2,
    ))
    if subtitulo:
        ax.text(x + w / 2, y + h * 0.64, titulo, ha="center", va="center",
                fontsize=tamanho_titulo, fontweight="bold", color=TINTA, zorder=3)
        ax.text(x + w / 2, y + h * 0.28, subtitulo, ha="center", va="center",
                fontsize=tamanho_sub, color=CINZA, zorder=3, linespacing=1.35)
    else:
        ax.text(x + w / 2, y + h / 2, titulo, ha="center", va="center",
                fontsize=tamanho_titulo, fontweight="bold", color=TINTA, zorder=3)


def _seta(ax, x1, y1, x2, y2, cor=CINZA, estilo="-|>", traco="-", largura=1.6):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2), arrowstyle=estilo, mutation_scale=14,
        linewidth=largura, color=cor, linestyle=traco, zorder=1,
        shrinkA=2, shrinkB=2,
    ))


# ==========================================================================
def diagrama_pipeline() -> Path:
    """Fluxo dos seis agentes, com as fontes de dados acima de cada consumidor."""
    fig, ax = plt.subplots(figsize=(14.0, 8.0))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 8)
    ax.axis("off")

    ax.text(7.0, 7.62, "AgroSentinela — pipeline multiagente",
            ha="center", fontsize=16, fontweight="bold", color=TINTA)
    ax.text(7.0, 7.28,
            "Desafio 5 · Comunicação Inteligente · InsurMinds / I2A2",
            ha="center", fontsize=9.5, color=CINZA)

    largura, altura = 2.85, 1.20
    colunas = [0.55, 3.72, 6.89, 10.06]      # x de cada agente da linha superior
    y_agentes = 4.90
    y_fontes = 6.28
    altura_fonte = 0.78

    # ---------------- linha 1: fontes ----------------------------------
    fontes = [
        (colunas[0], "Sicor / Proagro — BCB", "operações, ciclo, cobertura\ne histórico de COP/RCP"),
        (colunas[1], "Open-Meteo", "previsão de 16 dias\nsem chave de API"),
        (colunas[2], "—", ""),
        (colunas[3], "rules.yaml", "15 regras declarativas\nrevisáveis por especialista"),
    ]
    for x, titulo, sub in fontes:
        if titulo == "—":
            continue
        _caixa(ax, x, y_fontes, largura, altura_fonte, titulo, sub,
               cor=CINZA, fundo=CINZA_CLARO, tamanho_titulo=9, tamanho_sub=7)
        _seta(ax, x + largura / 2, y_fontes, x + largura / 2, y_agentes + altura,
              cor=CINZA, traco="--", largura=1.2)

    # ---------------- linha 1: agentes ---------------------------------
    agentes_topo = [
        ("① CarteiraAgent", "universo monitorado\nfase fenológica de hoje", VERDE, VERDE_CLARO),
        ("② ClimaAgent", "coleta externa\nindicadores por célula", AZUL, AZUL_CLARO),
        ("③ EventoAgent", "eventos climáticos\npor território", AZUL, AZUL_CLARO),
        ("④ RegrasAgent", "decisão de negócio\nalertas com score", LARANJA, LARANJA_CLARO),
    ]
    for x, (titulo, sub, cor, fundo) in zip(colunas, agentes_topo):
        _caixa(ax, x, y_agentes, largura, altura, titulo, sub, cor=cor, fundo=fundo)
    for i in range(3):
        x = colunas[i] + largura
        _seta(ax, x, y_agentes + altura / 2, colunas[i + 1], y_agentes + altura / 2, cor=TINTA)

    # ---------------- dobra ④ → ⑤ --------------------------------------
    x_dobra = colunas[3] + largura / 2
    _seta(ax, x_dobra, y_agentes, x_dobra, 4.12, cor=TINTA, estilo="-")
    _seta(ax, x_dobra, 4.12, colunas[3] + largura / 2, 4.12, cor=TINTA, estilo="-")

    # ---------------- linha 2: agentes (direita → esquerda) ------------
    y_linha2 = 2.62
    agentes_base = [
        (colunas[3], "⑤ RedatorAgent", "IA generativa por\npersona e canal", ROXO, ROXO_CLARO),
        (colunas[2], "⑥ DespachanteAgent", "anti-fadiga\nenvio simulado", ROXO, ROXO_CLARO),
        (colunas[1], "Caixa de saída", "SQLite · auditoria\ne histórico de envio", CINZA, CINZA_CLARO),
    ]
    for x, titulo, sub, cor, fundo in agentes_base:
        _caixa(ax, x, y_linha2, largura, altura, titulo, sub, cor=cor, fundo=fundo,
               tamanho_titulo=10 if "Caixa" not in titulo else 9.5)
    _seta(ax, x_dobra, 4.12, x_dobra, y_linha2 + altura, cor=TINTA)
    _seta(ax, colunas[3], y_linha2 + altura / 2, colunas[2] + largura, y_linha2 + altura / 2, cor=TINTA)
    _seta(ax, colunas[2], y_linha2 + altura / 2, colunas[1] + largura, y_linha2 + altura / 2, cor=TINTA)

    # GroqCloud alimenta o redator (seta curta, sem cruzar o desenho)
    _caixa(ax, colunas[3], 1.30, largura, 0.72, "GroqCloud",
           "camada gratuita · Llama 3.3 70B", cor=ROXO, fundo="#ffffff",
           tamanho_titulo=9, tamanho_sub=7)
    _seta(ax, x_dobra, 2.02, x_dobra, y_linha2, cor=ROXO, traco="--", largura=1.2)

    # Copiloto, fora do pipeline
    _caixa(ax, colunas[0], y_linha2, largura, 1.20, "⊕ CopilotoAgent",
           "consulta em linguagem natural\ncom function calling",
           cor=ROXO, fundo="#ffffff", tamanho_titulo=10, tamanho_sub=7.4)
    _seta(ax, colunas[1], y_linha2 + altura / 2, colunas[0] + largura,
          y_linha2 + altura / 2, cor=CINZA, traco=":", largura=1.1)

    # ---------------- rodapé -------------------------------------------
    ax.text(7.0, 0.98,
            "Etapas exigidas pelo enunciado:   ② coleta meteorológica  →  ③ identificação de eventos  →  "
            "④ regras de negócio  →  ⑤ geração das mensagens  →  ⑥ simulação do envio",
            ha="center", fontsize=8.6, color=TINTA, style="italic")

    _caixa(ax, 0.55, 0.18, 12.9, 0.62,
           "16 personas em 5 setores:  produção rural · setor de seguros (subscrição, perícia, atuária, comercial, "
           "corretagem) · crédito e política pública · assistência técnica e MEIs · cadeia produtiva e mercado",
           cor=ROXO, fundo=ROXO_CLARO, tamanho_titulo=8.8)

    legenda = [
        mpatches.Patch(facecolor=VERDE_CLARO, edgecolor=VERDE, label="Dados da carteira"),
        mpatches.Patch(facecolor=AZUL_CLARO, edgecolor=AZUL, label="Meteorologia"),
        mpatches.Patch(facecolor=LARANJA_CLARO, edgecolor=LARANJA, label="Decisão determinística"),
        mpatches.Patch(facecolor=ROXO_CLARO, edgecolor=ROXO, label="IA generativa e comunicação"),
    ]
    # A faixa central-esquerda entre as duas linhas de agentes está livre:
    # é onde a legenda cabe sem colidir com nenhuma caixa.
    ax.legend(handles=legenda, loc="center", bbox_to_anchor=(0.34, 0.525),
              ncol=2, frameon=False, fontsize=8.8, handlelength=1.6,
              columnspacing=2.2, labelspacing=0.9)

    caminhos = []
    for ext in ("png", "svg"):
        p = SAIDA / f"arquitetura_pipeline.{ext}"
        fig.savefig(p, dpi=190 if ext == "png" else None, facecolor="white")
        caminhos.append(p)
    plt.close(fig)
    return caminhos[0]


# ==========================================================================
def diagrama_dados() -> Path:
    """Como os arquivos do Sicor se combinam para formar a inteligência."""
    fig, ax = plt.subplots(figsize=(13.0, 7.0))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 7)
    ax.axis("off")

    ax.text(6.5, 6.62, "Do microdado do Banco Central ao alerta personalizado",
            ha="center", fontsize=14.5, fontweight="bold", color=TINTA)

    arquivos = [
        (0.3, 5.15, "SICOR_OPERACAO_BASICA_ESTADO_AAAA",
         "valor · área · datas do ciclo\ncobertura · irrigação · programa"),
        (0.3, 3.95, "SICOR_COMPLEMENTO_OPERACAO_BASICA",
         "CD_IBGE_MUNICIPIO\n(georreferencia a operação)"),
        (0.3, 2.75, "SICOR_COP_BASICO + SICOR_RCP_BASICO",
         "histórico de sinistro\npor evento e município"),
        (0.3, 1.55, "Tabelas de domínio",
         "Empreendimento · Produto · Programa\nEventoProagro · TipoSeguro · Municípios"),
    ]
    for x, y, titulo, sub in arquivos:
        _caixa(ax, x, y, 4.35, 0.98, titulo, sub, cor=CINZA, fundo=CINZA_CLARO,
               tamanho_titulo=8.4, tamanho_sub=7)

    _caixa(ax, 5.25, 3.40, 2.55, 2.55, "Carteira curada",
           "uma linha por operação\ncom município, cultura,\nfase fenológica,\nexposição e cobertura",
           cor=VERDE, fundo=VERDE_CLARO, tamanho_titulo=10.5, tamanho_sub=8)
    for _, y, _, _ in arquivos:
        _seta(ax, 4.65, y + 0.49, 5.25, 4.65, cor=CINZA, traco="--", largura=1.2)

    _caixa(ax, 5.25, 1.55, 2.55, 1.35, "Previsão",
           "Open-Meteo\npor célula de ~11 km",
           cor=AZUL, fundo=AZUL_CLARO, tamanho_titulo=10.5, tamanho_sub=8)

    _caixa(ax, 8.30, 3.40, 2.20, 2.55, "Motor de regras",
           "15 regras\nem YAML\n\nscore 0–100\nrastreável",
           cor=LARANJA, fundo=LARANJA_CLARO, tamanho_titulo=10.5, tamanho_sub=8)
    _seta(ax, 7.80, 4.65, 8.30, 4.65, cor=TINTA)
    _seta(ax, 7.80, 2.20, 8.30, 4.00, cor=TINTA)

    _caixa(ax, 10.95, 3.40, 1.85, 2.55, "Mensagem",
           "persona\ncanal\ntom\nação\n\nIA generativa",
           cor=ROXO, fundo=ROXO_CLARO, tamanho_titulo=10.5, tamanho_sub=8)
    _seta(ax, 10.50, 4.65, 10.95, 4.65, cor=TINTA)

    ax.text(6.5, 0.85,
            "A diferença entre «vai gear no Sul» e «seu cafezal de 42 ha em Patrocínio-MG está em "
            "brotação\ne a mínima prevista é 1,2 °C na quinta» está inteiramente nos microdados do Sicor.",
            ha="center", fontsize=9, color=TINTA, style="italic", linespacing=1.5)

    caminhos = []
    for ext in ("png", "svg"):
        p = SAIDA / f"fluxo_dados.{ext}"
        fig.savefig(p, dpi=190 if ext == "png" else None, facecolor="white")
        caminhos.append(p)
    plt.close(fig)
    return caminhos[0]


# ==========================================================================
def diagrama_decisao() -> Path:
    """Composição do score e ponto de corte."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 4.6),
                                   gridspec_kw={"width_ratios": [1.05, 1]})

    componentes = ["Severidade\nmeteorológica", "Sensibilidade\nda fase",
                   "Histórico do\nProagro", "Exposição\nfinanceira",
                   "Ausência de\ncobertura"]
    pesos = [40, 25, 15, 12, 8]
    cores = [LARANJA, VERDE, AZUL, ROXO, CINZA]
    barras = ax1.barh(componentes[::-1], pesos[::-1], color=cores[::-1], height=0.62)
    for barra, peso in zip(barras, pesos[::-1]):
        ax1.text(peso + 0.8, barra.get_y() + barra.get_height() / 2,
                 str(peso), va="center", fontsize=10, fontweight="bold", color=TINTA)
    ax1.set_xlim(0, 48)
    ax1.set_title("Composição do score de risco (0–100)", fontsize=11.5,
                  fontweight="bold", color=TINTA, pad=12)
    ax1.set_xlabel("peso", fontsize=9, color=CINZA)
    ax1.tick_params(labelsize=8.6, length=0)
    for lado in ("top", "right", "left", "bottom"):
        ax1.spines[lado].set_visible(False)
    ax1.grid(axis="x", color="#e2e8f0", linewidth=0.8)
    ax1.set_axisbelow(True)

    # Escada de severidade
    niveis = ["Informativo", "Atenção", "Alerta", "Crítico"]
    valores = [1, 2, 3, 4]
    cores_sev = ["#94a3b8", "#f59e0b", "#ea580c", "#b91c1c"]
    ax2.bar(niveis, valores, color=cores_sev, width=0.55)
    ax2.axhline(1.4, color=TINTA, linestyle="--", linewidth=1.4)
    ax2.text(3.45, 1.5, "limiar de\nnotificação\n(score 35)", ha="right", va="bottom",
             fontsize=8.4, color=TINTA)
    ax2.set_title("Escada de severidade e ponto de corte", fontsize=11.5,
                  fontweight="bold", color=TINTA, pad=12)
    ax2.set_ylabel("peso da severidade", fontsize=9, color=CINZA)
    ax2.tick_params(labelsize=9, length=0)
    for lado in ("top", "right", "left"):
        ax2.spines[lado].set_visible(False)
    ax2.spines["bottom"].set_color("#cbd5e1")
    ax2.grid(axis="y", color="#e2e8f0", linewidth=0.8)
    ax2.set_axisbelow(True)

    fig.tight_layout()
    caminhos = []
    for ext in ("png", "svg"):
        p = SAIDA / f"score_risco.{ext}"
        fig.savefig(p, dpi=190 if ext == "png" else None, facecolor="white")
        caminhos.append(p)
    plt.close(fig)
    return caminhos[0]


# ==========================================================================
def main() -> int:
    gerados = [diagrama_pipeline(), diagrama_dados(), diagrama_decisao()]
    print(f"Diagramas gerados em {SAIDA}:")
    for p in sorted(SAIDA.iterdir()):
        print(f"  {p.name:<32} {p.stat().st_size / 1024:7.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
