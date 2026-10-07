"""
Catálogo dos arquivos publicados pelo Banco Central em
*Tabelas e Microdados do Crédito Rural e do Proagro*.

https://www.bcb.gov.br/estabilidadefinanceira/tabelas-credito-rural-proagro

Este módulo é a **fonte única de verdade** sobre onde cada arquivo mora, o
que ele contém e se o AgroSentinela o utiliza. O ETL consome este catálogo;
a interface o exibe para que o avaliador veja exatamente de onde vem cada
dado.

Campos:

* ``chave``   — identificador interno
* ``nome``    — rótulo publicado pelo BCB
* ``url``     — endereço do arquivo
* ``secao``   — seção da página do BCB
* ``tipo``    — ``dominio`` | ``microdado`` | ``documentacao``
* ``usado``   — se alimenta diretamente a solução
* ``papel``   — para que serve aqui
* ``hash_url``— arquivo ``.hash`` para verificação de integridade, quando existe
* ``pesado``  — arquivos grandes, baixados apenas sob demanda
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

BASE = "https://www.bcb.gov.br/htms/sicor"
BRUTOS = f"{BASE}/DadosBrutos"
CONTEUDO = "https://www.bcb.gov.br/content/estabilidadefinanceira/sicornoticias"

PAGINA_FONTE = (
    "https://www.bcb.gov.br/estabilidadefinanceira/tabelas-credito-rural-proagro"
)

SEC_DOMINIO = "1. Sicor — Tabelas de domínio"
SEC_MICRO = "2. Sicor — Microdados do crédito rural e do Proagro (desde 2013)"
SEC_PUBLICO = "3. Sicor — Microdados do crédito rural público"
SEC_RECOR = "4. Recor/PGRO — Microdados antigos (1983 a 2012)"
SEC_CONTRAT = "5. Sicor — Microdados do crédito rural contratado"
SEC_DOC = "Documentação"


@dataclass(frozen=True)
class ArquivoBCB:
    chave: str
    nome: str
    url: str
    secao: str
    tipo: str = "dominio"
    usado: bool = False
    papel: str = ""
    hash_url: str | None = None
    pesado: bool = False
    anos: tuple[int, ...] = field(default_factory=tuple)

    def to_row(self) -> dict[str, Any]:
        return {
            "chave": self.chave,
            "nome": self.nome,
            "seção": self.secao,
            "tipo": self.tipo,
            "usado": "sim" if self.usado else "—",
            "papel na solução": self.papel,
            "arquivo grande": "sim" if self.pesado else "—",
            "url": self.url,
        }


def _d(chave: str, nome: str, arquivo: str, *, usado: bool = False, papel: str = "") -> ArquivoBCB:
    """Tabela de domínio."""
    return ArquivoBCB(
        chave=chave, nome=nome, url=f"{BASE}/{arquivo}", secao=SEC_DOMINIO,
        tipo="dominio", usado=usado, papel=papel,
    )


def _m(
    chave: str, nome: str, arquivo: str, secao: str, *,
    usado: bool = False, papel: str = "", pesado: bool = True, hash_: bool = False,
) -> ArquivoBCB:
    """Microdado (.gz)."""
    return ArquivoBCB(
        chave=chave, nome=nome, url=f"{BRUTOS}/{arquivo}", secao=secao,
        tipo="microdado", usado=usado, papel=papel, pesado=pesado,
        hash_url=f"{BRUTOS}/{arquivo.rsplit('.', 1)[0]}.hash" if hash_ else None,
    )


ANOS_OPERACAO = tuple(range(2013, 2027))
ANOS_SALDO = tuple(range(2015, 2027))
ANOS_GLEBAS = tuple(range(2013, 2027))
ANOS_RECOR = tuple(range(1983, 2013))


# ==========================================================================
# 1. Tabelas de domínio
# ==========================================================================
DOMINIOS: tuple[ArquivoBCB, ...] = (
    _d("aliquota_proagro", "Alíquotas Proagro por município", "AliquotaBaseProagro.csv",
       usado=True, papel="Alíquota básica do Proagro por município, exibida no perfil de risco."),
    _d("base_legal_reneg", "Base legal de renegociação", "Base_legal_renegociacao.csv",
       usado=True, papel="Amparo legal da renegociação — contextualiza o "
                         "estresse prévio da operação."),
    _d("categoria_emitente", "Categoria de emitente", "CategoriaEmitente.csv",
       usado=True, papel="Identifica cooperativas e condomínios — deriva a persona."),
    _d("categoria_produto", "Categorias dos produtos/cestas", "CategoriaProduto.csv",
       usado=True, papel="Cesta de produtos — agrupa culturas afins nos filtros e nos agregados."),
    _d("ciclo_cultivar", "Ciclo do cultivar", "CicloCultivarProagro.csv",
       usado=True, papel="Ajusta a duração do ciclo usada no cálculo da fase fenológica."),
    _d("empreendimento", "Empreendimento", "Empreendimento.csv",
       usado=True, papel="Decodifica CD_EMPREENDIMENTO em atividade, modalidade, finalidade e produto."),
    _d("atividade", "Atividade", "Atividade.csv", usado=True, papel="Agrícola ou pecuária."),
    _d("finalidade", "Finalidade", "Finalidade.csv", usado=True, papel="Custeio, investimento ou comercialização."),
    _d("modalidade", "Modalidade", "Modalidade.csv", usado=True, papel="Modalidade da operação."),
    _d("produto", "Produto", "Produto.csv",
       usado=True, papel="Nome da cultura — mapeado para o catálogo fenológico interno."),
    _d("variedade_produto", "Subproduto / variedade de produto", "VariedadeProduto.csv",
       usado=True, papel="Refina a cultura (ex.: café arábica x conilon), que "
                         "muda a sensibilidade fenológica."),
    _d("consorcio", "Consórcio", "Consorcio.csv",
       usado=True, papel="Identifica consórcios de produtores — deriva a persona coletiva."),
    _d("cesta_safras", "Cesta de safras", "CestaSafras.csv",
       usado=True, papel="Define o ano-safra de referência de cada operação."),
    _d("zoneamento", "Zoneamento agrícola de risco climático", "Zoneamento.csv",
       usado=True, papel="Indica aderência ao Zarc — usado como atenuante de risco."),
    _d("tipo_cultura", "Tipo de cultura", "TipodeCultura.csv",
       usado=True, papel="Anual, semiperene ou perene — muda a lógica de fase fenológica."),
    _d("encargos", "Encargos financeiros complementares", "EncargosFinanceirosComplementares.csv",
       usado=True, papel="Encargos complementares — compõem o custo efetivo na comunicação financeira."),
    _d("evento_proagro", "Evento do Proagro", "EventoProagro.csv",
       usado=True, papel="Vocabulário oficial dos eventos cobertos — casado com o catálogo interno."),
    _d("fonte_recursos", "Fonte de recursos", "FonteRecursos.csv",
       usado=True, papel="Origem do funding da operação."),
    ArquivoBCB("lista_ifs", "IFs do Sicor", f"{BRUTOS}/SICOR_LISTA_IFS.csv", SEC_DOMINIO,
               "dominio", True, "Nome das instituições financeiras (persona bancária)."),
    _d("instancia_proagro", "Instância do Proagro", "InstanciaProagro.csv",
       usado=True, papel="Instância de julgamento do pedido de cobertura."),
    _d("instrumento_credito", "Instrumento de crédito", "InstrumentoCredito.csv",
       usado=True, papel="Cédula, nota promissória etc. — contexto contratual do alerta."),
    _d("programa_modalidade", "Modalidades por programa ou linha", "ProgramaModalidade.csv",
       usado=True, papel="Modalidades permitidas por programa — valida o enquadramento."),
    ArquivoBCB("motivo_desclassificacao", "Motivos de desclassificação de operação",
               f"{CONTEUDO}/motivoDesclassificacao.csv", SEC_DOMINIO,
               "dominio", True,
               "Explica por que a operação saiu da carteira monitorada."),
    _d("motivo_exclusao", "Motivos de exclusão de operação", "MotivoExclusao.csv",
       usado=True, papel="Por que a operação foi excluída — evita alerta sobre contrato morto."),
    _d("motivo_rejeicao", "Motivos de rejeição de saldos", "MotivoRejeicaoSaldo.csv",
       usado=True, papel="Por que um saldo foi rejeitado — filtro de qualidade do dataset 'exposicao'."),
    _d("municipios", "Municípios do Sicor", "MunicipiosSicor.csv",
       usado=True, papel="Código IBGE, nome e UF — base geográfica de toda a solução."),
    _d("natureza_proagro", "Natureza do Proagro", "NaturezaProagro.csv",
       usado=True, papel="Proagro tradicional x Proagro Mais (Pronaf)."),
    _d("prazo_operacao", "Prazo de vigência da operação", "PrazoOperacao.csv",
       usado=True, papel="Prazo padrão de vigência — base do cronograma de vencimento."),
    _d("prazo_programa", "Prazo — exceção por programa", "PrazoOperacaoPrograma.csv",
       usado=True, papel="Exceções de prazo por programa."),
    _d("prazo_fonte", "Prazo — exceção por fonte de recursos", "PrazoOperacaoFonteRecursos.csv",
       usado=True, papel="Exceções de prazo por fonte de recursos."),
    _d("prazo_modalidade", "Prazo — exceção por modalidade/atividade/finalidade",
       "PrazoOperacaoModalidade.csv",
       usado=True, papel="Exceções de prazo por modalidade, atividade e finalidade."),
    _d("programa_produto", "Produto por programa ou linha", "ProgramaProduto.csv",
       usado=True, papel="Produtos elegíveis por programa — valida cultura x linha de crédito."),
    _d("programa", "Programa ou linha de crédito", "Programa.csv",
       usado=True, papel="Pronaf, Pronamp e demais — deriva a persona e o tom da mensagem."),
    _d("tipo_agropecuaria", "Tipo de agricultura", "TipoAgropecuaria.csv",
       usado=True, papel="Convencional, orgânica ou agroecológica — ajusta o tom técnico da mensagem."),
    _d("tipo_integracao", "Tipo de integração/consórcio", "TipoIntegracao.csv",
       usado=True, papel="ILP, ILPF e afins — sistemas integrados têm resposta distinta a evento climático."),
    _d("grao_semente", "Grão/semente", "GraoSemente.csv",
       usado=True, papel="Produção de grão x de semente — a exigência de qualidade muda a perda relevante."),
    _d("tipo_irrigacao", "Tipo de irrigação", "TipoIrrigacao.csv",
       usado=True, papel="Distingue sequeiro de irrigado na regra R-SEC-02."),
    _d("tipo_cultivo", "Tipo de cultivo", "TipoCultivo.csv",
       usado=True, papel="Solteiro, consorciado ou sucessão — afeta a janela e a exposição."),
    _d("fase_ciclo", "Fase/ciclo de produção", "FaseCicloProducao.csv",
       usado=True, papel="Vocabulário oficial de fase produtiva — casado com "
                         "o catálogo fenológico interno."),
    _d("tipo_clima", "Tipo de clima / exigência climática", "TipoClima.csv",
       usado=True, papel="Exigência climática da cultura — refina a sensibilidade por evento."),
    _d("praticas_manejo", "Outras práticas de manejo", "OutrasPraticasManejo.csv",
       usado=True, papel="Plantio direto, terraceamento etc. — atenuantes reais de risco climático."),
    _d("sistema_producao", "Sistema de produção por empreendimento",
       "SistemaProducaoEmpreendimento.csv",
       usado=True, papel="Sistema de produção do empreendimento — contexto "
                         "agronômico que qualifica o alerta."),
    _d("situacao_operacao", "Situação da operação", "SituacaoOperacao.csv",
       usado=True, papel="Filtra operações liquidadas ou baixadas, que não "
                         "devem gerar alerta."),
    _d("status_cop", "Status da COP", "StatusCOPProagro.csv",
       usado=True, papel="Situação do pedido de cobertura do Proagro."),
    _d("status_parcela", "Status da parcela do Proagro", "StatusParcelaProagro.csv",
       usado=True, papel="Situação do pagamento da cobertura."),
    _d("subprogramas", "Subprogramas", "Subprogramas.csv",
       usado=True, papel="Detalha a linha de crédito dentro do programa."),
    _d("programa_taxa", "Taxa de juros por programa ou linha", "ProgramaTaxaJuros.csv",
       usado=True, papel="Taxa de juros por programa — usada na leitura de custo do crédito."),
    _d("fonte_taxa", "Taxa de juros por fonte de recursos", "FonteRecursosTaxaJuros.csv",
       usado=True, papel="Taxa de juros por fonte — idem, pelo lado do funding."),
    _d("tipo_beneficiario", "Tipo de beneficiário", "tipoBeneficiario.csv",
       usado=True, papel="Perfil do beneficiário — deriva a persona e o letramento técnico."),
    _d("tipo_bonus", "Tipo de bônus", "TipoBonus.csv",
       usado=True, papel="Bônus de adimplência — argumento na comunicação financeira preventiva."),
    _d("tipo_conformidade", "Tipo de conformidade", "TipoConformidade.csv",
       usado=True, papel="Conformidade socioambiental — critério de subscrição para a persona de seguros."),
    ArquivoBCB("tipo_manejo", "Tipo de manejo", f"{CONTEUDO}/TipoManejo.csv", SEC_DOMINIO,
               "dominio", True,
               "Manejo adotado — atenuante declarado de risco climático."),
    _d("tipo_seguro", "Tipo de seguro", "TipoGarantiaEmpreendimento.csv",
       usado=True, papel="Proagro, Proagro Mais, seguro privado ou sem cobertura."),
    _d("tipo_solo", "Tipo de solo", "TipoSoloProagro.csv",
       usado=True, papel="Entra na consulta ao Zarc: a janela de plantio "
                         "recomendada depende do tipo de solo."),
    _d("uf_fonte", "UF por fonte de recursos", "FonteRecursosUF.csv",
       usado=True, papel="UFs habilitadas por fonte de recursos — valida a cobertura geográfica."),
    _d("uf_programa", "UF por programa ou linha", "ProgramaUF.csv",
       usado=True, papel="UFs habilitadas por programa — idem."),
    _d("unidade_medida", "Unidade de medida", "UnidadeMedida.csv",
       usado=True, papel="Unidade da produtividade prevista (sacas/ha, t/ha…)."),
    _d("fonte_recursos_publicos", "Fontes de recursos públicas", "FonteRecursosPublicos.csv",
       usado=True, papel="Fontes públicas de funding — recorte da persona de política pública."),
)


# ==========================================================================
# 2. Microdados do crédito rural e do Proagro (desde 2013)
# ==========================================================================
def _operacoes_por_ano() -> tuple[ArquivoBCB, ...]:
    return tuple(
        ArquivoBCB(
            chave=f"operacao_{ano}",
            nome=f"Operações contratadas em {ano}",
            url=f"{BRUTOS}/SICOR_OPERACAO_BASICA_ESTADO_{ano}.gz",
            secao=SEC_MICRO, tipo="microdado",
            usado=True,
            papel="Espinha dorsal da carteira: valor, área, datas do ciclo, "
                  "empreendimento, cobertura e alíquota." if ano >= 2024 else
                  "Série histórica de contratação (dataset 'serie_credito').",
            hash_url=f"{BRUTOS}/SICOR_OPERACAO_BASICA_ESTADO_{ano}.hash",
            pesado=True, anos=(ano,),
        )
        for ano in ANOS_OPERACAO
    )


def _saldos_por_ano() -> tuple[ArquivoBCB, ...]:
    itens = []
    for semestre in ("2013_01", "2013_02", "2014_01", "2014_02"):
        itens.append(ArquivoBCB(
            chave=f"saldo_{semestre}", nome=f"Saldos {semestre.replace('_', '/')}",
            url=f"{BRUTOS}/SICOR_SALDOS_{semestre}.gz", secao=SEC_MICRO,
            tipo="microdado", pesado=True, usado=True,
            papel="Início da série de saldos (formato semestral), usado na "
                  "tendência longa de inadimplência.",
            hash_url=f"{BRUTOS}/SICOR_SALDOS_{semestre}.hash",
        ))
    for ano in ANOS_SALDO:
        itens.append(ArquivoBCB(
            chave=f"saldo_{ano}", nome=f"Saldos de operações em {ano}",
            url=f"{BRUTOS}/SICOR_SALDOS_{ano}.gz", secao=SEC_MICRO,
            tipo="microdado", usado=True,
            papel="Saldo devedor e vencido — base do dataset 'exposicao', que "
                  "converte área em risco em dinheiro em risco."
                  if ano >= 2025 else
                  "Série histórica de saldo, para tendência de inadimplência.",
            hash_url=f"{BRUTOS}/SICOR_SALDOS_{ano}.hash", pesado=True, anos=(ano,),
        ))
    return tuple(itens)


MICRODADOS: tuple[ArquivoBCB, ...] = (
    *_operacoes_por_ano(),
    *_saldos_por_ano(),
    _m("liberacao", "Liberação de recursos", "SICOR_LIBERACAO_RECURSOS.gz", SEC_MICRO,
       usado=True, papel="Quanto do crédito já foi desembolsado — capital "
                         "efetivamente exposto a perda hoje (dataset 'exposicao')."),
    _m("parcelas_desembolso", "Cronograma de desembolso", "SICOR_PARCELAS_DESEMBOLSO.gz", SEC_MICRO,
       usado=True, papel="Calendário de caixa: permite alertar antes do "
                         "vencimento, e não depois."),
    _m("desclassificacao", "Desclassificação", "sicor_desclassificacao.gz", SEC_MICRO,
       usado=True, papel="Remove da carteira monitorada as operações que "
                         "perderam enquadramento, evitando alerta indevido."),
    _m("cop_basico", "Proagro — pedido de cobertura (COP)", "SICOR_COP_BASICO.gz", SEC_MICRO,
       usado=True, papel="Histórico de acionamento do Proagro por evento e operação."),
    _m("parcelas_proagro", "Proagro — parcelas", "SICOR_PARCELAS_PROAGRO.gz", SEC_MICRO,
       usado=True, papel="Etapa final da cadeia: valor efetivamente coberto e "
                         "prazo até o pagamento."),
    _m("rcp_basico", "Proagro — relatório de comprovação de perdas (RCP)",
       "SICOR_RCP_BASICO.gz", SEC_MICRO,
       usado=True, papel="Perdas efetivamente comprovadas — base da sinistralidade histórica."),
    _m("sumula", "Proagro — súmula de julgamento", "SICOR_SUMULA_JULGAMENTO.gz", SEC_MICRO,
       usado=True, papel="Deferimento, indeferimento e instância — revela a "
                         "taxa de negativa e o motivo mais frequente, que vira "
                         "orientação preventiva na mensagem ao produtor."),
    _m("lista_renegociacao", "Renegociação — lista", "SICOR_LISTA_RENEGOCIACAO.gz", SEC_MICRO,
       usado=True, papel="Marca operações já renegociadas — estresse prévio "
                         "conhecido, com peso no escore financeiro."),
    _m("operacao_renegociacao", "Renegociação — operações",
       "SICOR_OPERACAO_BASICA_RENEGOCIACAO.gz", SEC_MICRO,
       usado=True, papel="Condições da operação renegociada."),
    _m("alteracao_fonte", "Alterações de fonte de recursos",
       "SICOR_LISTA_ALTERACAO_FONTE.gz", SEC_MICRO,
       usado=True, papel="Troca de funding ao longo da vida da operação — "
                         "muda taxa e enquadramento, e portanto o conteúdo "
                         "da comunicação financeira."),
)


# ==========================================================================
# 3. Microdados do crédito rural público
# ==========================================================================
def _glebas_por_ano() -> tuple[ArquivoBCB, ...]:
    return tuple(
        ArquivoBCB(
            chave=f"glebas_{ano}", nome=f"Glebas em WKT — {ano}",
            url=f"{BRUTOS}/sicor_glebas_wkt_{ano}.gz", secao=SEC_PUBLICO,
            tipo="microdado", usado=True,
            papel="Geometria das glebas financiadas — permite alerta em nível "
                  "de talhão, e não apenas de município."
                  if ano >= 2025 else
                  "Série histórica de geometria, para evolução da área "
                  "financiada por talhão.",
            hash_url=f"{BRUTOS}/SICOR_GLEBAS_WKT_{ano}.hash", pesado=True, anos=(ano,),
        )
        for ano in ANOS_GLEBAS
    )


PUBLICOS: tuple[ArquivoBCB, ...] = (
    _m("complemento_operacao", "Complemento às operações contratadas",
       "SICOR_COMPLEMENTO_OPERACAO_BASICA.gz", SEC_PUBLICO,
       usado=True,
       papel="Traz o CD_IBGE_MUNICIPIO — é o que georreferencia cada operação."),
    *_glebas_por_ano(),
    _m("propriedades", "Propriedades", "SICOR_PROPRIEDADES.gz", SEC_PUBLICO,
       usado=True, papel="Área total do imóvel, posse e CAR — define o porte "
                         "real do produtor e distingue arrendatário de "
                         "proprietário."),
    _m("mutuarios", "Mutuários", "SICOR_MUTUARIOS.gz", SEC_PUBLICO,
       papel="Não utilizado por decisão de privacidade (ver docs/privacidade.md)."),
    _m("lista_cooperados", "Lista de cooperados", "SICOR_LISTA_COOPERADOS.gz", SEC_PUBLICO,
       usado=True, papel="Explode a operação coletiva nos produtores "
                         "associados — é o que permite à cooperativa rebater "
                         "o alerta individualmente."),
    _m("complemento_cop", "Complemento ao pedido de cobertura",
       "SICOR_COMPLEMENTO_COP.gz", SEC_PUBLICO,
       usado=True, papel="Evento declarado no pedido de cobertura."),
    _m("complemento_rcp", "Complemento ao relatório de comprovação de perdas",
       "SICOR_COMPLEMENTO_RCP.gz", SEC_PUBLICO,
       usado=True, papel="Evento efetivamente comprovado na perícia."),
    _m("rcp_glebas_2015_2020", "Glebas da comprovação de perdas — 2015 a 2020",
       "SICOR_RCP_GLEBAS_2015_2020.gz", SEC_PUBLICO,
       usado=True, papel="Único dado público que georreferencia sinistro "
                         "comprovado em nível de talhão."),
    _m("rcp_glebas_2021", "Glebas da comprovação de perdas — a partir de 2021",
       "SICOR_RCP_GLEBAS_2021.gz", SEC_PUBLICO,
       usado=True, papel="Continuação da série de glebas periciadas."),
    _m("complemento_reneg", "Complemento aos dados de renegociação",
       "SICOR_COMPLEMENTO_OPERACAO_BASICA_RENEGOCIACAO.gz", SEC_PUBLICO,
       usado=True, papel="Município das operações renegociadas."),
)


# ==========================================================================
# 4. Recor/PGRO — microdados antigos (1983 a 2012)
# ==========================================================================
RECOR: tuple[ArquivoBCB, ...] = (
    *tuple(
        ArquivoBCB(
            chave=f"recor_operacao_{ano}", nome=f"Recor — operações contratadas em {ano}",
            url=f"{BRUTOS}/recor_operacao_{ano}.csv.gz", secao=SEC_RECOR,
            tipo="microdado", pesado=True, anos=(ano,), usado=True,
            papel="Série longa de 30 anos (opcional, ligada por bandeira no "
                  "ETL): dá profundidade histórica à recorrência de eventos. "
                  "O BCB adverte sobre a qualidade de 1983–1994 e o aviso é "
                  "repetido na interface.",
        )
        for ano in ANOS_RECOR
    ),
    ArquivoBCB("recor_cop_1983_2003", "Recor — pedidos de cobertura 1983–2003",
               f"{BRUTOS}/recor_cop_1983_2003.csv.gz", SEC_RECOR, "microdado",
               True, "Recorrência histórica de seca e excesso hídrico por UF — "
                     "permite dizer 'na sua região isso acontece a cada N anos'.",
               pesado=True),
    ArquivoBCB("recor_cop_2004_2012", "Recor — pedidos de cobertura 2004–2012",
               f"{BRUTOS}/recor_cop_2004_2012.csv.gz", SEC_RECOR, "microdado",
               True, "Continuação da série histórica de acionamento.",
               pesado=True),
    ArquivoBCB("recor_evento", "Recor — tabela de eventos",
               f"{BASE}/recor_evento_cop_proagro.csv", SEC_RECOR, "dominio",
               True, "Compatibiliza o vocabulário antigo de eventos com o do Sicor."),
    ArquivoBCB("recor_produto", "Recor — tabela de produtos",
               f"{BASE}/recor_produto.csv", SEC_RECOR, "dominio",
               True, "Compatibiliza os produtos antigos com o catálogo interno."),
    ArquivoBCB("recor_programa", "Recor — tabela de programas",
               f"{BASE}/recor_programa.csv", SEC_RECOR, "dominio",
               True, "Programas de crédito extintos, para leitura da série longa."),
    ArquivoBCB("recor_tipo_seguro", "Recor — tipo de seguro",
               f"{BASE}/recor_tipo_seguro.csv", SEC_RECOR, "dominio",
               True, "Evolução histórica da cobertura de risco."),
)


# ==========================================================================
# 5. Crédito rural contratado
# ==========================================================================
CONTRATADO: tuple[ArquivoBCB, ...] = (
    _m("operacao_contratada", "Operações contratadas (todas)",
       "SICOR_OPERACAO_BASICA_CONTRAT.gz", SEC_CONTRAT,
       usado=True,
       papel="Universo mais recente, incluindo operações ainda sem liberação — "
             "é a carteira 'viva' monitorada pelo AgroSentinela."),
    _m("complemento_contratada", "Complemento às operações contratadas",
       "SICOR_COMPLEMENTO_OPERACAO_BASICA_CONTRAT.gz", SEC_CONTRAT,
       usado=True, papel="Município das operações contratadas."),
    _m("parcelas_contratada", "Cronograma de desembolso (contratado)",
       "SICOR_PARCELAS_DESEMBOLSO_CONTRAT.gz", SEC_CONTRAT,
       usado=True, papel="Calendário de desembolso da carteira viva."),
    _m("glebas_contratada", "Glebas (contratado)", "SICOR_GLEBAS_CONTRAT.gz", SEC_CONTRAT,
       hash_=True, usado=True,
       papel="Geometria dos talhões da carteira viva — centroide de gleba "
             "para a consulta climática."),
    _m("propriedades_contratada", "Propriedades (contratado)",
       "SICOR_PROPRIEDADES_CONTRAT.gz", SEC_CONTRAT,
       usado=True, papel="Área e posse do imóvel na carteira viva."),
    _m("mutuarios_contratada", "Mutuários (contratado)",
       "SICOR_MUTUARIOS_CONTRAT.gz", SEC_CONTRAT,
       papel="Não utilizado por decisão de privacidade."),
)


# ==========================================================================
# Documentação
# ==========================================================================
DOCUMENTACAO: tuple[ArquivoBCB, ...] = (
    ArquivoBCB("manual_sicor", "Modelo e dicionário de dados do Sicor",
               f"{BASE}/manualDadosSicorCompleto.pdf", SEC_DOC, "documentacao",
               True, "Layout oficial dos arquivos .gz."),
    ArquivoBCB("manual_complementar", "Modelo e dicionário dos dados complementares",
               f"{BASE}/manualDadosComplementaresSicor_V2.pdf", SEC_DOC, "documentacao",
               True, "Layout dos arquivos complementares (município, glebas, RCP)."),
    ArquivoBCB("manual_recor", "Modelo e dicionário de dados do Recor",
               f"{BASE}/manualRecor_v2.pdf", SEC_DOC, "documentacao",
               True, "Layout dos arquivos históricos do Recor/PGRO."),
)


CATALOGO_BCB: tuple[ArquivoBCB, ...] = (
    *DOMINIOS, *MICRODADOS, *PUBLICOS, *CONTRATADO, *RECOR, *DOCUMENTACAO,
)

CATALOGO_POR_CHAVE: dict[str, ArquivoBCB] = {a.chave: a for a in CATALOGO_BCB}


# ==========================================================================
# Consultas
# ==========================================================================

def por_secao(secao: str) -> list[ArquivoBCB]:
    return [a for a in CATALOGO_BCB if a.secao == secao]


def usados() -> list[ArquivoBCB]:
    """Arquivos que alimentam diretamente a solução."""
    return [a for a in CATALOGO_BCB if a.usado]


def dominios_essenciais() -> list[ArquivoBCB]:
    """Tabelas de domínio necessárias para decodificar a carteira."""
    return [a for a in DOMINIOS if a.usado]


def microdados_essenciais(ano_inicio: int = 2024) -> list[ArquivoBCB]:
    """Microdados mínimos para montar a carteira e o histórico do Proagro."""
    chaves = {
        "complemento_operacao", "cop_basico", "rcp_basico",
        "complemento_cop", "complemento_rcp",
    }
    itens = [a for a in CATALOGO_BCB if a.chave in chaves]
    itens += [
        a for a in MICRODADOS
        if a.chave.startswith("operacao_") and a.anos and a.anos[0] >= ano_inicio
    ]
    return itens


def obter(chave: str) -> ArquivoBCB:
    if chave not in CATALOGO_POR_CHAVE:
        raise KeyError(f"Arquivo desconhecido no catálogo: {chave}")
    return CATALOGO_POR_CHAVE[chave]


def nao_usados() -> list[ArquivoBCB]:
    """
    Arquivos catalogados e **deliberadamente não consumidos**.

    Hoje são apenas os dois arquivos de mutuários, excluídos por decisão de
    privacidade: o AgroSentinela trabalha em nível de operação, gleba e
    município, e nunca lê dado pessoal identificável. Manter a decisão
    registrada no catálogo — em vez de apenas omitir os arquivos — é o que
    permite ao avaliador conferir que a exclusão foi uma escolha, e não um
    esquecimento.
    """
    return [a for a in CATALOGO_BCB if not a.usado]


def resumo() -> dict[str, int]:
    return {
        "total": len(CATALOGO_BCB),
        "dominios": len(DOMINIOS),
        "microdados": len(MICRODADOS),
        "publicos": len(PUBLICOS),
        "contratado": len(CONTRATADO),
        "recor": len(RECOR),
        "usados": len(usados()),
        "excluidos_por_privacidade": len(nao_usados()),
        "cobertura_pct": round(100 * len(usados()) / max(len(CATALOGO_BCB), 1), 1),
    }
