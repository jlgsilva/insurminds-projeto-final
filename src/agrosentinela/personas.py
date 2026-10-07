"""
Personas — público-alvo da comunicação proativa.

O Desafio 5 pede "mensagens personalizadas para diferentes perfis de
segurados". O AgroSentinela vai além e modela **dezesseis personas**,
organizadas em cinco setores, que compõem a cadeia do crédito rural e do
Proagro — do produtor familiar ao atuário de resseguro, passando pelo
extensionista MEI que atende trinta propriedades com um celular na mão.

Cada persona declara:

* canal preferencial e janela de contato;
* nível de letramento técnico e financeiro;
* decisão que a mensagem precisa habilitar (o "call to action");
* limites de tamanho por canal;
* gatilho de severidade mínima (evita fadiga de alerta).

As personas são derivadas de atributos reais dos microdados do Sicor:

    CD_CATEG_EMITENTE  -> produtor individual / cooperativa / condomínio
    CD_PROGRAMA        -> Pronaf (familiar), Pronamp (médio), demais (empresarial)
    CD_TIPO_SEGURO     -> Proagro / Proagro Mais / seguro privado / sem cobertura
    CNPJ_IF            -> instituição financeira (persona bancária)

As demais personas não vêm da operação: são profissionais e instituições
que consomem o resultado agregado — e recebem boletins consolidados, não
mensagens por operação.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Canal = Literal["whatsapp", "sms", "email", "push", "painel", "voz"]

# Limite prático de caracteres por canal (usado como restrição dura no prompt).
LIMITE_CANAL: dict[str, int] = {
    "sms": 320,
    "whatsapp": 700,
    "push": 180,
    "email": 2200,
    "painel": 1600,
    "voz": 550,
}

SEVERIDADES = ("informativo", "atencao", "alerta", "critico")
PESO_SEVERIDADE: dict[str, int] = {
    "informativo": 1,
    "atencao": 2,
    "alerta": 3,
    "critico": 4,
}


@dataclass(frozen=True)
class Persona:
    """Perfil de destinatário da comunicação proativa."""

    codigo: str
    nome: str
    descricao: str
    papel_na_cadeia: str
    canais: tuple[str, ...]
    canal_padrao: str
    tom: str
    letramento_tecnico: Literal["baixo", "medio", "alto"]
    decisao_alvo: str
    severidade_minima: str = "atencao"
    janela_contato: str = "07h-20h"
    prioriza_valor_financeiro: bool = False
    aceita_dado_agronomico: bool = True
    agrega_por: Literal["operacao", "municipio", "carteira", "uf"] = "operacao"
    exemplos_necessidade: tuple[str, ...] = field(default_factory=tuple)

    @property
    def limite_caracteres(self) -> int:
        return LIMITE_CANAL.get(self.canal_padrao, 900)


PERSONAS: tuple[Persona, ...] = (
    Persona(
        codigo="produtor_familiar",
        nome="Produtor Rural Familiar (Pronaf)",
        descricao=(
            "Agricultor familiar com operação de custeio de pequeno porte, "
            "geralmente enquadrada no Pronaf e coberta pelo Proagro. "
            "Acessa a informação pelo celular, frequentemente com conexão "
            "instável."
        ),
        papel_na_cadeia="Segurado / mutuário",
        canais=("whatsapp", "sms", "voz"),
        canal_padrao="whatsapp",
        tom="Muito simples, direto, acolhedor, sem jargão. Frases curtas.",
        letramento_tecnico="baixo",
        decisao_alvo=(
            "Tomar uma ação prática de campo nas próximas 72 horas e saber "
            "que existe cobertura do Proagro caso haja perda."
        ),
        severidade_minima="atencao",
        janela_contato="06h-19h",
        prioriza_valor_financeiro=False,
        agrega_por="operacao",
        exemplos_necessidade=(
            "O que eu faço na minha lavoura hoje?",
            "Se perder, eu tenho direito a alguma coisa?",
            "Com quem eu falo?",
        ),
    ),
    Persona(
        codigo="produtor_empresarial",
        nome="Produtor Empresarial / Médio (Pronamp e demais)",
        descricao=(
            "Produtor de médio e grande porte, com múltiplas operações, "
            "área financiada relevante e uso de seguro privado e/ou Proagro. "
            "Decide com base em número."
        ),
        papel_na_cadeia="Segurado / mutuário",
        canais=("email", "whatsapp", "painel"),
        canal_padrao="email",
        tom="Objetivo, técnico-executivo, orientado a números e prazos.",
        letramento_tecnico="alto",
        decisao_alvo=(
            "Priorizar manejo/colheita, acionar assistência técnica e avaliar "
            "antecipação de comunicação de sinistro."
        ),
        severidade_minima="atencao",
        prioriza_valor_financeiro=True,
        agrega_por="operacao",
        exemplos_necessidade=(
            "Qual o impacto em R$ e em sacas?",
            "Quais talhões priorizar?",
            "Preciso abrir COP agora?",
        ),
    ),
    Persona(
        codigo="cooperativa",
        nome="Cooperativa Agropecuária",
        descricao=(
            "Cooperativa que intermedia crédito e assistência técnica para "
            "dezenas ou centenas de cooperados no mesmo território."
        ),
        papel_na_cadeia="Intermediário / agente de campo",
        canais=("email", "painel", "whatsapp"),
        canal_padrao="email",
        tom="Técnico-operacional, orientado a mobilização de equipe de campo.",
        letramento_tecnico="alto",
        decisao_alvo=(
            "Mobilizar o corpo técnico, priorizar visitas e comunicar cooperados "
            "por microrregião."
        ),
        severidade_minima="atencao",
        prioriza_valor_financeiro=True,
        agrega_por="municipio",
        exemplos_necessidade=(
            "Quantos cooperados estão expostos e onde?",
            "Quantos técnicos preciso deslocar?",
            "Qual a cultura mais crítica desta semana?",
        ),
    ),
    Persona(
        codigo="gerente_credito_rural",
        nome="Gerente / Analista de Crédito Rural (Banco)",
        descricao=(
            "Responsável pela carteira de crédito rural de uma agência ou "
            "regional. Precisa antecipar inadimplência, prorrogação e provisão."
        ),
        papel_na_cadeia="Credor / instituição financeira",
        canais=("email", "painel"),
        canal_padrao="painel",
        tom="Executivo, quantitativo, foco em exposição e risco de carteira.",
        letramento_tecnico="alto",
        decisao_alvo=(
            "Dimensionar exposição em risco, priorizar contatos e preparar "
            "prorrogação/renegociação e provisionamento."
        ),
        severidade_minima="alerta",
        prioriza_valor_financeiro=True,
        aceita_dado_agronomico=False,
        agrega_por="carteira",
        exemplos_necessidade=(
            "Quanto da minha carteira está sob evento climático?",
            "Quais operações contatar primeiro?",
            "Qual a projeção de acionamento de Proagro?",
        ),
    ),
    Persona(
        codigo="subscricao_seguradora",
        nome="Analista de Risco / Subscrição (Seguradora e Proagro)",
        descricao=(
            "Avalia exposição agregada, sinistralidade esperada e necessidade "
            "de acionar perícia. Trabalha com alíquotas e séries históricas."
        ),
        papel_na_cadeia="Garantidor do risco",
        canais=("email", "painel"),
        canal_padrao="painel",
        tom="Atuarial, preciso, com séries históricas e intervalos de incerteza.",
        letramento_tecnico="alto",
        decisao_alvo=(
            "Estimar sinistralidade incremental, reservar capacidade de perícia "
            "e revisar apetite por município/cultura."
        ),
        severidade_minima="alerta",
        prioriza_valor_financeiro=True,
        agrega_por="uf",
        exemplos_necessidade=(
            "Qual o histórico de COP/RCP deste município para este evento?",
            "Quantas perícias devo provisionar?",
            "A alíquota vigente cobre este risco?",
        ),
    ),
    Persona(
        codigo="assistencia_tecnica",
        nome="Assistência Técnica e Extensão Rural (ATER / agrônomo)",
        descricao=(
            "Agrônomo ou técnico de campo que traduz o alerta em recomendação "
            "agronômica por cultura e fase fenológica."
        ),
        papel_na_cadeia="Mitigação de risco em campo",
        canais=("whatsapp", "email", "painel"),
        canal_padrao="whatsapp",
        tom="Agronômico e prescritivo, com janelas operacionais claras.",
        letramento_tecnico="alto",
        decisao_alvo=(
            "Emitir recomendação de manejo por cultura/fase e organizar roteiro "
            "de visitas."
        ),
        severidade_minima="atencao",
        agrega_por="municipio",
        exemplos_necessidade=(
            "Qual manejo recomendar nesta fase?",
            "Qual a janela segura para aplicação?",
            "Onde ir primeiro amanhã?",
        ),
    ),
    Persona(
        codigo="corretor_associacao",
        nome="Corretor de Seguros / Sindicato / Associação",
        descricao=(
            "Ponto de contato comercial e institucional com o produtor. "
            "Precisa de lista de contatos priorizada e script pronto."
        ),
        papel_na_cadeia="Relacionamento e distribuição",
        canais=("whatsapp", "email", "painel"),
        canal_padrao="email",
        tom="Comercial-consultivo, empático, com próximo passo explícito.",
        letramento_tecnico="medio",
        decisao_alvo=(
            "Contatar produtores expostos, orientar sobre cobertura e registrar "
            "o atendimento."
        ),
        severidade_minima="atencao",
        agrega_por="municipio",
        exemplos_necessidade=(
            "Quem eu ligo hoje?",
            "O que eu falo?",
            "Quem está sem cobertura e pode contratar?",
        ),
    ),
    Persona(
        codigo="gestor_politica_publica",
        nome="Gestor de Política Agrícola / Órgão Regulador",
        descricao=(
            "Acompanha o desempenho regional do crédito rural e do Proagro e "
            "antecipa pressão sobre o fundo garantidor."
        ),
        papel_na_cadeia="Política pública e supervisão",
        canais=("painel", "email"),
        canal_padrao="painel",
        tom="Analítico e institucional, com visão regional agregada.",
        letramento_tecnico="alto",
        decisao_alvo=(
            "Identificar municípios críticos, antecipar demanda por cobertura e "
            "subsidiar medidas de política agrícola."
        ),
        severidade_minima="alerta",
        prioriza_valor_financeiro=True,
        aceita_dado_agronomico=False,
        agrega_por="uf",
        exemplos_necessidade=(
            "Quais regiões concentram risco nesta safra?",
            "Qual o valor potencialmente acionável do Proagro?",
            "Onde a cobertura é mais rala?",
        ),
    ),

    # ======================================================================
    # Profissionais autônomos e MEI que vivem do tema
    # ======================================================================
    Persona(
        codigo="mei_extensionista",
        nome="Extensionista Rural Autônomo (MEI)",
        descricao=(
            "Profissional autônomo, quase sempre MEI, que presta assistência "
            "técnica a dezenas de produtores em um raio de poucos municípios. "
            "Não tem estrutura de análise de dados nem acesso a sistema de "
            "seguradora — trabalha com celular em campo e planilha à noite."
        ),
        papel_na_cadeia="Assistência técnica independente",
        canais=("whatsapp", "email", "painel"),
        canal_padrao="whatsapp",
        tom=(
            "Técnico e prático, de colega para colega. Objetivo, sem "
            "formalidade corporativa."
        ),
        letramento_tecnico="alto",
        decisao_alvo=(
            "Montar o roteiro de visitas da semana e saber que recomendação "
            "levar para cada propriedade."
        ),
        severidade_minima="atencao",
        janela_contato="06h-20h",
        agrega_por="municipio",
        exemplos_necessidade=(
            "Em quais propriedades eu preciso estar esta semana?",
            "Que recomendação técnica eu levo?",
            "Como eu justifico a visita para o produtor?",
        ),
    ),
    Persona(
        codigo="assessor_rural",
        nome="Assessor Rural / Consultor Independente",
        descricao=(
            "Consultor que assessora produtores e cooperativas em gestão, "
            "crédito e risco. Vende análise, não insumo. Precisa de dado "
            "defensável para sustentar a recomendação que cobra."
        ),
        papel_na_cadeia="Consultoria e gestão de risco",
        canais=("email", "painel", "whatsapp"),
        canal_padrao="painel",
        tom=(
            "Consultivo e analítico, com números e comparação regional; "
            "linguagem de quem apresenta a um cliente pagante."
        ),
        letramento_tecnico="alto",
        decisao_alvo=(
            "Produzir recomendação fundamentada de manejo de risco e de "
            "cobertura para a carteira de clientes assessorados."
        ),
        severidade_minima="atencao",
        prioriza_valor_financeiro=True,
        agrega_por="municipio",
        exemplos_necessidade=(
            "Como o risco do meu cliente se compara ao da região?",
            "Vale contratar seguro privado além do Proagro?",
            "Que evidência eu levo para a reunião?",
        ),
    ),

    # ======================================================================
    # Setor de seguros — além da subscrição
    # ======================================================================
    Persona(
        codigo="perito_regulador",
        nome="Perito / Regulador de Sinistros (Proagro e seguro rural)",
        descricao=(
            "Faz a verificação em campo que decide o deferimento da cobertura. "
            "Trabalha por demanda e sofre com picos concentrados: quando o "
            "evento é regional, todas as perícias chegam na mesma semana."
        ),
        papel_na_cadeia="Regulação de sinistro",
        canais=("painel", "email", "whatsapp"),
        canal_padrao="painel",
        tom=(
            "Objetivo e probatório, focado em evidência verificável: datas, "
            "indicadores e localização."
        ),
        letramento_tecnico="alto",
        decisao_alvo=(
            "Antecipar o volume e a localização das perícias, montar rota de "
            "campo e chegar com a evidência climática já reunida."
        ),
        severidade_minima="alerta",
        agrega_por="municipio",
        exemplos_necessidade=(
            "Quantas perícias devo esperar e onde?",
            "O evento alegado tem lastro nos dados meteorológicos?",
            "Qual a janela de data do evento nesse município?",
        ),
    ),
    Persona(
        codigo="atuario_precificacao",
        nome="Atuário / Precificação de Seguro Rural",
        descricao=(
            "Calcula prêmio, provisão e necessidade de resseguro. Precisa de "
            "série histórica por município, cultura e evento — exatamente o "
            "que os microdados do Proagro oferecem."
        ),
        papel_na_cadeia="Precificação e resseguro",
        canais=("painel", "email"),
        canal_padrao="painel",
        tom=(
            "Atuarial e quantitativo: frequência, severidade, exposição e "
            "incerteza declarada."
        ),
        letramento_tecnico="alto",
        decisao_alvo=(
            "Revisar taxa por município e cultura, dimensionar provisão e "
            "avaliar acionamento do contrato de resseguro."
        ),
        severidade_minima="alerta",
        prioriza_valor_financeiro=True,
        aceita_dado_agronomico=False,
        agrega_por="uf",
        exemplos_necessidade=(
            "Qual a frequência e a severidade histórica deste evento aqui?",
            "A exposição acumulada ameaça o limite de retenção?",
            "A taxa vigente está aderente ao risco observado?",
        ),
    ),
    Persona(
        codigo="comercial_seguradora",
        nome="Comercial / Produto de Seguro Rural (Seguradora)",
        descricao=(
            "Responsável por crescimento de carteira e desenho de produto. A "
            "informação mais valiosa para esta pessoa é onde existe lavoura "
            "financiada **sem cobertura** — demanda latente, mapeada."
        ),
        papel_na_cadeia="Distribuição e produto",
        canais=("painel", "email"),
        canal_padrao="painel",
        tom=(
            "Comercial e orientado a oportunidade, com tamanho de mercado e "
            "priorização geográfica."
        ),
        letramento_tecnico="medio",
        decisao_alvo=(
            "Priorizar praças e culturas para expansão e ajustar o desenho do "
            "produto ao risco real da região."
        ),
        severidade_minima="alerta",
        prioriza_valor_financeiro=True,
        aceita_dado_agronomico=False,
        agrega_por="uf",
        exemplos_necessidade=(
            "Onde há lavoura financiada sem cobertura?",
            "Qual o tamanho dessa demanda em R$ e em hectares?",
            "Que cultura e que praça priorizar no próximo trimestre?",
        ),
    ),

    # ======================================================================
    # Cadeia produtiva e mercado
    # ======================================================================
    Persona(
        codigo="revenda_insumos",
        nome="Revenda de Insumos / Agroindústria",
        descricao=(
            "Vende insumo a prazo e, com isso, assume risco de crédito do "
            "produtor. Um evento climático regional vira inadimplência na "
            "revenda antes de virar sinistro na seguradora."
        ),
        papel_na_cadeia="Fornecimento e crédito comercial",
        canais=("email", "painel"),
        canal_padrao="email",
        tom="Comercial-operacional, com foco em recebíveis e logística.",
        letramento_tecnico="medio",
        decisao_alvo=(
            "Ajustar concessão de prazo, antecipar renegociação e planejar "
            "estoque de insumos de emergência."
        ),
        severidade_minima="alerta",
        prioriza_valor_financeiro=True,
        agrega_por="municipio",
        exemplos_necessidade=(
            "Quais clientes podem atrasar o pagamento?",
            "Devo antecipar estoque de defensivo ou de semente?",
            "Onde concentro a equipe de campo?",
        ),
    ),
    Persona(
        codigo="trading_originacao",
        nome="Trading / Originação e Armazenagem",
        descricao=(
            "Compra safra antecipada e opera armazéns. Um evento em fase de "
            "enchimento ou colheita altera volume originado, qualidade do grão "
            "e necessidade de secagem."
        ),
        papel_na_cadeia="Originação e logística",
        canais=("painel", "email"),
        canal_padrao="painel",
        tom="Mercado: volume, qualidade, prazo e logística.",
        letramento_tecnico="alto",
        decisao_alvo=(
            "Rever estimativa de originação por região e preparar capacidade "
            "de secagem e armazenagem."
        ),
        severidade_minima="alerta",
        prioriza_valor_financeiro=True,
        agrega_por="uf",
        exemplos_necessidade=(
            "Quanto volume está sob risco na minha área de originação?",
            "Vou receber grão úmido? Quanto de secagem preciso?",
            "Devo rever os contratos de entrega futura?",
        ),
    ),
    Persona(
        codigo="pesquisa_imprensa",
        nome="Pesquisa, Ensino e Análise de Mercado",
        descricao=(
            "Pesquisador, professor, analista de mercado ou jornalista "
            "especializado. Usa os mesmos dados públicos para produzir "
            "análise, aula ou reportagem — e precisa de procedência clara."
        ),
        papel_na_cadeia="Conhecimento e transparência",
        canais=("painel", "email"),
        canal_padrao="painel",
        tom=(
            "Expositivo e rigoroso, com fonte, método e limitação declarados."
        ),
        letramento_tecnico="alto",
        decisao_alvo=(
            "Produzir análise fundamentada sobre exposição climática do "
            "crédito rural, com dado rastreável até a fonte oficial."
        ),
        severidade_minima="informativo",
        agrega_por="uf",
        exemplos_necessidade=(
            "De onde vem cada número?",
            "Como isso se compara com safras anteriores?",
            "Qual a limitação metodológica desta leitura?",
        ),
    ),
)

PERSONAS_POR_CODIGO: dict[str, Persona] = {p.codigo: p for p in PERSONAS}


def get_persona(codigo: str) -> Persona:
    """Retorna a persona pelo código, com fallback seguro."""
    return PERSONAS_POR_CODIGO.get(codigo, PERSONAS_POR_CODIGO["produtor_familiar"])


def personas_por_papel() -> dict[str, list[Persona]]:
    agrupado: dict[str, list[Persona]] = {}
    for p in PERSONAS:
        agrupado.setdefault(p.papel_na_cadeia, []).append(p)
    return agrupado


# --------------------------------------------------------------------------
# Derivação de persona a partir dos atributos reais do Sicor
# --------------------------------------------------------------------------

# Programas Pronaf no Sicor começam por "0001".."0007" na maioria das linhas;
# usamos o rótulo textual como sinal principal e o código como reforço.
_PALAVRAS_PRONAF = ("pronaf", "agricultura familiar", "familiar")
_PALAVRAS_PRONAMP = ("pronamp", "médio produtor", "medio produtor")
_PALAVRAS_COOP = ("cooperativ", "condomínio", "condominio", "associaç", "associac")


def inferir_persona_do_mutuario(
    *,
    programa_descricao: str | None = None,
    categoria_emitente: str | None = None,
    valor_credito: float | None = None,
    area_financiada: float | None = None,
) -> str:
    """
    Infere o código da persona de um **mutuário** a partir dos campos do Sicor.

    Regras (documentadas em docs/personas.md):

    1. Categoria de emitente indicando cooperativa/condomínio -> ``cooperativa``
    2. Programa Pronaf -> ``produtor_familiar``
    3. Programa Pronamp -> ``produtor_empresarial``
    4. Sem programa identificável: usa porte (valor e área) como desempate.
    """
    cat = (categoria_emitente or "").lower()
    prog = (programa_descricao or "").lower()

    if any(p in cat for p in _PALAVRAS_COOP) or any(p in prog for p in _PALAVRAS_COOP):
        return "cooperativa"
    if any(p in prog for p in _PALAVRAS_PRONAF):
        return "produtor_familiar"
    if any(p in prog for p in _PALAVRAS_PRONAMP):
        return "produtor_empresarial"

    # Desempate por porte — limiares alinhados ao Manual de Crédito Rural
    # (Pronaf: renda bruta anual até R$ 500 mil; operações tipicamente < R$ 250 mil).
    if valor_credito is not None and valor_credito > 0:
        if valor_credito <= 250_000:
            return "produtor_familiar"
        return "produtor_empresarial"
    if area_financiada is not None and area_financiada > 0:
        return "produtor_familiar" if area_financiada <= 60 else "produtor_empresarial"
    return "produtor_empresarial"


# Personas que recebem comunicação **individual** (por operação/mutuário)
PERSONAS_MUTUARIO = ("produtor_familiar", "produtor_empresarial", "cooperativa")

# Personas que recebem comunicação **agregada** (boletim consolidado)
PERSONAS_INSTITUCIONAIS = (
    "gerente_credito_rural",
    "subscricao_seguradora",
    "assistencia_tecnica",
    "corretor_associacao",
    "gestor_politica_publica",
    "mei_extensionista",
    "assessor_rural",
    "perito_regulador",
    "atuario_precificacao",
    "comercial_seguradora",
    "revenda_insumos",
    "trading_originacao",
    "pesquisa_imprensa",
)

# Agrupamento por setor — usado na interface e na documentação
SETORES: dict[str, tuple[str, ...]] = {
    "Produção rural": ("produtor_familiar", "produtor_empresarial", "cooperativa"),
    "Setor de seguros": (
        "subscricao_seguradora", "perito_regulador", "atuario_precificacao",
        "comercial_seguradora", "corretor_associacao",
    ),
    "Crédito e política pública": ("gerente_credito_rural", "gestor_politica_publica"),
    "Assistência técnica e consultoria": (
        "assistencia_tecnica", "mei_extensionista", "assessor_rural",
    ),
    "Cadeia produtiva e mercado": (
        "revenda_insumos", "trading_originacao", "pesquisa_imprensa",
    ),
}


def personas_do_setor(setor: str) -> list[Persona]:
    return [PERSONAS_POR_CODIGO[c] for c in SETORES.get(setor, ()) if c in PERSONAS_POR_CODIGO]


def setor_da_persona(codigo: str) -> str:
    for setor, membros in SETORES.items():
        if codigo in membros:
            return setor
    return "Outros"
