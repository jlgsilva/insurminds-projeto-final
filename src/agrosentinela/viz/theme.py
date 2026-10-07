"""
Tema visual do AgroSentinela.

Paleta pensada para leitura rápida de risco: as cores de severidade seguem
uma escala sequencial quente única (não semáforo puro), com contraste
suficiente em tema claro e escuro, e são distinguíveis nas formas mais
comuns de daltonismo (deuteranopia e protanopia) — o que importa quando a
informação exibida é "esta lavoura pode ser perdida".
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Cores
# --------------------------------------------------------------------------

VERDE = "#15803d"
VERDE_CLARO = "#86efac"
TERRA = "#92400e"
AREIA = "#fef3c7"
AZUL = "#1d4ed8"
CINZA = "#475569"

CORES_SEVERIDADE: dict[str, str] = {
    "informativo": "#94a3b8",
    "atencao": "#f59e0b",
    "alerta": "#ea580c",
    "critico": "#b91c1c",
}

ICONES_SEVERIDADE: dict[str, str] = {
    "informativo": "ℹ️",
    "atencao": "⚠️",
    "alerta": "🔶",
    "critico": "🔴",
}

RGB_SEVERIDADE: dict[str, list[int]] = {
    "informativo": [148, 163, 184],
    "atencao": [245, 158, 11],
    "alerta": [234, 88, 12],
    "critico": [185, 28, 28],
}

CORES_EVENTO: dict[str, str] = {
    "seca": "#d97706",
    "chuva_excessiva": "#2563eb",
    "chuva_intensa": "#1d4ed8",
    "granizo": "#0ea5e9",
    "geada": "#38bdf8",
    "onda_calor": "#dc2626",
    "vendaval": "#4b5563",
    "umidade_colheita": "#a16207",
    "consolidado": "#64748b",
    "multiplo": "#64748b",
}

CORES_CANAL: dict[str, str] = {
    "whatsapp": "#16a34a",
    "sms": "#7c3aed",
    "email": "#2563eb",
    "push": "#db2777",
    "painel": "#0f766e",
    "voz": "#b45309",
}

# Paleta categórica para gráficos genéricos (testada para daltonismo)
PALETA = [
    "#2563eb", "#ea580c", "#15803d", "#7c3aed", "#0891b2",
    "#b91c1c", "#a16207", "#be185d", "#4338ca", "#047857",
]

ORDEM_SEVERIDADE = ["critico", "alerta", "atencao", "informativo"]

ROTULO_SEVERIDADE = {
    "critico": "Crítico",
    "alerta": "Alerta",
    "atencao": "Atenção",
    "informativo": "Informativo",
}


# --------------------------------------------------------------------------
# CSS da aplicação
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# CSS da aplicação — responsivo por construção
#
# A solução é consultada em três situações muito diferentes:
#
# * **no celular**, por produtor, extensionista e técnico **em campo**, muitas
#   vezes com uma mão só, sol na tela e conexão ruim;
# * **no tablet**, por assessor e perito em visita;
# * **no desktop**, por analista de crédito, atuário e gestor público.
#
# Por isso o layout não é "desktop encolhido": os pontos de quebra abaixo
# mudam o que aparece, o tamanho do toque e a densidade da informação. As
# decisões concretas:
#
# * alvo de toque mínimo de 44 px (recomendação de acessibilidade da WCAG e
#   das diretrizes de iOS e Android) em botões, abas e itens de seleção;
# * colunas do Streamlit **empilham** abaixo de 640 px em vez de espremer —
#   três métricas de 90 px de largura não são legíveis, são decorativas;
# * tipografia fluida com ``clamp()``, para o número do alerta continuar
#   legível sem zoom;
# * tabelas e gráficos largos rolam **dentro do seu próprio quadro**, nunca
#   empurrando a página inteira para o lado;
# * ``prefers-reduced-motion`` respeitado;
# * foco visível em toda a navegação por teclado.
# --------------------------------------------------------------------------

ALTURA_MAPA_PADRAO = 560
ALTURA_MAPA_COMPACTA = 380

CSS = """
<style>
  /* ===================== tokens ===================== */
  :root {
      --as-raio: 12px;
      --as-borda: 1px solid rgba(128,128,128,.22);
      --as-toque: 44px;            /* alvo mínimo de toque */
      --as-gap: 12px;
  }

  /* ===================== blocos de métrica ===================== */
  .bloco-metrica {
      background: var(--secondary-background-color);
      border: var(--as-borda);
      border-radius: var(--as-raio);
      padding: clamp(10px, 2.2vw, 16px);
      height: 100%;
      min-width: 0;                /* permite encolher dentro do flex */
  }
  .bloco-metrica .rotulo {
      font-size: clamp(.68rem, 1.7vw, .74rem);
      text-transform: uppercase; letter-spacing: .06em;
      opacity: .70; margin-bottom: 6px;
      overflow-wrap: anywhere;
  }
  .bloco-metrica .valor {
      font-size: clamp(1.15rem, 4.2vw, 1.55rem);
      font-weight: 700; line-height: 1.15;
      overflow-wrap: anywhere;
  }
  .bloco-metrica .nota  {
      font-size: clamp(.72rem, 1.9vw, .78rem); opacity: .72; margin-top: 4px;
  }

  /* ===================== etiquetas ===================== */
  .faixa-sev {
      display: inline-block; padding: 3px 10px; border-radius: 999px;
      font-size: clamp(.70rem, 1.8vw, .74rem); font-weight: 700;
      color: #fff; white-space: nowrap;
  }
  .etiqueta {
      display: inline-block; padding: 2px 8px; border-radius: 6px;
      font-size: clamp(.68rem, 1.8vw, .72rem);
      border: 1px solid rgba(128,128,128,.35); opacity: .9;
      margin: 2px 2px 2px 0;
  }
  .etiqueta-fonte {
      font-size: .70rem; padding: 1px 7px; border-radius: 6px;
      border: 1px dashed rgba(128,128,128,.45); opacity: .85;
      white-space: nowrap;
  }

  /* ===================== cartão de mensagem ===================== */
  .cartao-msg {
      border: var(--as-borda);
      border-left-width: 5px;
      border-radius: 10px;
      padding: clamp(11px, 2.4vw, 16px);
      margin-bottom: 12px;
      background: var(--secondary-background-color);
  }
  .cartao-msg .cabecalho {
      display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
      font-size: clamp(.74rem, 1.9vw, .8rem); opacity: .85; margin-bottom: 8px;
  }
  .cartao-msg pre {
      white-space: pre-wrap; word-wrap: break-word;
      font-size: clamp(.82rem, 2.3vw, .88rem);
      margin: 0; font-family: inherit; line-height: 1.55;
  }

  .rodape-fonte { font-size: clamp(.72rem, 1.9vw, .76rem); opacity: .65; margin-top: 6px; }

  /* ===================== barra de filtros ===================== */
  .barra-filtros {
      border: var(--as-borda); border-radius: var(--as-raio);
      padding: 10px 14px; margin-bottom: 10px;
      background: var(--secondary-background-color);
  }
  .resumo-filtros {
      display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
      font-size: clamp(.72rem, 1.9vw, .78rem); opacity: .9;
  }

  /* ===================== Streamlit: densidade e toque ===================== */
  div[data-testid="stMetricValue"] { font-size: clamp(1.1rem, 4vw, 1.5rem); }
  section[data-testid="stSidebar"] { min-width: 300px; }

  /* Alvo de toque confortável em botões, abas e seleções */
  .stButton > button,
  .stDownloadButton > button,
  div[data-baseweb="select"] > div,
  div[data-baseweb="tab"] {
      min-height: var(--as-toque);
  }
  .stButton > button, .stDownloadButton > button {
      border-radius: 10px;
  }

  /* Tabelas e gráficos largos rolam no próprio quadro, não na página */
  div[data-testid="stDataFrame"],
  div[data-testid="stTable"],
  .rolagem-lateral {
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      max-width: 100%;
  }

  /* Abas: viram rolagem horizontal em vez de quebrar o cabeçalho */
  div[data-baseweb="tab-list"] {
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: thin;
  }

  /* Foco visível — navegação por teclado e leitores de tela */
  .stButton > button:focus-visible,
  .stDownloadButton > button:focus-visible,
  a:focus-visible,
  div[data-baseweb="select"]:focus-within {
      outline: 3px solid rgba(37, 99, 235, .65);
      outline-offset: 2px;
  }

  /* ===================== tablet (<= 1024px) ===================== */
  @media (max-width: 1024px) {
      section.main > div.block-container {
          padding-left: 1.1rem; padding-right: 1.1rem; padding-top: 2.6rem;
      }
      section[data-testid="stSidebar"] { min-width: 260px; }
  }

  /* ===================== celular (<= 640px) ===================== */
  @media (max-width: 640px) {
      /* Colunas empilham em vez de espremer: três métricas de 90px de
         largura não informam nada. */
      div[data-testid="stHorizontalBlock"] {
          flex-direction: column !important;
          gap: var(--as-gap);
      }
      div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
          width: 100% !important;
          flex: 1 1 100% !important;
          min-width: 0 !important;
      }
      section.main > div.block-container {
          padding-left: .75rem; padding-right: .75rem;
          padding-top: 2.2rem; padding-bottom: 3rem;
      }
      h1 { font-size: 1.45rem !important; line-height: 1.25; }
      h2 { font-size: 1.18rem !important; }
      h3 { font-size: 1.02rem !important; }

      /* Um botão de largura total é muito mais fácil de acertar com o polegar */
      .stButton > button, .stDownloadButton > button { width: 100%; }

      /* Legendas do Plotly consomem metade da tela do celular */
      .js-plotly-plot .legend { display: none; }

      /* Só o essencial da tabela cabe: o resto rola */
      div[data-testid="stDataFrame"] { font-size: .82rem; }

      .somente-desktop { display: none !important; }
  }

  @media (min-width: 641px) {
      .somente-celular { display: none !important; }
  }

  /* ===================== impressão ===================== */
  @media print {
      section[data-testid="stSidebar"], .stButton, .stDownloadButton { display: none !important; }
      .cartao-msg, .bloco-metrica { break-inside: avoid; }
  }

  /* ===================== movimento reduzido ===================== */
  @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
          animation-duration: .001ms !important;
          transition-duration: .001ms !important;
      }
  }
</style>
"""


def cor_severidade(sev: str) -> str:
    return CORES_SEVERIDADE.get(str(sev).lower(), CINZA)


def cor_evento(evento: str) -> str:
    return CORES_EVENTO.get(str(evento).lower(), CINZA)


def rgb_severidade(sev: str, alpha: int = 190) -> list[int]:
    return RGB_SEVERIDADE.get(str(sev).lower(), [100, 116, 139]) + [alpha]


def faixa(sev: str) -> str:
    """HTML de uma etiqueta colorida de severidade."""
    rotulo = ROTULO_SEVERIDADE.get(str(sev).lower(), str(sev))
    return (
        f'<span class="faixa-sev" style="background:{cor_severidade(sev)}">'
        f"{ICONES_SEVERIDADE.get(str(sev).lower(), '')} {rotulo}</span>"
    )
