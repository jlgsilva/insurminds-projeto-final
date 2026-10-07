"""
Modelo integrado dos microdados do Crédito Rural e do Proagro.

Este módulo responde, de forma executável e auditável, à pergunta central
de quem abre a página do Banco Central pela primeira vez:

    "São 166 arquivos. Como eles se ligam uns aos outros?"

Aqui não há heurística: cada ligação foi conferida contra o *Modelo e
dicionário de dados do Sicor* (``manualDadosSicorCompleto.pdf``) e o
*Modelo e dicionário dos dados complementares* (``manualDadosComplementaresSicor_V2.pdf``).

Três descobertas organizam todo o resto:

1. **A chave universal do Sicor é o par ``(REF_BACEN, NU_ORDEM)``.**
   ``REF_BACEN`` identifica o contrato junto ao Banco Central e ``NU_ORDEM``
   distingue cada empreendimento (gleba/cultura) dentro do mesmo contrato.
   Praticamente todo arquivo de microdado do Sicor carrega esse par — é por
   ele que carteira, Proagro, glebas, saldos e renegociação se encontram.

2. **A operação básica não tem município.**
   ``SICOR_OPERACAO_BASICA_ESTADO_AAAA.gz`` só traz ``CD_ESTADO``. O
   ``CD_IBGE_MUNICIPIO`` mora em ``SICOR_COMPLEMENTO_OPERACAO_BASICA.gz``.
   Sem essa junção **não existe georreferenciamento** — e, portanto, não
   existe alerta climático dirigido.

3. **O Proagro é uma cadeia de três etapas, não uma tabela.**
   COP (pedido de cobertura) → RCP (comprovação de perdas) → Súmula
   (julgamento) → Parcelas (pagamento). Medir sinistralidade olhando só o
   COP superestima; olhar só o RCP ignora o que foi negado. O AgroSentinela
   percorre a cadeia inteira e expõe as duas taxas separadamente.

O grafo declarado abaixo é consumido por:

* ``etl/`` — para saber a ordem das junções e as chaves de cada passo;
* a página *Documentação* do aplicativo — que o desenha em Mermaid;
* ``scripts/gerar_relatorio.py`` — que publica a tabela de ligações;
* os testes — que verificam que o grafo é conexo e que toda chave existe.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

# ==========================================================================
# Chaves recorrentes
# ==========================================================================

CHAVE_OPERACAO = ("REF_BACEN", "NU_ORDEM")
"""Par que identifica um empreendimento financiado dentro de um contrato."""

CHAVE_CONTRATO = ("REF_BACEN",)
"""Identificador do contrato junto ao Banco Central."""

CHAVE_MUNICIPIO = ("CD_IBGE_MUNICIPIO",)
"""Código IBGE de 7 dígitos — a cola entre o Sicor e qualquer dado externo."""


# ==========================================================================
# Entidades
# ==========================================================================

@dataclass(frozen=True)
class Entidade:
    """Um arquivo (ou família de arquivos) tratado como tabela lógica."""

    chave: str
    rotulo: str
    arquivos: tuple[str, ...]
    grao: str
    pk: tuple[str, ...]
    colunas_uteis: tuple[str, ...] = ()
    papel: str = ""
    dominio: bool = False
    volume: str = "médio"          # "pequeno" | "médio" | "grande" | "enorme"
    usado: bool = True
    nota: str = ""

    def to_row(self) -> dict[str, Any]:
        return {
            "entidade": self.rotulo,
            "grão": self.grao,
            "chave primária": " + ".join(self.pk) if self.pk else "—",
            "volume": self.volume,
            "usado": "sim" if self.usado else "—",
            "papel": self.papel,
            "arquivos": ", ".join(self.arquivos),
        }


ENTIDADES: tuple[Entidade, ...] = (
    # ---------------------------------------------------------------- núcleo
    Entidade(
        "operacao", "Operação básica (contratada por ano)",
        ("SICOR_OPERACAO_BASICA_ESTADO_AAAA.gz",),
        grao="um empreendimento financiado dentro de um contrato",
        pk=CHAVE_OPERACAO,
        colunas_uteis=(
            "REF_BACEN", "NU_ORDEM", "CNPJ_IF", "CD_ESTADO", "CD_EMPREENDIMENTO",
            "CD_PROGRAMA", "CD_FONTE_RECURSO", "CD_TIPO_SEGURO", "CD_TIPO_IRRIGACAO",
            "DT_EMISSAO", "DT_VENCIMENTO", "DT_INIC_PLANTIO", "DT_FIM_PLANTIO",
            "DT_INIC_COLHEITA", "DT_FIM_COLHEITA", "VL_PARC_CREDITO",
            "VL_AREA_FINANC", "VL_PREV_PROD", "VL_RECEITA_BRUTA_ESPERADA",
            "VL_ALIQ_PROAGRO", "CD_CATEG_EMITENTE",
        ),
        papel="Espinha dorsal: valor, área, datas do ciclo, cobertura e alíquota.",
        volume="enorme",
        nota="Só traz CD_ESTADO. O município vem de 'complemento'.",
    ),
    Entidade(
        "complemento", "Complemento à operação básica",
        ("SICOR_COMPLEMENTO_OPERACAO_BASICA.gz",
         "SICOR_COMPLEMENTO_OPERACAO_BASICA_CONTRAT.gz"),
        grao="um empreendimento financiado",
        pk=CHAVE_OPERACAO,
        colunas_uteis=("REF_BACEN", "NU_ORDEM", "CD_IBGE_MUNICIPIO",
                       "CD_CONTRATO_STN", "CD_SUBPROGRAMA"),
        papel="Única fonte do município — sem ela não há mapa nem alerta dirigido.",
        volume="grande",
    ),
    Entidade(
        "operacao_contratada", "Operação básica (universo contratado)",
        ("SICOR_OPERACAO_BASICA_CONTRAT.gz",),
        grao="um empreendimento financiado",
        pk=CHAVE_OPERACAO,
        papel="Carteira 'viva': inclui operações ainda sem liberação de recursos.",
        volume="enorme",
    ),
    Entidade(
        "glebas", "Glebas em WKT",
        ("sicor_glebas_wkt_AAAA.gz", "SICOR_GLEBAS_CONTRAT.gz"),
        grao="uma gleba (polígono) de um empreendimento",
        pk=("REF_BACEN", "NU_ORDEM", "NU_GLEBA"),
        colunas_uteis=("REF_BACEN", "NU_ORDEM", "NU_GLEBA", "GEOMETRIA_WKT",
                       "VL_AREA_GLEBA"),
        papel="Geometria real do talhão: permite alerta em nível de gleba, "
              "centroide preciso e cruzamento com uso do solo e queimadas.",
        volume="enorme",
        nota="Maior ganho de precisão do projeto: substitui o centroide do "
             "município pelo centroide da própria lavoura.",
    ),
    Entidade(
        "propriedades", "Propriedades",
        ("SICOR_PROPRIEDADES.gz", "SICOR_PROPRIEDADES_CONTRAT.gz"),
        grao="uma propriedade vinculada ao empreendimento",
        pk=("REF_BACEN", "NU_ORDEM", "NU_ORDEM_PROPRIEDADE"),
        colunas_uteis=("CD_IBGE_MUNICIPIO", "NU_AREA_PROPRIEDADE",
                       "CD_TIPO_POSSE", "NU_CAR"),
        papel="Área total, posse e CAR — distingue arrendatário de proprietário "
              "e fecha a escala do imóvel (pequeno/médio/grande).",
        volume="grande",
    ),
    Entidade(
        "mutuarios", "Mutuários",
        ("SICOR_MUTUARIOS.gz", "SICOR_MUTUARIOS_CONTRAT.gz"),
        grao="um mutuário do contrato",
        pk=("REF_BACEN", "NU_CPF_CNPJ"),
        papel="NÃO utilizado — decisão de privacidade (docs/privacidade.md). "
              "A solução trabalha em nível de operação e município.",
        volume="grande",
        usado=False,
    ),
    Entidade(
        "cooperados", "Lista de cooperados",
        ("SICOR_LISTA_COOPERADOS.gz",),
        grao="um cooperado dentro de uma operação coletiva",
        pk=("REF_BACEN", "NU_ORDEM", "NU_SEQ_COOPERADO"),
        papel="Explode a operação da cooperativa nos produtores beneficiados — "
              "é o que torna a persona 'cooperativa' capaz de rebater o alerta "
              "para os associados.",
        volume="grande",
    ),

    # ------------------------------------------------------------ financeiro
    Entidade(
        "saldos", "Saldos das operações",
        ("SICOR_SALDOS_AAAA.gz",),
        grao="posição mensal do saldo devedor da operação",
        pk=("REF_BACEN", "NU_ORDEM", "DT_POSICAO"),
        colunas_uteis=("VL_SALDO_DEVEDOR", "VL_SALDO_VENCIDO", "DT_POSICAO"),
        papel="Exposição financeira corrente e inadimplência — transforma "
              "'área em risco' em 'dinheiro em risco'.",
        volume="enorme",
    ),
    Entidade(
        "liberacao", "Liberação de recursos",
        ("SICOR_LIBERACAO_RECURSOS.gz",),
        grao="uma liberação de parcela",
        pk=("REF_BACEN", "NU_ORDEM", "NU_PARCELA"),
        papel="Quanto do crédito já foi efetivamente desembolsado — "
              "capital exposto a perda hoje.",
        volume="grande",
    ),
    Entidade(
        "parcelas_desembolso", "Cronograma de desembolso",
        ("SICOR_PARCELAS_DESEMBOLSO.gz", "SICOR_PARCELAS_DESEMBOLSO_CONTRAT.gz"),
        grao="uma parcela programada",
        pk=("REF_BACEN", "NU_ORDEM", "NU_PARCELA"),
        papel="Calendário de caixa — permite alertar antes do vencimento.",
        volume="grande",
    ),
    Entidade(
        "renegociacao", "Renegociação (lista + operações + complemento)",
        ("SICOR_LISTA_RENEGOCIACAO.gz",
         "SICOR_OPERACAO_BASICA_RENEGOCIACAO.gz",
         "SICOR_COMPLEMENTO_OPERACAO_BASICA_RENEGOCIACAO.gz"),
        grao="uma operação renegociada",
        pk=CHAVE_OPERACAO,
        papel="Sinal de estresse prévio: município com renegociação recorrente "
              "recebe peso extra no escore de risco financeiro.",
        volume="grande",
    ),
    Entidade(
        "desclassificacao", "Desclassificação de operações",
        ("sicor_desclassificacao.gz",),
        grao="uma operação desclassificada",
        pk=CHAVE_OPERACAO,
        papel="Operações que perderam enquadramento — filtradas da carteira "
              "monitorada para não gerar alerta indevido.",
        volume="médio",
    ),
    Entidade(
        "alteracao_fonte", "Alterações de fonte de recursos",
        ("SICOR_LISTA_ALTERACAO_FONTE.gz",),
        grao="uma alteração de fonte",
        pk=("REF_BACEN", "NU_ORDEM", "DT_ALTERACAO"),
        papel="Rastreia trocas de funding que mudam taxa e enquadramento.",
        volume="médio",
    ),

    # --------------------------------------------------------------- Proagro
    Entidade(
        "cop", "Proagro — pedido de cobertura (COP)",
        ("SICOR_COP_BASICO.gz", "SICOR_COMPLEMENTO_COP.gz"),
        grao="um pedido de cobertura",
        pk=("REF_BACEN", "NU_ORDEM", "NU_COP"),
        colunas_uteis=("CD_EVENTO", "DT_OCORRENCIA", "DT_COMUNICACAO",
                       "CD_STATUS_COP", "VL_PERDA_DECLARADA"),
        papel="Etapa 1 da cadeia: o produtor declarou perda. Base da "
              "**taxa de acionamento** por município × cultura × evento.",
        volume="grande",
    ),
    Entidade(
        "rcp", "Proagro — comprovação de perdas (RCP)",
        ("SICOR_RCP_BASICO.gz", "SICOR_COMPLEMENTO_RCP.gz"),
        grao="um relatório de comprovação de perdas",
        pk=("REF_BACEN", "NU_ORDEM", "NU_RCP"),
        colunas_uteis=("CD_EVENTO_COMPROVADO", "VL_PERDA_COMPROVADA",
                       "VL_PRODUCAO_OBTIDA", "DT_PERICIA"),
        papel="Etapa 2: a perícia confirmou (ou não) o evento. Base da "
              "**severidade observada** e do casamento evento declarado × "
              "evento comprovado.",
        volume="grande",
    ),
    Entidade(
        "rcp_glebas", "Glebas do RCP",
        ("SICOR_RCP_GLEBAS_2015_2020.gz", "SICOR_RCP_GLEBAS_2021.gz"),
        grao="uma gleba periciada",
        pk=("REF_BACEN", "NU_ORDEM", "NU_RCP", "NU_GLEBA"),
        papel="Onde exatamente a perda foi comprovada — o único dado público "
              "que georreferencia sinistro em nível de talhão.",
        volume="grande",
    ),
    Entidade(
        "sumula", "Proagro — súmula de julgamento",
        ("SICOR_SUMULA_JULGAMENTO.gz",),
        grao="uma decisão de julgamento",
        pk=("REF_BACEN", "NU_ORDEM", "NU_COP"),
        papel="Etapa 3: deferimento, indeferimento e instância. Revela a "
              "**taxa de negativa** — informação que muda a comunicação com "
              "o produtor (o que documentar para não ter o pedido negado).",
        volume="médio",
    ),
    Entidade(
        "parcelas_proagro", "Proagro — parcelas",
        ("SICOR_PARCELAS_PROAGRO.gz",),
        grao="uma parcela de cobertura paga",
        pk=("REF_BACEN", "NU_ORDEM", "NU_PARCELA"),
        colunas_uteis=("VL_COBERTURA", "DT_PAGAMENTO", "CD_STATUS_PARCELA"),
        papel="Etapa 4: valor efetivamente coberto e prazo até o pagamento — "
              "a métrica que o produtor de fato quer saber.",
        volume="grande",
    ),

    # ---------------------------------------------------------------- Recor
    Entidade(
        "recor_operacao", "Recor — operações 1983–2012",
        ("recor_operacao_AAAA.csv.gz",),
        grao="uma operação histórica",
        pk=("NU_OPERACAO",),
        papel="Série longa de 30 anos para contexto climático estrutural. "
              "Usada só em gráfico de tendência, com o disclaimer do BCB "
              "sobre 1983–1994.",
        volume="enorme",
    ),
    Entidade(
        "recor_cop", "Recor — pedidos de cobertura 1983–2012",
        ("recor_cop_1983_2003.csv.gz", "recor_cop_2004_2012.csv.gz"),
        grao="um pedido de cobertura histórico",
        pk=("NU_OPERACAO", "NU_COP"),
        papel="Recorrência histórica de seca/excesso de chuva por UF — "
              "permite dizer 'na sua região isso acontece a cada N anos'.",
        volume="grande",
    ),

    # ------------------------------------------------------------- domínios
    Entidade(
        "d_municipios", "Municípios do Sicor",
        ("MunicipiosSicor.csv",),
        grao="um município",
        pk=CHAVE_MUNICIPIO,
        papel="Nome, UF e código IBGE — a ponte para todo dado externo.",
        dominio=True, volume="pequeno",
    ),
    Entidade(
        "d_empreendimento", "Empreendimento",
        ("Empreendimento.csv", "Atividade.csv", "Modalidade.csv",
         "Finalidade.csv", "Produto.csv", "VariedadeProduto.csv"),
        grao="um código de empreendimento",
        pk=("CD_EMPREENDIMENTO",),
        papel="Decodifica o empreendimento em atividade + modalidade + "
              "finalidade + produto (a cultura).",
        dominio=True, volume="pequeno",
    ),
    Entidade(
        "d_programa", "Programa / linha de crédito",
        ("Programa.csv", "Subprogramas.csv", "ProgramaProduto.csv",
         "ProgramaModalidade.csv", "ProgramaTaxaJuros.csv", "ProgramaUF.csv"),
        grao="um programa",
        pk=("CD_PROGRAMA",),
        papel="Pronaf, Pronamp, Moderfrota… define porte, taxa e persona.",
        dominio=True, volume="pequeno",
    ),
    Entidade(
        "d_fonte", "Fonte de recursos",
        ("FonteRecursos.csv", "FonteRecursosTaxaJuros.csv",
         "FonteRecursosUF.csv", "FonteRecursosPublicos.csv"),
        grao="uma fonte de recursos",
        pk=("CD_FONTE_RECURSO",),
        papel="Origem do funding — separa recurso controlado de livre.",
        dominio=True, volume="pequeno",
    ),
    Entidade(
        "d_evento", "Evento do Proagro",
        ("EventoProagro.csv", "recor_evento_cop_proagro.csv"),
        grao="um evento coberto",
        pk=("CD_EVENTO",),
        papel="Vocabulário oficial (seca, chuva excessiva, granizo, geada…) — "
              "casado com o catálogo climático interno.",
        dominio=True, volume="pequeno",
    ),
    Entidade(
        "d_zoneamento", "Zoneamento agrícola (Zarc)",
        ("Zoneamento.csv",),
        grao="um código de zoneamento",
        pk=("CD_ZONEAMENTO",),
        papel="Aderência ao Zarc — atenuante no escore e argumento central "
              "na mensagem ao produtor.",
        dominio=True, volume="pequeno",
    ),
    Entidade(
        "d_seguro", "Tipo de garantia/seguro",
        ("TipoGarantiaEmpreendimento.csv",),
        grao="um tipo de cobertura",
        pk=("CD_TIPO_SEGURO",),
        papel="Proagro, Proagro Mais, seguro privado ou **sem cobertura** — "
              "o campo que mais muda o teor da mensagem.",
        dominio=True, volume="pequeno",
    ),
    Entidade(
        "d_aliquota", "Alíquota básica do Proagro",
        ("AliquotaBaseProagro.csv",),
        grao="município × empreendimento",
        pk=("CD_IBGE_MUNICIPIO", "CD_EMPREENDIMENTO"),
        papel="Preço do risco segundo o próprio BCB — usado como proxy "
              "oficial de risco climático municipal.",
        dominio=True, volume="pequeno",
    ),
    Entidade(
        "d_ifs", "Instituições financeiras",
        ("SICOR_LISTA_IFS.csv",),
        grao="uma IF",
        pk=("CNPJ_IF",),
        papel="Nome do banco/cooperativa de crédito — persona institucional.",
        dominio=True, volume="pequeno",
    ),
    Entidade(
        "d_ciclo", "Ciclo do cultivar / fase de produção",
        ("CicloCultivarProagro.csv", "FaseCicloProducao.csv",
         "TipoCultivo.csv", "TipoCultura.csv", "TipoIrrigacao.csv",
         "TipoSoloProagro.csv", "TipoClima.csv", "OutrasPraticasManejo.csv"),
        grao="um atributo agronômico",
        pk=("CD_CICLO",),
        papel="Duração do ciclo e manejo — insumo do cálculo da fase "
              "fenológica e da sensibilidade ao evento.",
        dominio=True, volume="pequeno",
    ),
    Entidade(
        "d_status", "Status e motivos (COP, parcela, exclusão, rejeição)",
        ("StatusCOPProagro.csv", "StatusParcelaProagro.csv",
         "MotivoExclusao.csv", "MotivoRejeicaoSaldo.csv",
         "motivoDesclassificacao.csv", "InstanciaProagro.csv",
         "NaturezaProagro.csv", "SituacaoOperacao.csv"),
        grao="um código de situação",
        pk=("CD_STATUS",),
        papel="Traduz a cadeia do Proagro em linguagem humana e explica "
              "por que um pedido foi negado.",
        dominio=True, volume="pequeno",
    ),
    Entidade(
        "d_emitente", "Categoria de emitente / beneficiário",
        ("CategoriaEmitente.csv", "tipoBeneficiario.csv",
         "TipoIntegracao.csv", "Consorcio.csv"),
        grao="uma categoria",
        pk=("CD_CATEG_EMITENTE",),
        papel="Individual, cooperativa, condomínio — derivação direta da persona.",
        dominio=True, volume="pequeno",
    ),
    Entidade(
        "d_prazos", "Prazos e encargos",
        ("PrazoOperacao.csv", "PrazoOperacaoPrograma.csv",
         "PrazoOperacaoFonteRecursos.csv", "PrazoOperacaoModalidade.csv",
         "EncargosFinanceirosComplementares.csv", "TipoBonus.csv",
         "InstrumentoCredito.csv", "Base_legal_renegociacao.csv",
         "TipoConformidade.csv", "CestaSafras.csv", "CategoriaProduto.csv",
         "GraoSemente.csv", "TipoAgropecuaria.csv", "TipoManejo.csv",
         "SistemaProducaoEmpreendimento.csv", "UnidadeMedida.csv"),
        grao="atributos contratuais diversos",
        pk=("CD_PRAZO",),
        papel="Completam a leitura do contrato (prazo, encargo, unidade de "
              "medida da produtividade prevista).",
        dominio=True, volume="pequeno",
    ),

    # --------------------------------------------------------------- externo
    Entidade(
        "ext_clima", "Clima observado e previsto (externo)",
        ("Open-Meteo", "NASA POWER", "INMET"),
        grao="ponto (lat, lon) × dia",
        pk=("lat", "lon", "data"),
        papel="Previsão e histórico climático nos centroides de gleba/município.",
        volume="médio",
        nota="Entra pelo código IBGE ou pelo centroide da gleba.",
    ),
    Entidade(
        "ext_territorio", "Território e uso do solo (externo)",
        ("IBGE malhas/SIDRA", "MapBiomas", "INPE queimadas", "ANA", "CONAB"),
        grao="município (ou polígono) × ano",
        pk=CHAVE_MUNICIPIO,
        papel="Produção, área plantada, uso do solo, focos de calor e "
              "situação hídrica — contexto que o Sicor não tem.",
        volume="médio",
    ),
    Entidade(
        "ext_seguro", "Seguro rural (externo)",
        ("PSR/MAPA — Atlas do Seguro Rural", "SUSEP"),
        grao="município × cultura × ano",
        pk=CHAVE_MUNICIPIO,
        papel="Apólices subvencionadas, taxa média e sinistralidade do seguro "
              "privado — completa o quadro que o Proagro sozinho não fecha.",
        volume="médio",
    ),
)

ENTIDADES_POR_CHAVE: dict[str, Entidade] = {e.chave: e for e in ENTIDADES}


# ==========================================================================
# Ligações
# ==========================================================================

@dataclass(frozen=True)
class Ligacao:
    """Uma junção entre duas entidades, com a chave e o porquê."""

    origem: str
    destino: str
    chaves: tuple[str, ...]
    cardinalidade: str = "N:1"
    motivo: str = ""
    critica: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_row(self) -> dict[str, Any]:
        o = ENTIDADES_POR_CHAVE.get(self.origem)
        d = ENTIDADES_POR_CHAVE.get(self.destino)
        return {
            "de": o.rotulo if o else self.origem,
            "para": d.rotulo if d else self.destino,
            "chave": " + ".join(self.chaves),
            "cardinalidade": self.cardinalidade,
            "crítica": "sim" if self.critica else "—",
            "para quê": self.motivo,
        }


LIGACOES: tuple[Ligacao, ...] = (
    # ------------------------------------------------ núcleo georreferenciado
    Ligacao("operacao", "complemento", CHAVE_OPERACAO, "1:1",
            "Traz o CD_IBGE_MUNICIPIO. Sem esta junção a operação fica sem "
            "localização e nenhum alerta pode ser dirigido.",
            critica=True, tags=("geo", "obrigatória")),
    Ligacao("complemento", "d_municipios", CHAVE_MUNICIPIO, "N:1",
            "Nome, UF e centroide do município.",
            critica=True, tags=("geo",)),
    Ligacao("operacao", "glebas", CHAVE_OPERACAO, "1:N",
            "Substitui o centroide do município pelo polígono real da lavoura: "
            "ganho de precisão de ~50 km para ~1 km na consulta climática.",
            critica=True, tags=("geo", "precisão")),
    Ligacao("operacao", "propriedades", CHAVE_OPERACAO, "1:N",
            "Área total do imóvel, posse e CAR — define porte e vínculo com a terra.",
            tags=("perfil",)),
    Ligacao("operacao", "mutuarios", CHAVE_CONTRATO, "1:N",
            "Ligação existente no modelo do BCB, mas **deliberadamente não "
            "materializada** aqui: o AgroSentinela nunca lê dado pessoal. "
            "Documentada para que a decisão fique explícita ao avaliador.",
            tags=("privacidade", "não-usada")),
    Ligacao("operacao", "cooperados", CHAVE_OPERACAO, "1:N",
            "Explode a operação coletiva nos produtores associados, permitindo "
            "que a cooperativa rebata o alerta individualmente.",
            tags=("persona",)),
    Ligacao("operacao_contratada", "complemento", CHAVE_OPERACAO, "1:1",
            "Mesmo papel do complemento, para o universo contratado.",
            critica=True, tags=("geo",)),

    # ------------------------------------------------------------- domínios
    Ligacao("operacao", "d_empreendimento", ("CD_EMPREENDIMENTO",), "N:1",
            "Cultura, atividade, modalidade e finalidade.",
            critica=True, tags=("agronomia",)),
    Ligacao("operacao", "d_programa", ("CD_PROGRAMA",), "N:1",
            "Programa de crédito — define porte e tom da comunicação.",
            tags=("persona",)),
    Ligacao("operacao", "d_fonte", ("CD_FONTE_RECURSO",), "N:1",
            "Fonte de recursos e taxa aplicável.", tags=("financeiro",)),
    Ligacao("operacao", "d_seguro", ("CD_TIPO_SEGURO",), "N:1",
            "Proagro, Proagro Mais, seguro privado ou sem cobertura — o campo "
            "que mais altera o conteúdo da mensagem.",
            critica=True, tags=("risco",)),
    Ligacao("operacao", "d_emitente", ("CD_CATEG_EMITENTE",), "N:1",
            "Individual, cooperativa ou condomínio — deriva a persona.",
            tags=("persona",)),
    Ligacao("operacao", "d_ciclo", ("CD_CICLO",), "N:1",
            "Duração do ciclo do cultivar, refinando a fase fenológica.",
            tags=("agronomia",)),
    Ligacao("operacao", "d_zoneamento", ("CD_ZONEAMENTO",), "N:1",
            "Aderência ao Zarc: atenua o escore e vira argumento na mensagem.",
            tags=("risco",)),
    Ligacao("operacao", "d_ifs", ("CNPJ_IF",), "N:1",
            "Nome da instituição financeira (persona bancária).",
            tags=("persona",)),
    Ligacao("operacao", "d_prazos", ("CD_PRAZO",), "N:1",
            "Prazo de vigência e encargos.", tags=("financeiro",)),
    Ligacao("complemento", "d_aliquota",
            ("CD_IBGE_MUNICIPIO", "CD_EMPREENDIMENTO"), "N:1",
            "Alíquota básica do Proagro — proxy oficial de risco climático "
            "daquele município para aquela cultura.",
            critica=True, tags=("risco",)),

    # -------------------------------------------------------- cadeia Proagro
    Ligacao("operacao", "cop", CHAVE_OPERACAO, "1:N",
            "Etapa 1: pedidos de cobertura já feitos por esta operação.",
            critica=True, tags=("proagro",)),
    Ligacao("cop", "rcp", ("REF_BACEN", "NU_ORDEM", "NU_COP"), "1:N",
            "Etapa 2: o que a perícia comprovou. Comparar CD_EVENTO com "
            "CD_EVENTO_COMPROVADO mede a acurácia da declaração.",
            critica=True, tags=("proagro",)),
    Ligacao("rcp", "rcp_glebas", ("REF_BACEN", "NU_ORDEM", "NU_RCP"), "1:N",
            "Georreferencia a perda comprovada no talhão.",
            tags=("proagro", "geo")),
    Ligacao("cop", "sumula", ("REF_BACEN", "NU_ORDEM", "NU_COP"), "1:N",
            "Etapa 3: deferido ou indeferido, e em qual instância. Revela a "
            "taxa de negativa por evento e por motivo.",
            critica=True, tags=("proagro",)),
    Ligacao("cop", "parcelas_proagro", CHAVE_OPERACAO, "1:N",
            "Etapa 4: valor pago e prazo até o pagamento.",
            tags=("proagro", "financeiro")),
    Ligacao("cop", "d_evento", ("CD_EVENTO",), "N:1",
            "Nome oficial do evento climático.",
            critica=True, tags=("proagro",)),
    Ligacao("cop", "d_status", ("CD_STATUS_COP",), "N:1",
            "Situação do pedido em linguagem humana.", tags=("proagro",)),

    # ------------------------------------------------------------ financeiro
    Ligacao("operacao", "saldos", CHAVE_OPERACAO, "1:N",
            "Saldo devedor e vencido por posição mensal: converte área em risco "
            "em dinheiro em risco.",
            critica=True, tags=("financeiro",)),
    Ligacao("operacao", "liberacao", CHAVE_OPERACAO, "1:N",
            "Quanto do crédito já foi desembolsado.", tags=("financeiro",)),
    Ligacao("operacao", "parcelas_desembolso", CHAVE_OPERACAO, "1:N",
            "Calendário de desembolso e vencimento.", tags=("financeiro",)),
    Ligacao("operacao", "renegociacao", CHAVE_OPERACAO, "1:1",
            "Marca a operação já renegociada — estresse prévio conhecido.",
            tags=("financeiro", "risco")),
    Ligacao("operacao", "desclassificacao", CHAVE_OPERACAO, "1:1",
            "Remove da carteira monitorada o que perdeu enquadramento, "
            "evitando alerta indevido.",
            tags=("qualidade",)),
    Ligacao("operacao", "alteracao_fonte", CHAVE_OPERACAO, "1:N",
            "Histórico de troca de funding.", tags=("financeiro",)),

    # ----------------------------------------------------------------- Recor
    Ligacao("recor_operacao", "recor_cop", ("NU_OPERACAO",), "1:N",
            "Série histórica 1983–2012 de acionamento por evento e UF.",
            tags=("histórico",)),
    Ligacao("recor_cop", "d_evento", ("CD_EVENTO",), "N:1",
            "Compatibiliza o vocabulário antigo do Recor com o do Sicor.",
            tags=("histórico",)),

    # --------------------------------------------------------------- externo
    Ligacao("glebas", "ext_clima", ("centroide da gleba",), "N:1",
            "Consulta climática no ponto exato da lavoura.",
            critica=True, tags=("externo", "clima")),
    Ligacao("d_municipios", "ext_clima", ("lat", "lon"), "N:1",
            "Consulta climática no centroide do município quando não há gleba.",
            critica=True, tags=("externo", "clima")),
    Ligacao("d_municipios", "ext_territorio", CHAVE_MUNICIPIO, "1:N",
            "Produção agrícola municipal (IBGE/PAM), uso do solo (MapBiomas), "
            "focos de calor (INPE) e situação hídrica (ANA).",
            tags=("externo",)),
    Ligacao("d_municipios", "ext_seguro", CHAVE_MUNICIPIO, "1:N",
            "Apólices do PSR e sinistralidade do seguro privado, para comparar "
            "com a cobertura do Proagro na mesma região.",
            critica=True, tags=("externo", "seguro")),
)


# ==========================================================================
# Consultas sobre o grafo
# ==========================================================================

def vizinhos(chave: str) -> list[str]:
    saida = {l.destino for l in LIGACOES if l.origem == chave}
    saida |= {l.origem for l in LIGACOES if l.destino == chave}
    return sorted(saida)


def caminho(origem: str, destino: str) -> list[Ligacao]:
    """
    Menor sequência de junções entre duas entidades.

    Usado pela página de documentação para responder perguntas do tipo
    "como chego do pedido de cobertura até o município?" — a resposta é
    ``cop → operacao → complemento → d_municipios``.
    """
    if origem not in ENTIDADES_POR_CHAVE or destino not in ENTIDADES_POR_CHAVE:
        raise KeyError(f"Entidade desconhecida: {origem} / {destino}")
    if origem == destino:
        return []
    adj: dict[str, list[tuple[str, Ligacao]]] = {}
    for l in LIGACOES:
        adj.setdefault(l.origem, []).append((l.destino, l))
        adj.setdefault(l.destino, []).append((l.origem, l))
    fila: deque[tuple[str, list[Ligacao]]] = deque([(origem, [])])
    visto = {origem}
    while fila:
        atual, trilha = fila.popleft()
        for prox, lig in adj.get(atual, []):
            if prox in visto:
                continue
            nova = [*trilha, lig]
            if prox == destino:
                return nova
            visto.add(prox)
            fila.append((prox, nova))
    return []


def conexo() -> bool:
    """Verdadeiro se toda entidade é alcançável a partir de ``operacao``."""
    alcancadas = {"operacao"}
    fronteira = ["operacao"]
    while fronteira:
        atual = fronteira.pop()
        for v in vizinhos(atual):
            if v not in alcancadas:
                alcancadas.add(v)
                fronteira.append(v)
    return alcancadas == set(ENTIDADES_POR_CHAVE)


def ligacoes_criticas() -> list[Ligacao]:
    return [l for l in LIGACOES if l.critica]


def ligacoes_por_tag(tag: str) -> list[Ligacao]:
    return [l for l in LIGACOES if tag in l.tags]


def entidades_por_tipo(dominio: bool | None = None) -> list[Entidade]:
    if dominio is None:
        return list(ENTIDADES)
    return [e for e in ENTIDADES if e.dominio is dominio]


def resumo() -> dict[str, Any]:
    return {
        "entidades": len(ENTIDADES),
        "entidades_fato": len(entidades_por_tipo(dominio=False)),
        "entidades_dominio": len(entidades_por_tipo(dominio=True)),
        "ligacoes": len(LIGACOES),
        "ligacoes_criticas": len(ligacoes_criticas()),
        "grafo_conexo": conexo(),
    }


# ==========================================================================
# Diagrama
# ==========================================================================

_GRUPOS = (
    ("Núcleo da carteira",
     ("operacao", "operacao_contratada", "complemento", "glebas",
      "propriedades", "cooperados", "mutuarios")),
    ("Cadeia do Proagro", ("cop", "rcp", "rcp_glebas", "sumula", "parcelas_proagro")),
    ("Financeiro", ("saldos", "liberacao", "parcelas_desembolso",
                    "renegociacao", "desclassificacao", "alteracao_fonte")),
    ("Histórico (Recor)", ("recor_operacao", "recor_cop")),
    ("Tabelas de domínio",
     ("d_municipios", "d_empreendimento", "d_programa", "d_fonte", "d_evento",
      "d_zoneamento", "d_seguro", "d_aliquota", "d_ifs", "d_ciclo",
      "d_status", "d_emitente", "d_prazos")),
    ("Fontes externas livres", ("ext_clima", "ext_territorio", "ext_seguro")),
)


def _id(chave: str) -> str:
    return chave.replace("-", "_")


def mermaid(*, somente_criticas: bool = False) -> str:
    """Diagrama Mermaid do modelo integrado, pronto para a documentação."""
    linhas = ["graph LR"]
    for titulo, chaves in _GRUPOS:
        linhas.append(f'  subgraph {_id(titulo.replace(" ", "_"))}["{titulo}"]')
        for ch in chaves:
            ent = ENTIDADES_POR_CHAVE.get(ch)
            if ent is None:
                continue
            marca = "" if ent.usado else " ✖"
            linhas.append(f'    {_id(ch)}["{ent.rotulo}{marca}"]')
        linhas.append("  end")
    for l in LIGACOES:
        if somente_criticas and not l.critica:
            continue
        seta = "==>" if l.critica else "-->"
        rot = " + ".join(l.chaves)
        linhas.append(f"  {_id(l.origem)} {seta}|{rot}| {_id(l.destino)}")
    return "\n".join(linhas)


def tabela_entidades() -> list[dict[str, Any]]:
    return [e.to_row() for e in ENTIDADES]


def tabela_ligacoes() -> list[dict[str, Any]]:
    return [l.to_row() for l in LIGACOES]


# ==========================================================================
# Receita de montagem — a ordem em que o ETL executa as junções
# ==========================================================================

@dataclass(frozen=True)
class PassoMontagem:
    ordem: int
    nome: str
    entrada: tuple[str, ...]
    saida: str
    descricao: str


RECEITA: tuple[PassoMontagem, ...] = (
    PassoMontagem(
        1, "Referência geográfica",
        ("d_municipios", "d_aliquota", "ext_territorio"), "municipios",
        "Municípios do Sicor + centroides IBGE + alíquota básica do Proagro, "
        "enriquecidos com produção agrícola (PAM) e uso do solo.",
    ),
    PassoMontagem(
        2, "Carteira georreferenciada",
        ("operacao", "operacao_contratada", "complemento", "desclassificacao",
         "d_empreendimento", "d_programa", "d_fonte", "d_seguro", "d_emitente",
         "d_ciclo", "d_zoneamento", "d_ifs"), "carteira",
        "Operações vigentes decodificadas, com município, cultura, datas do "
        "ciclo, cobertura e persona. Exclui operações desclassificadas.",
    ),
    PassoMontagem(
        3, "Geometria fina",
        ("glebas", "propriedades"), "glebas",
        "Centroide e área de cada gleba, ligados à operação — substitui o "
        "centroide do município na consulta climática quando disponível.",
    ),
    PassoMontagem(
        4, "Exposição financeira",
        ("saldos", "liberacao", "parcelas_desembolso", "renegociacao"),
        "exposicao",
        "Saldo devedor, saldo vencido, desembolsado e marca de renegociação "
        "por operação — e agregado por município.",
    ),
    PassoMontagem(
        5, "Cadeia do Proagro",
        ("cop", "rcp", "sumula", "parcelas_proagro", "rcp_glebas", "d_evento",
         "d_status"), "proagro_sinistros",
        "Percorre COP → RCP → súmula → parcelas e agrega por município × "
        "cultura × evento: taxa de acionamento, taxa de comprovação, taxa de "
        "deferimento, perda média e prazo até o pagamento.",
    ),
    PassoMontagem(
        6, "Série histórica",
        ("operacao", "recor_operacao", "recor_cop"), "serie_credito",
        "Contratação anual por UF e cultura desde 2013 (Sicor) com opção de "
        "estender a 1983 pelo Recor.",
    ),
    PassoMontagem(
        7, "Contexto externo",
        ("ext_clima", "ext_territorio", "ext_seguro"), "contexto_externo",
        "Normais climáticas, focos de calor, uso do solo, situação hídrica e "
        "penetração do seguro rural privado por município.",
    ),
)


def receita_tabela() -> list[dict[str, Any]]:
    saida = []
    for p in RECEITA:
        entradas = [
            ENTIDADES_POR_CHAVE[e].rotulo for e in p.entrada
            if e in ENTIDADES_POR_CHAVE
        ]
        saida.append({
            "ordem": p.ordem,
            "passo": p.nome,
            "produz": p.saida,
            "consome": ", ".join(entradas),
            "o que faz": p.descricao,
        })
    return saida
