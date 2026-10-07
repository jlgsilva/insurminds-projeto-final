"""
Catálogo de fontes de dados **externas, gratuitas, públicas e livres**.

Regra de ouro deste projeto (definida pelo autor): *só entra o que for
gratuito e público, sem contrato, sem cartão de crédito e sem cota paga*.
Cada fonte abaixo foi registrada com a licença e a condição de uso que a
própria instituição publica, para que o avaliador — e qualquer pessoa que
reaproveite o código — saiba exatamente o que pode fazer com o dado.

Por que dados externos, se o Sicor já é riquíssimo?

O Sicor conta o que foi **financiado** e o que foi **sinistrado**. Ele não
conta o que está acontecendo **agora** no campo, nem o que existe **fora**
do crédito rural. Três lacunas concretas:

* **Tempo presente e futuro** — o Sicor é retrospectivo. Alerta útil exige
  previsão (Open-Meteo), série climática longa (NASA POWER, INMET) e
  monitoramento em tempo quase real (CEMADEN, INPE, Agritempo).
* **Denominador** — "1.200 operações de soja em Sorriso" só vira risco
  quando comparado à área total de soja do município (IBGE/PAM) e ao uso do
  solo (MapBiomas).
* **O outro lado da cobertura** — o Proagro é metade do mercado. A outra
  metade é o seguro rural privado subvencionado (PSR/MAPA) e o mercado
  supervisionado pela SUSEP. Sem eles não se sabe se um município está
  *descoberto* ou apenas *coberto por outro instrumento*.

Campos do registro:

* ``chave`` / ``nome`` / ``orgao``
* ``categoria``     — clima | monitoramento | seguro | produção | território | hídrico
* ``licenca``       — licença ou condição de uso publicada
* ``exige_chave``   — se pede cadastro/API key (preferimos as que não pedem)
* ``granularidade`` — a que nível o dado existe
* ``chave_juncao``  — como se liga ao Sicor
* ``papel``         — o que muda no AgroSentinela por causa dela
* ``conector``      — módulo em ``agrosentinela.external`` que a consome
* ``fallback``      — o que acontece quando a rede não está disponível
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CAT_CLIMA = "clima"
CAT_MONITOR = "monitoramento"
CAT_SEGURO = "seguro"
CAT_PRODUCAO = "produção"
CAT_TERRITORIO = "território"
CAT_HIDRICO = "hídrico"

CATEGORIAS = (CAT_CLIMA, CAT_MONITOR, CAT_SEGURO, CAT_PRODUCAO,
              CAT_TERRITORIO, CAT_HIDRICO)


@dataclass(frozen=True)
class FonteExterna:
    chave: str
    nome: str
    orgao: str
    categoria: str
    url_portal: str
    licenca: str
    papel: str
    chave_juncao: str
    granularidade: str
    atualizacao: str
    url_api: str = ""
    exige_chave: bool = False
    gratuita: bool = True
    formato: str = "JSON"
    conector: str = ""
    fallback: str = "tabela embutida (normais e médias públicas)"
    usado_agora: bool = True
    nota: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_row(self) -> dict[str, Any]:
        return {
            "fonte": self.nome,
            "órgão": self.orgao,
            "categoria": self.categoria,
            "licença": self.licenca,
            "exige cadastro": "sim" if self.exige_chave else "não",
            "granularidade": self.granularidade,
            "liga ao Sicor por": self.chave_juncao,
            "papel na solução": self.papel,
            "portal": self.url_portal,
        }


FONTES: tuple[FonteExterna, ...] = (
    # ------------------------------------------------------------- clima
    FonteExterna(
        "open_meteo", "Open-Meteo — previsão e reanálise ERA5",
        "Open-Meteo (open data, ECMWF/DWD/NOAA)", CAT_CLIMA,
        "https://open-meteo.com",
        "CC BY 4.0 — uso não comercial livre e sem chave",
        papel="Previsão de 16 dias e histórico diário no centroide da gleba "
              "ou do município. É a fonte que dispara o alerta.",
        chave_juncao="lat/lon do centroide (célula de grade ~11 km)",
        granularidade="ponto × dia (e hora, para CAPE)",
        atualizacao="horária",
        url_api="https://api.open-meteo.com/v1/forecast",
        conector="agrosentinela.weather.open_meteo",
        fallback="provedor sintético determinístico, rotulado na interface",
        tags=("previsão", "alerta", "núcleo"),
    ),
    FonteExterna(
        "nasa_power", "NASA POWER — agroclimatologia",
        "NASA Langley Research Center", CAT_CLIMA,
        "https://power.larc.nasa.gov",
        "Domínio público (NASA open data) — sem chave",
        papel="Normais climáticas de 1981 em diante no mesmo ponto. É o que "
              "transforma '80 mm de chuva' em '80 mm, o triplo da média "
              "histórica desta semana aqui' — o número que dá contexto à "
              "mensagem e evita alarme falso.",
        chave_juncao="lat/lon do centroide",
        granularidade="ponto × dia (grade 0,5°)",
        atualizacao="diária (defasagem de ~2 dias)",
        url_api="https://power.larc.nasa.gov/api/temporal/daily/point",
        conector="agrosentinela.external.nasa_power",
        fallback="normais climatológicas embutidas por região do país",
        tags=("normais", "anomalia"),
    ),
    FonteExterna(
        "inmet", "INMET — estações automáticas e BDMEP",
        "Instituto Nacional de Meteorologia", CAT_CLIMA,
        "https://portal.inmet.gov.br/dadoshistoricos",
        "Dados abertos (Lei 12.527/2011) — API pública sem chave",
        papel="Observação de superfície em estação real, usada para conferir "
              "a previsão (skill check) e como evidência em perícia.",
        chave_juncao="estação mais próxima do centroide (raio configurável)",
        granularidade="estação × hora/dia",
        atualizacao="horária",
        url_api="https://apitempo.inmet.gov.br",
        conector="agrosentinela.external.inmet",
        fallback="lista embutida de estações principais, sem série",
        tags=("observação", "validação"),
    ),
    FonteExterna(
        "agritempo", "Agritempo — monitoramento agrometeorológico",
        "Embrapa Informática Agropecuária / Unicamp", CAT_CLIMA,
        "https://www.agritempo.gov.br",
        "Dados abertos governamentais",
        papel="Boletins agrometeorológicos e balanço hídrico por município, "
              "em linguagem já agronômica.",
        chave_juncao="código IBGE",
        granularidade="município × decêndio",
        atualizacao="diária/decendial",
        conector="agrosentinela.external.agritempo",
        usado_agora=False,
        nota="Mapeado e pronto para ativação; hoje o balanço hídrico é "
             "calculado internamente a partir de ET0 e precipitação.",
        tags=("balanço hídrico",),
    ),

    # ------------------------------------------------------ monitoramento
    FonteExterna(
        "cemaden", "CEMADEN — pluviômetros automáticos e alertas",
        "Centro Nacional de Monitoramento e Alertas de Desastres Naturais",
        CAT_MONITOR,
        "https://www.cemaden.gov.br",
        "Dados abertos (Ministério da Ciência e Tecnologia)",
        papel="Chuva acumulada medida em solo e alertas oficiais de desastre. "
              "Quando o CEMADEN já emitiu alerta para o município, o "
              "AgroSentinela **cita o alerta oficial** em vez de criar um "
              "aviso concorrente — evita ruído e aumenta a credibilidade.",
        chave_juncao="código IBGE do município",
        granularidade="estação/município × hora",
        atualizacao="horária",
        url_api="http://sjc.salvar.cemaden.gov.br/resources/dados",
        conector="agrosentinela.external.cemaden",
        fallback="sem alerta oficial (campo marcado como indisponível)",
        tags=("alerta oficial", "chuva"),
    ),
    FonteExterna(
        "queimadas_inpe", "Programa Queimadas — focos de calor",
        "INPE", CAT_MONITOR,
        "https://terrabrasilis.dpi.inpe.br/queimadas/portal/",
        "Dados abertos — CSV diário de acesso livre",
        papel="Focos de calor por município nas últimas 24h/7d/30d. Fogo é "
              "evento coberto pelo Proagro e é o risco mais subnotificado "
              "em pastagem e cana. Também identifica queima de resteva "
              "vizinha que ameaça a lavoura segurada.",
        chave_juncao="código IBGE / ponto (lat,lon) dentro da gleba",
        granularidade="foco (ponto) × satélite × hora",
        atualizacao="a cada 3 horas",
        url_api="https://firms.modaps.eosdis.nasa.gov/data/active_fire",
        formato="CSV",
        conector="agrosentinela.external.queimadas",
        fallback="contagem zero, campo marcado como indisponível",
        tags=("fogo", "evento proagro"),
    ),

    # -------------------------------------------------------------- seguro
    FonteExterna(
        "psr_mapa", "Atlas do Seguro Rural / SISSER — apólices do PSR",
        "Ministério da Agricultura e Pecuária (MAPA)", CAT_SEGURO,
        "https://indicadores.agricultura.gov.br/atlasdosegurorural/",
        "Dados abertos — dados.gov.br, uso livre com citação",
        papel="Apólices subvencionadas, área segurada, prêmio, taxa média e "
              "indenizações por município × cultura × ano. É o **outro lado "
              "da cobertura**: permite dizer se um município está de fato "
              "descoberto ou apenas protegido por seguro privado em vez do "
              "Proagro — e é a base do argumento comercial das personas de "
              "seguradora e corretora.",
        chave_juncao="código IBGE + cultura + ano-safra",
        granularidade="município × cultura × ano",
        atualizacao="anual (com prévias)",
        formato="CSV",
        conector="agrosentinela.external.psr_mapa",
        fallback="agregados embutidos por UF × cultura",
        tags=("seguro rural", "PSR", "público de seguros"),
    ),
    FonteExterna(
        "susep", "SUSEP — dados abertos do mercado segurador",
        "Superintendência de Seguros Privados", CAT_SEGURO,
        "https://www2.susep.gov.br/menuestatistica/SES/principal.aspx",
        "Dados abertos — uso livre",
        papel="Prêmios emitidos e sinistros retidos do ramo rural por "
              "empresa e UF. Dá a sinistralidade de mercado com que o "
              "atuário e a área de subscrição comparam a carteira própria.",
        chave_juncao="UF + ramo (agrupamento 'rural') + mês",
        granularidade="empresa × ramo × UF × mês",
        atualizacao="mensal",
        formato="CSV/ZIP",
        conector="agrosentinela.external.susep",
        fallback="série anual agregada embutida",
        usado_agora=False,
        nota="Ativado na página de seguros; opcional no fluxo de alerta.",
        tags=("seguro", "atuarial"),
    ),

    # ------------------------------------------------------------ produção
    FonteExterna(
        "ibge_pam", "IBGE SIDRA — Produção Agrícola Municipal (PAM)",
        "Instituto Brasileiro de Geografia e Estatística", CAT_PRODUCAO,
        "https://sidra.ibge.gov.br/tabela/5457",
        "Dados abertos — API SIDRA pública, sem chave",
        papel="Área plantada, quantidade produzida e rendimento médio por "
              "município e cultura. É o **denominador** de tudo: converte "
              "'área financiada' em 'percentual da lavoura do município', "
              "e permite estimar a perda em toneladas e em reais.",
        chave_juncao="código IBGE + produto (mapeado para a cultura interna)",
        granularidade="município × cultura × ano",
        atualizacao="anual",
        url_api="https://apisidra.ibge.gov.br/values",
        conector="agrosentinela.external.ibge_sidra",
        fallback="rendimentos médios por UF × cultura embutidos",
        tags=("denominador", "produtividade"),
    ),
    FonteExterna(
        "ibge_ppm", "IBGE SIDRA — Pesquisa da Pecuária Municipal (PPM)",
        "IBGE", CAT_PRODUCAO,
        "https://sidra.ibge.gov.br/tabela/3939",
        "Dados abertos — API SIDRA pública",
        papel="Rebanho por município e espécie — denominador das operações "
              "de bovinocultura, que hoje são um ponto cego do alerta "
              "climático agrícola.",
        chave_juncao="código IBGE + espécie",
        granularidade="município × espécie × ano",
        atualizacao="anual",
        url_api="https://apisidra.ibge.gov.br/values",
        conector="agrosentinela.external.ibge_sidra",
        tags=("pecuária",),
    ),
    FonteExterna(
        "conab", "CONAB — safras, custos e preços mínimos",
        "Companhia Nacional de Abastecimento", CAT_PRODUCAO,
        "https://portaldeinformacoes.conab.gov.br",
        "Dados abertos — uso livre com citação",
        papel="Preço mínimo e preço de mercado por produto e UF, e custos de "
              "produção. Converte perda física em perda financeira usando "
              "preço oficial, não estimativa — diferença que importa ao "
              "banco e à seguradora.",
        chave_juncao="UF + produto + safra",
        granularidade="UF × produto × safra/mês",
        atualizacao="mensal",
        formato="CSV",
        conector="agrosentinela.external.conab",
        fallback="tabela de preços de referência embutida por produto",
        tags=("preço", "perda financeira"),
    ),

    # ----------------------------------------------------------- território
    FonteExterna(
        "ibge_malhas", "IBGE — malhas territoriais e localidades",
        "IBGE", CAT_TERRITORIO,
        "https://servicodados.ibge.gov.br/api/docs/malhas",
        "Dados abertos — API de serviços pública, sem chave",
        papel="Geometria e centroide oficial de cada município — base de "
              "todos os mapas e o ponto usado quando não há gleba.",
        chave_juncao="código IBGE",
        granularidade="município (polígono)",
        atualizacao="quando há alteração territorial",
        url_api="https://servicodados.ibge.gov.br/api/v3/malhas",
        conector="agrosentinela.external.ibge_malhas",
        fallback="centroides embutidos em data/seed (5.570 municípios)",
        tags=("geo", "núcleo"),
    ),
    FonteExterna(
        "mapbiomas", "MapBiomas — uso e cobertura do solo",
        "Rede MapBiomas", CAT_TERRITORIO,
        "https://brasil.mapbiomas.org/estatisticas/",
        "CC BY-SA 4.0 — uso livre com atribuição",
        papel="Área de lavoura, pastagem e vegetação nativa por município e "
              "ano. Mostra se a expansão do crédito está indo para área já "
              "consolidada ou para fronteira — leitura essencial para "
              "política pública e para subscrição com critério socioambiental.",
        chave_juncao="código IBGE + ano",
        granularidade="município × classe de uso × ano",
        atualizacao="anual",
        formato="CSV/XLSX",
        conector="agrosentinela.external.mapbiomas",
        fallback="participação média de lavoura/pastagem por UF",
        tags=("uso do solo", "ESG"),
    ),
    FonteExterna(
        "zarc", "Zarc — Zoneamento Agrícola de Risco Climático",
        "MAPA / Embrapa (Zarc Plantio Certo)", CAT_TERRITORIO,
        "https://www.gov.br/agricultura/pt-br/assuntos/riscos-seguro/programa-nacional-de-zoneamento-agricola-de-risco-climatico",
        "Dados abertos — portarias e API pública do Plantio Certo",
        papel="Janela de plantio recomendada por município, cultura, tipo de "
              "solo e ciclo, com o nível de risco (20%, 30%, 40%). Duas "
              "aplicações: (a) atenua o escore de quem plantou dentro da "
              "janela; (b) explica ao produtor **por que** o risco daquela "
              "data é maior — argumento que o Sicor sozinho não fornece.",
        chave_juncao="código IBGE + cultura + tipo de solo + ciclo",
        granularidade="município × cultura × solo × decêndio",
        atualizacao="anual (por portaria de safra)",
        conector="agrosentinela.external.zarc",
        fallback="janelas de plantio embutidas por região × cultura "
                 "(as mesmas do catálogo fenológico interno)",
        tags=("risco climático", "janela de plantio"),
    ),

    # -------------------------------------------------------------- hídrico
    FonteExterna(
        "ana_hidroweb", "ANA — HidroWeb / Sala de Situação",
        "Agência Nacional de Águas e Saneamento Básico", CAT_HIDRICO,
        "https://www.snirh.gov.br/hidroweb/",
        "Dados abertos — série histórica pública",
        papel="Nível e vazão de rios e situação de reservatórios. Em "
              "lavoura irrigada, a restrição de outorga chega **antes** da "
              "seca agronômica: é o alerta mais antecipado disponível.",
        chave_juncao="estação da bacia mais próxima do município",
        granularidade="estação × dia",
        atualizacao="diária",
        url_api="https://www.ana.gov.br/hidrowebservice",
        conector="agrosentinela.external.ana",
        fallback="situação hídrica marcada como indisponível",
        usado_agora=False,
        nota="Relevante para as operações irrigadas da carteira (regra R-SEC-02).",
        tags=("irrigação", "outorga"),
    ),
    FonteExterna(
        "monitor_secas", "Monitor de Secas do Brasil",
        "ANA / FUNCEME / INMET e parceiros estaduais", CAT_HIDRICO,
        "https://monitordesecas.ana.gov.br",
        "Dados abertos — mapas mensais públicos",
        papel="Classificação oficial de severidade de seca (S0 a S4) por "
              "município. Quando existe, o AgroSentinela **usa a "
              "classificação oficial** em vez da própria — alinhamento que "
              "importa para laudo de Proagro e para política pública.",
        chave_juncao="código IBGE",
        granularidade="município × mês",
        atualizacao="mensal",
        formato="SHP/GeoJSON",
        conector="agrosentinela.external.monitor_secas",
        fallback="severidade calculada internamente por déficit hídrico",
        tags=("seca", "oficial"),
    ),
)

FONTES_POR_CHAVE: dict[str, FonteExterna] = {f.chave: f for f in FONTES}


# ==========================================================================
# Consultas
# ==========================================================================

def por_categoria(categoria: str) -> list[FonteExterna]:
    return [f for f in FONTES if f.categoria == categoria]


def ativas() -> list[FonteExterna]:
    return [f for f in FONTES if f.usado_agora]


def sem_cadastro() -> list[FonteExterna]:
    return [f for f in FONTES if not f.exige_chave]


def obter(chave: str) -> FonteExterna:
    if chave not in FONTES_POR_CHAVE:
        raise KeyError(f"Fonte externa desconhecida: {chave}")
    return FONTES_POR_CHAVE[chave]


def tabela() -> list[dict[str, Any]]:
    return [f.to_row() for f in FONTES]


def resumo() -> dict[str, Any]:
    return {
        "total": len(FONTES),
        "ativas": len(ativas()),
        "sem_cadastro": len(sem_cadastro()),
        "todas_gratuitas": all(f.gratuita for f in FONTES),
        "por_categoria": {c: len(por_categoria(c)) for c in CATEGORIAS},
    }


def creditos() -> list[str]:
    """Linhas de atribuição exigidas pelas licenças, exibidas no rodapé."""
    return [f"{f.nome} — {f.orgao} ({f.licenca})" for f in FONTES if f.usado_agora]
