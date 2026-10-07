"""
Taxonomia de cláusulas de uma apólice de D&O (Directors & Officers).

Comparar apólices lendo o texto de ponta a ponta não escala e não é auditável:
duas seguradoras escrevem a mesma coisa de formas diferentes, e a diferença
que importa quase nunca está onde a linguagem chama atenção. O caminho é
reduzir cada apólice a uma **grade fixa de cláusulas**, e comparar a grade.

Esta grade foi montada a partir da estrutura usual do produto no mercado
brasileiro — regulado hoje pela Circular SUSEP nº 637/2021, que consolidou as
regras dos seguros de responsabilidade civil (revogando, entre outras, a
Circular 553/2017, específica de D&O) — e do que efetivamente decide um
sinistro. Para manter a linha de pesquisa do projeto (crédito e seguro
rural), a grade ganhou um grupo próprio de **riscos do agronegócio**: o
administrador de cooperativa de crédito rural, de usina ou de trading responde
por temas que um D&O "de prateleira" não trata.

Três decisões de modelagem, cada uma com motivo:

1. **Peso por criticidade, não por quantidade.** Uma apólice pode vencer em
   quinze cláusulas irrelevantes e perder em "custos de defesa fora do LMG" —
   e ainda assim ser a pior. O escore é ponderado.

2. **"Ausente" é diferente de "restrito".** Uma cláusula que a apólice não
   menciona não é o mesmo que uma cláusula que ela menciona para restringir.
   Silêncio costuma ser resolvido contra o segurado no sinistro, então
   ``ausente`` recebe tratamento próprio e aparece nas lacunas.

3. **Nenhuma cláusula é avaliada por "boa" ou "ruim" isoladamente.** O que a
   comparação produz é *diferença* entre apólices, com a leitura de quem
   ganha o quê. A recomendação final é de quem contrata — este é um sistema
   de apoio, não um parecer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------
# Grupos
# --------------------------------------------------------------------------

G_ESCOPO = "Escopo da cobertura"
G_LIMITES = "Limites e valores"
G_DEFESA = "Defesa e custos"
G_TEMPO = "Vigência e prazos"
G_EXCLUSOES = "Exclusões"
G_OPERACAO = "Operação do contrato"
G_AGRO = "Riscos do agronegócio"

GRUPOS_CLAUSULA: tuple[str, ...] = (
    G_ESCOPO, G_LIMITES, G_DEFESA, G_TEMPO, G_EXCLUSOES, G_OPERACAO, G_AGRO,
)

# Níveis de atendimento de uma cláusula em uma apólice concreta.
NIVEIS: dict[str, float] = {
    "ampla": 1.00,        # cobre integralmente, sem condicionantes relevantes
    "padrao": 0.70,       # cobre nos termos usuais de mercado
    "restrita": 0.40,     # cobre com sublimite, condição ou carência relevante
    "ausente": 0.00,      # a apólice não trata do tema
    "excluida": 0.00,     # a apólice trata para excluir
}

ROTULO_NIVEL: dict[str, str] = {
    "ampla": "Ampla",
    "padrao": "Padrão de mercado",
    "restrita": "Restrita",
    "ausente": "Não mencionada",
    "excluida": "Excluída",
}


@dataclass(frozen=True)
class Clausula:
    codigo: str
    nome: str
    grupo: str
    peso: int                 # 1 a 5 — quanto pesa no escore final
    porque_importa: str
    pergunta: str             # o que procurar no texto da apólice
    sinal_de_alerta: str = ""  # o que costuma passar despercebido
    base_legal: str = ""
    critica: bool = False

    def to_row(self) -> dict[str, Any]:
        return {
            "código": self.codigo,
            "cláusula": self.nome,
            "grupo": self.grupo,
            "peso": self.peso,
            "crítica": "sim" if self.critica else "—",
            "por que importa": self.porque_importa,
            "o que procurar": self.pergunta,
        }


CLAUSULAS: tuple[Clausula, ...] = (
    # ------------------------------------------------------ escopo
    Clausula(
        "ESC-01", "Definição de segurado", G_ESCOPO, 5,
        porque_importa="Define **quem** está protegido. Apólices variam muito "
                       "em incluir conselheiros de administração e fiscal, "
                       "procuradores, administradores de fato, cônjuge, "
                       "herdeiros e espólio.",
        pergunta="A definição alcança administradores de fato, conselho "
                 "fiscal, procuradores com poderes de gestão, cônjuge/"
                 "companheiro e espólio?",
        sinal_de_alerta="Exclusão silenciosa do administrador de fato é a "
                        "lacuna mais comum — e alcança justamente quem mais "
                        "decide sem ter cargo formal.",
        critica=True,
    ),
    Clausula(
        "ESC-02", "Side A — administrador não indenizado", G_ESCOPO, 5,
        porque_importa="É a proteção pessoal do administrador quando a empresa "
                       "não pode ou não quer indenizá-lo (insolvência, recusa, "
                       "vedação legal). Sem ela, o patrimônio pessoal responde.",
        pergunta="Há cobertura Side A? Existe limite adicional dedicado "
                 "(Side A DIC/Excess)?",
        critica=True,
    ),
    Clausula(
        "ESC-03", "Side B — reembolso à companhia", G_ESCOPO, 3,
        porque_importa="Reembolsa a empresa pelo que ela adiantou ao "
                       "administrador. Protege o caixa da companhia.",
        pergunta="O reembolso está previsto e sujeito a qual franquia?",
    ),
    Clausula(
        "ESC-04", "Side C — cobertura da pessoa jurídica", G_ESCOPO, 3,
        porque_importa="Cobre a própria companhia em reclamações de valores "
                       "mobiliários. Relevante para empresa de capital aberto; "
                       "também consome o mesmo limite, competindo com o Side A.",
        pergunta="Há Side C? Compartilha o LMG com o Side A?",
        sinal_de_alerta="Side C partilhando limite com Side A pode esvaziar a "
                        "proteção pessoal justamente na crise que gera as duas "
                        "reclamações ao mesmo tempo.",
    ),
    Clausula(
        "ESC-05", "Âmbito geográfico e jurisdicional", G_ESCOPO, 4,
        porque_importa="Reclamação no exterior é cara e frequente em empresa "
                       "com investidor ou operação fora do país.",
        pergunta="A cobertura é mundial? Há exclusão de jurisdição "
                 "norte-americana (USA/Canadá)?",
        critica=True,
    ),
    Clausula(
        "ESC-06", "Cobertura de subsidiárias e controladas", G_ESCOPO, 3,
        porque_importa="Define se o grupo inteiro está protegido e o que "
                       "acontece com empresas adquiridas durante a vigência.",
        pergunta="Há inclusão automática de novas controladas? Até que "
                 "percentual de participação ou porte?",
    ),

    # ----------------------------------------------------- limites
    Clausula(
        "LIM-01", "Limite Máximo de Garantia (LMG)", G_LIMITES, 5,
        porque_importa="O teto de tudo. Comparar prêmio sem comparar LMG é "
                       "comparar preços de coisas diferentes.",
        pergunta="Qual o LMG agregado por vigência? É por reclamação ou "
                 "agregado?",
        critica=True,
    ),
    Clausula(
        "LIM-02", "Sublimites por cobertura", G_LIMITES, 4,
        porque_importa="Sublimite baixo em uma cobertura muito acionada "
                       "(multas administrativas, custos de defesa) torna o LMG "
                       "grande apenas nominal.",
        pergunta="Quais coberturas têm sublimite e de quanto?",
        sinal_de_alerta="LMG alto com sublimite de 10% para o risco que mais "
                        "acontece é o truque mais comum de precificação.",
        critica=True,
    ),
    Clausula(
        "LIM-03", "Reintegração do limite", G_LIMITES, 4,
        porque_importa="Um sinistro grande pode esgotar o LMG no primeiro "
                       "semestre e deixar o resto da vigência descoberto.",
        pergunta="Há reintegração? Automática ou mediante prêmio adicional? "
                 "Quantas vezes?",
    ),
    Clausula(
        "LIM-04", "Franquia / participação obrigatória", G_LIMITES, 3,
        porque_importa="Franquia alta em Side B pode inviabilizar o "
                       "acionamento em reclamações menores, que são a maioria.",
        pergunta="Há franquia? Aplica-se também ao Side A? (Não deveria.)",
        sinal_de_alerta="Franquia incidindo sobre Side A descaracteriza a "
                        "proteção pessoal do administrador.",
    ),

    # -------------------------------------------------- defesa
    Clausula(
        "DEF-01", "Custos de defesa dentro ou fora do LMG", G_DEFESA, 5,
        porque_importa="Em D&O, a maior parte do dinheiro sai em honorários, "
                       "não em condenação. Custos **dentro** do LMG corroem a "
                       "indenização; **fora** preservam.",
        pergunta="Os custos de defesa são adicionais ao LMG ou nele contidos?",
        sinal_de_alerta="É a diferença que mais muda o resultado prático da "
                        "apólice e a que menos aparece na proposta comercial.",
        critica=True,
    ),
    Clausula(
        "DEF-02", "Adiantamento de custos de defesa", G_DEFESA, 5,
        porque_importa="Sem adiantamento, o administrador precisa pagar a "
                       "defesa do próprio bolso e esperar o reembolso — que "
                       "pode levar anos.",
        pergunta="Há adiantamento? Em que prazo após a notificação?",
        critica=True,
    ),
    Clausula(
        "DEF-03", "Livre escolha do advogado", G_DEFESA, 3,
        porque_importa="Define se o administrador escolhe a própria defesa ou "
                       "aceita a lista da seguradora — que pode ter conflito "
                       "de interesse com a companhia.",
        pergunta="A escolha do patrono é livre ou sujeita à anuência prévia?",
    ),
    Clausula(
        "DEF-04", "Cláusula de separabilidade (severability)", G_DEFESA, 4,
        porque_importa="Impede que a conduta de um administrador contamine a "
                       "cobertura dos demais — e que uma declaração incorreta "
                       "na proposta anule a apólice para todos.",
        pergunta="A separabilidade alcança as declarações da proposta e as "
                 "exclusões de conduta?",
        critica=True,
    ),
    Clausula(
        "DEF-05", "Multas e penalidades administrativas", G_DEFESA, 4,
        porque_importa="CVM, CADE, ANPD (LGPD), Bacen e órgãos ambientais são "
                       "hoje a origem mais frequente de exposição de "
                       "administrador no Brasil.",
        pergunta="Multas administrativas são cobertas? Com que sublimite? "
                 "Há exclusão de multa de natureza pessoal e intransferível?",
        base_legal="Lei 6.404/76; Lei 13.709/2018 (LGPD); Lei 12.846/2013.",
        critica=True,
    ),

    # ------------------------------------------------------ tempo
    Clausula(
        "TMP-01", "Retroatividade", G_TEMPO, 5,
        porque_importa="D&O é à base de reclamações: cobre o que for reclamado "
                       "na vigência, por ato praticado após a data de "
                       "retroatividade. Retroatividade curta deixa décadas de "
                       "gestão descobertas.",
        pergunta="Qual a data de retroatividade? É ilimitada ou a partir de "
                 "data específica?",
        critica=True,
    ),
    Clausula(
        "TMP-02", "Prazo adicional (antigo complementar/suplementar)", G_TEMPO, 4,
        porque_importa="Após o término da apólice, reclamações ainda chegam. "
                       "Sem prazo estendido, o ex-administrador fica exposto "
                       "justamente quando não controla mais a renovação.",
        pergunta="Há prazo adicional automático e gratuito? Qual a duração "
                 "do prazo adicional opcional e a que custo?",
        base_legal="Circular SUSEP 637/2021 (unificou os prazos complementar "
                   "e suplementar no conceito de prazo adicional).",
        critica=True,
    ),
    Clausula(
        "TMP-03", "Notificação de circunstâncias", G_TEMPO, 4,
        porque_importa="Permite travar a cobertura de um fato que ainda não "
                       "virou reclamação. É o que salva a cobertura quando o "
                       "problema aparece perto do fim da vigência.",
        pergunta="A apólice aceita notificação de circunstância? Em que prazo "
                 "após o conhecimento?",
    ),
    Clausula(
        "TMP-04", "Run-off em mudança de controle", G_TEMPO, 3,
        porque_importa="Em fusão, aquisição ou fechamento de capital, a apólice "
                       "costuma congelar. Sem run-off contratado, os atos "
                       "anteriores ficam sem quem responda.",
        pergunta="Há previsão de run-off? Por quantos anos e mediante que "
                 "prêmio?",
    ),

    # -------------------------------------------------- exclusões
    Clausula(
        "EXC-01", "Conduta dolosa e ato fraudulento", G_EXCLUSOES, 5,
        porque_importa="Exclusão legítima e universal. O que varia — e decide "
                       "o sinistro — é **quando** ela passa a valer: por "
                       "alegação, ou só após decisão judicial final.",
        pergunta="A exclusão exige sentença transitada em julgado? Os custos "
                 "de defesa são reembolsados até lá?",
        sinal_de_alerta="Exclusão que opera por mera alegação torna a apólice "
                        "quase inútil: toda ação começa alegando dolo.",
        base_legal="Art. 762 do Código Civil.",
        critica=True,
    ),
    Clausula(
        "EXC-02", "Reclamações entre segurados", G_EXCLUSOES, 3,
        porque_importa="A empresa processando o próprio administrador é "
                       "cenário comum após troca de gestão.",
        pergunta="Há exceções à exclusão (ação derivada de acionistas, "
                 "administrador judicial, jurisdição estrangeira)?",
    ),
    Clausula(
        "EXC-03", "Danos ambientais e poluição", G_EXCLUSOES, 3,
        porque_importa="Em empresa do agronegócio e da indústria, a "
                       "responsabilidade pessoal do administrador por dano "
                       "ambiental é risco concreto e crescente.",
        pergunta="A exclusão alcança a defesa do administrador ou apenas a "
                 "reparação do dano?",
        base_legal="Lei 9.605/98 (responsabilidade penal ambiental).",
    ),
    Clausula(
        "EXC-04", "Cibernético e vazamento de dados", G_EXCLUSOES, 3,
        porque_importa="Falha de governança de dados hoje gera reclamação "
                       "contra administrador, não só contra a empresa.",
        pergunta="Há exclusão cibernética ampla? Ela alcança a falha de "
                 "supervisão do administrador?",
        base_legal="LGPD, art. 42 e seguintes.",
    ),
    Clausula(
        "EXC-05", "Fatos conhecidos e anteriores", G_EXCLUSOES, 4,
        porque_importa="Exclui o que já se sabia na contratação. A redação "
                       "define se basta o conhecimento de **qualquer** pessoa "
                       "da empresa ou apenas de quem assinou a proposta.",
        pergunta="O conhecimento é imputado a quem? Há data de corte objetiva?",
        critica=True,
    ),

    # --------------------------------------------------- operação
    Clausula(
        "OPE-01", "Cancelamento e rescisão", G_OPERACAO, 3,
        porque_importa="Cancelamento unilateral pela seguradora no meio de uma "
                       "crise deixa o administrador sem defesa.",
        pergunta="Em que hipóteses a seguradora pode cancelar? Há prazo de "
                 "aviso prévio?",
    ),
    Clausula(
        "OPE-02", "Arbitragem e foro", G_OPERACAO, 2,
        porque_importa="Define onde e como se discute a negativa de cobertura. "
                       "Arbitragem é rápida e cara; judiciário é lento e barato.",
        pergunta="Há cláusula compromissória? A câmara arbitral é indicada?",
    ),
    Clausula(
        "OPE-03", "Sub-rogação contra segurados", G_OPERACAO, 2,
        porque_importa="Seguradora que se sub-roga contra o próprio "
                       "administrador esvazia a proteção que vendeu.",
        pergunta="Há renúncia expressa à sub-rogação contra os segurados?",
    ),
    Clausula(
        "OPE-04", "Ordem de pagamento das coberturas", G_OPERACAO, 4,
        porque_importa="Quando o limite é insuficiente, define quem recebe "
                       "primeiro. A ordem correta paga o Side A antes da "
                       "companhia — do contrário a pessoa física fica por último.",
        pergunta="Há cláusula de prioridade de pagamento (order of payments) "
                 "em favor do Side A?",
        critica=True,
    ),
    Clausula(
        "OPE-05", "Idioma, moeda e correção do limite", G_OPERACAO, 2,
        porque_importa="LMG em moeda estrangeira sem critério de conversão "
                       "gera disputa no pior momento.",
        pergunta="Qual a moeda do limite e o critério de conversão na data do "
                 "sinistro?",
    ),
)



CLAUSULAS_AGRO: tuple[Clausula, ...] = (
    Clausula(
        "AGR-01", "Atos de gestão em crédito rural e Proagro", G_AGRO, 4,
        porque_importa="Em cooperativas de crédito, bancos e agroindústrias "
                       "que repassam crédito rural, o administrador responde "
                       "perante o Banco Central por desvio de finalidade, "
                       "enquadramento indevido no Proagro e falhas de registro "
                       "no Sicor. É a exposição regulatória típica do agro.",
        pergunta="A apólice cobre reclamações e processos administrativos do "
                 "BCB/MAPA ligados ao Manual de Crédito Rural (MCR), ao Sicor "
                 "e ao Proagro? Há sublimite?",
        sinal_de_alerta="Exclusão genérica de 'atividade financeira' pode "
                        "eliminar justamente a cobertura do crédito rural "
                        "repassado pela cooperativa.",
        base_legal="Lei 4.829/65; Manual de Crédito Rural (MCR/BCB); "
                   "Lei 13.506/2017 (processo administrativo sancionador BCB).",
        critica=True,
    ),
    Clausula(
        "AGR-02", "Responsabilidade ambiental do administrador rural", G_AGRO, 4,
        porque_importa="Desmatamento em fornecedor, embargo do Ibama, CAR "
                       "irregular e queimada alcançam o administrador pessoalmente "
                       "— inclusive na esfera penal. Diferente da exclusão de "
                       "poluição (EXC-03), aqui se pergunta se há cobertura "
                       "positiva para a defesa.",
        pergunta="Há cobertura expressa para custos de defesa em processos "
                 "ambientais (Ibama, órgãos estaduais, MP) envolvendo a cadeia "
                 "de fornecimento rural, CAR e embargos?",
        base_legal="Lei 12.651/2012 (Código Florestal); Lei 9.605/98; "
                   "Decreto 6.514/2008.",
    ),
    Clausula(
        "AGR-03", "Recuperação judicial e insolvência no agro", G_AGRO, 3,
        porque_importa="Recuperações judiciais de produtores e agroindústrias "
                       "cresceram com a Lei 14.112/2020. O administrador de "
                       "empresa em RJ é alvo frequente de credores, do "
                       "administrador judicial e de ações de responsabilidade.",
        pergunta="A apólice mantém cobertura (sobretudo Side A) após pedido de "
                 "recuperação judicial ou falência da tomadora? Há exclusão de "
                 "insolvência?",
        base_legal="Lei 11.101/2005, alterada pela Lei 14.112/2020.",
    ),
)

CLAUSULAS = CLAUSULAS + CLAUSULAS_AGRO

CLAUSULAS_POR_CODIGO: dict[str, Clausula] = {c.codigo: c for c in CLAUSULAS}


def clausulas_do_grupo(grupo: str) -> list[Clausula]:
    return [c for c in CLAUSULAS if c.grupo == grupo]


def criticas() -> list[Clausula]:
    """
    Cláusulas que, sozinhas, mudam o resultado de um sinistro.

    A comparação destaca estas separadamente: uma apólice pode ganhar no
    escore geral e perder em todas as críticas — e nesse caso o escore geral
    está mentindo.
    """
    return [c for c in CLAUSULAS if c.critica]


def peso_total(apenas_criticas: bool = False) -> int:
    fonte = criticas() if apenas_criticas else CLAUSULAS
    return sum(c.peso for c in fonte)


def tabela() -> list[dict[str, Any]]:
    return [c.to_row() for c in CLAUSULAS]


def resumo() -> dict[str, Any]:
    return {
        "clausulas": len(CLAUSULAS),
        "criticas": len(criticas()),
        "grupos": len(GRUPOS_CLAUSULA),
        "peso_total": peso_total(),
        "peso_critico": peso_total(apenas_criticas=True),
        "niveis_de_atendimento": list(NIVEIS),
    }
