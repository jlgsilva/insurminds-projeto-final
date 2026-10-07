"""
Arquiteturas de documento — uma por seguradora simulada.

No mercado real, cada seguradora organiza a apólice à sua maneira: onde fica
o quadro de valores (no início, em tabela, em prosa, no fim), como as
cláusulas são numeradas (1.1.1, Cláusula 4ª, romanos, Item 7), se as
exclusões vêm uma por cláusula ou todas numa lista com alíneas, se há
glossário, se o texto é jurídico, simples ou bilíngue. Este módulo produz,
para a mesma especificação (gabarito), seis documentos estruturalmente
diferentes. O renderizador (scripts/gerar_apolices_simuladas.py) só desenha
os blocos.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .clausulas import CLAUSULAS
from .simulador import (
    AVISO_SIMULACAO, PERFIS_ROTULO, SEGURADORAS_POR_CODIGO, TOMADORAS_POR_CODIGO, EspecApolice,
    corpo_clausula, descricao_risco, formatar_data, formatar_valor, titulo_base,
)

_ROMANOS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII",
            "XIV", "XV", "XVI"]
_ORDINAIS = lambda n: f"{n}ª"  # noqa: E731


@dataclass
class Bloco:
    tipo: str                      # titulo_doc | subtitulo | aviso | secao | subsecao | par | item | tabela | caixa
    texto: str = ""
    titulo: str = ""               # para 'item' (alínea com título em linha)
    linhas: list[tuple[str, str]] = field(default_factory=list)   # tabela / caixa
    codigo: str = ""               # cláusula da taxonomia (gabarito; não vai ao documento)
    caixa_alta: bool = False


@dataclass
class DocumentoApolice:
    espec: EspecApolice
    blocos: list[Bloco]

    def texto(self) -> str:
        out: list[str] = []
        for b in self.blocos:
            if b.tipo in ("tabela", "caixa"):
                out += [f"{k}: {v}" if k else v for k, v in b.linhas]
            elif b.tipo == "item":
                out.append(f"{b.titulo}: {b.texto}")
            else:
                out.append(b.texto)
        return "\n".join(out)


# --------------------------------------------------------------------------
# utilidades
# --------------------------------------------------------------------------

def _fv(e: EspecApolice, v: float) -> str:
    return formatar_valor(v, SEGURADORAS_POR_CODIGO[e.seguradora_codigo].formato_valor)


def _fd(e: EspecApolice, d) -> str:
    return formatar_data(d, SEGURADORAS_POR_CODIGO[e.seguradora_codigo].formato_data)


def _retro(e: EspecApolice) -> str:
    return "Ilimitada" if e.retroatividade_ilimitada else _fd(e, e.retroatividade)


def _presentes(e: EspecApolice, codigos: list[str]) -> list[tuple[str, str]]:
    """Cláusulas presentes do grupo — exceto as que a apólice trata para EXCLUIR,
    que vão para a seção de exclusões (ver ``_exclusoes``)."""
    out = []
    for c in codigos:
        if not c.startswith("EXC") and e.avaliacoes.get(c) == "excluida":
            continue
        corpo = corpo_clausula(e, c)
        if corpo:
            out.append((c, corpo))
    return out


def _exclusoes(e: EspecApolice) -> list[tuple[str, str]]:
    """Exclusões gerais + coberturas que esta apólice exclui expressamente."""
    codigos = ["EXC-01", "EXC-02", "EXC-03", "EXC-04", "EXC-05"] + [
        c.codigo for c in CLAUSULAS
        if not c.codigo.startswith("EXC") and e.avaliacoes.get(c.codigo) == "excluida"]
    out = []
    for c in codigos:
        corpo = corpo_clausula(e, c)
        if corpo:
            out.append((c, corpo))
    return out


_MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "em", "a", "o", "à", "ao", "com", "por",
               "para", "na", "no", "ou", "sobre", "entre", "contra"}


_SIGLAS = {"LMG", "LMI", "D&O", "CVM", "BCB", "MAPA", "CAR", "LGPD", "POS", "EUA", "RJ", "DIC",
           "(RUN-OFF)", "SICOR,", "SICOR", "PROAGRO"}


def _tt(t: str) -> str:
    """Título em caixa de frase: preposições minúsculas, siglas e letras de cobertura preservadas."""
    palavras = t.replace("EXCLUSÃO — ", "").split()
    out = []
    for i, p in enumerate(palavras):
        low = p.lower()
        anterior = palavras[i - 1].lower() if i else ""
        if p.upper() in _SIGLAS:
            out.append(p.upper() if p.upper() not in ("(RUN-OFF)", "SICOR,", "SICOR", "PROAGRO")
                       else p.capitalize() if p.startswith("(") is False else "(Run-off)")
        elif len(p) == 1 and anterior in ("cobertura", "side", "garantia"):
            out.append(p.upper())
        elif i > 0 and low in _MINUSCULAS:
            out.append(low)
        else:
            out.append(low[:1].upper() + low[1:])
    return " ".join(out)


def _rng(e: EspecApolice) -> random.Random:
    return random.Random(e.semente)


def _cabecalho_padrao(e: EspecApolice, titulo: str, sub: str) -> list[Bloco]:
    return [Bloco("titulo_doc", titulo), Bloco("subtitulo", sub), Bloco("aviso", AVISO_SIMULACAO)]


# ==========================================================================
# 1. ATA — decimal com glossário (inspiração estrutural: C.G. AIG)
# ==========================================================================

def _modelo_decimal_glossario(e: EspecApolice) -> list[Bloco]:
    t = e.tomadora
    b = _cabecalho_padrao(e, "SEGURO DE RESPONSABILIDADE CIVIL DE ADMINISTRADORES (D&O)",
                          f"Apólice à Base de Reclamações com Notificação · nº {e.numero_apolice}")
    b.append(Bloco("secao", "ESPECIFICAÇÃO DA APÓLICE"))
    b.append(Bloco("tabela", linhas=[
        ("Seguradora", f"{e.seguradora} — CNPJ {e.seguradora_cnpj}"),
        ("Sociedade (Tomador)", f"{t} — CNPJ {e.tomadora_cnpj}"),
        ("Endereço da Sociedade", f"{e.municipio}/{e.uf}"),
        ("Período de Vigência", f"{_fd(e, e.vigencia_inicio)} a {_fd(e, e.vigencia_fim)}, às 24h"),
        ("Data de Retroatividade", _retro(e)),
        ("Limite Máximo de Garantia da Apólice (LMG)", _fv(e, e.lmg)),
        ("Franquia (Garantias B e C)", _fv(e, e.franquia)),
        ("Prêmio Total", _fv(e, e.premio)),
    ]))
    b += [Bloco("secao", "1. DEFINIÇÕES"),
          Bloco("par", "Para fins desta apólice: Ato Danoso é qualquer ato ou omissão culposa "
                "praticado pela Pessoa Segurada no exercício de suas funções; Reclamação é qualquer "
                "procedimento judicial, arbitral ou administrativo contra a Pessoa Segurada; Perda "
                "Indenizável compreende indenizações, acordos aprovados e Custos de Defesa; "
                "Partes Seguradas são as Pessoas Seguradas e a Sociedade."),
          Bloco("secao", "2. INFORMAÇÕES DO RISCO"), Bloco("par", descricao_risco(e)),
          Bloco("secao", "3. RISCOS COBERTOS — GARANTIA BÁSICA")]
    n = 0
    for c, corpo in _presentes(e, ["ESC-01", "ESC-02", "ESC-03", "ESC-04"]):
        n += 1
        b += [Bloco("subsecao", f"3.{n} {_tt(titulo_base(e, c))}", codigo=c),
              Bloco("par", corpo, codigo=c)]
    b.append(Bloco("secao", "4. EXTENSÕES DE COBERTURA"))
    n = 0
    for c, corpo in _presentes(e, ["DEF-02", "DEF-03", "DEF-05", "ESC-06", "TMP-04", "AGR-01",
                                   "AGR-02", "AGR-03", "LIM-03"]):
        n += 1
        b += [Bloco("subsecao", f"4.{n} Extensão — {_tt(titulo_base(e, c))}", codigo=c),
              Bloco("par", corpo, codigo=c)]
    b.append(Bloco("secao", "5. LIMITES, FRANQUIA E CUSTOS DE DEFESA"))
    n = 0
    for c, corpo in _presentes(e, ["LIM-01", "LIM-02", "LIM-04", "DEF-01", "OPE-04"]):
        n += 1
        b += [Bloco("subsecao", f"5.{n} {_tt(titulo_base(e, c))}", codigo=c),
              Bloco("par", corpo, codigo=c)]
    b.append(Bloco("secao", "6. EXCLUSÕES"))
    b.append(Bloco("par", "Esta apólice não cobre Perdas decorrentes de Reclamações:"))
    n = 0
    for c, corpo in _exclusoes(e):
        n += 1
        b += [Bloco("subsecao", f"6.{n} {_tt(titulo_base(e, c))}",
                    codigo=c), Bloco("par", corpo, codigo=c)]
    b.append(Bloco("secao", "7. VIGÊNCIA, RETROATIVIDADE E NOTIFICAÇÕES"))
    n = 0
    for c, corpo in _presentes(e, ["TMP-01", "TMP-02", "TMP-03"]):
        n += 1
        b += [Bloco("subsecao", f"7.{n} {_tt(titulo_base(e, c))}", codigo=c),
              Bloco("par", corpo, codigo=c)]
    b.append(Bloco("secao", "8. DISPOSIÇÕES GERAIS"))
    n = 0
    for c, corpo in _presentes(e, ["ESC-05", "DEF-04", "OPE-01", "OPE-02", "OPE-03", "OPE-05"]):
        n += 1
        b += [Bloco("subsecao", f"8.{n} {_tt(titulo_base(e, c))}", codigo=c),
              Bloco("par", corpo, codigo=c)]
    b.append(Bloco("par", "Ouvidoria e SAC conforme Condições Gerais. " + AVISO_SIMULACAO))
    return b


# ==========================================================================
# 2. IPE — cláusulas com romanos, exclusões em CAIXA ALTA (inspiração: Allianz)
# ==========================================================================

def _modelo_clausulas_romanos(e: EspecApolice) -> list[Bloco]:
    b = _cabecalho_padrao(e, "RESPONSABILIDADE CIVIL DE DIRETORES E ADMINISTRADORES DE EMPRESAS — D&O",
                          f"Condições Particulares · Apólice {e.numero_apolice} · emitida em "
                          f"{_fd(e, e.vigencia_inicio)}")
    b.append(Bloco("secao", "CONDIÇÕES PARTICULARES — DADOS DA APÓLICE"))
    for i, (k, v) in enumerate([
        ("Seguradora", f"{e.seguradora}, CNPJ {e.seguradora_cnpj}"),
        ("Empresa Tomadora", f"{e.tomadora}, inscrita no CNPJ sob o nº {e.tomadora_cnpj}"),
        ("Sede", f"município de {e.municipio}, Estado {e.uf}"),
        ("Vigência", f"das 24 horas de {_fd(e, e.vigencia_inicio)} às 24 horas de {_fd(e, e.vigencia_fim)}"),
        ("Data limite de retroatividade", _retro(e)),
        ("Limite Máximo de Garantia (LMG)", _fv(e, e.lmg)),
        ("Participação Obrigatória do Segurado (POS)", _fv(e, e.franquia)),
        ("Prêmio total", _fv(e, e.premio)),
    ], 1):
        b.append(Bloco("par", f"{i}. {k}: {v}."))
    b.append(Bloco("par", "Descrição do risco: " + descricao_risco(e)))
    cl = 0

    def clausula(titulo: str):
        nonlocal cl
        cl += 1
        b.append(Bloco("secao", f"CLÁUSULA {cl} – {titulo}"))

    clausula("OBJETO DO SEGURO")
    b.append(Bloco("par", "Garantir, até o LMG, o pagamento de Perdas decorrentes de Reclamações "
                          "contra o Segurado por Ato Danoso no exercício de cargo na Empresa."))
    clausula("PESSOAS SEGURADAS E COBERTURA BÁSICA")
    for i, (c, corpo) in enumerate(_presentes(e, ["ESC-01", "ESC-02", "ESC-03", "ESC-04"])):
        b.append(Bloco("item", corpo, titulo=f"{'ABCD'[i]}) {_tt(titulo_base(e, c))}", codigo=c))
    clausula("EXTENSÕES DE COBERTURA")
    for i, (c, corpo) in enumerate(_presentes(e, ["DEF-01", "DEF-02", "DEF-03", "DEF-05",
                                                  "ESC-06", "AGR-01", "AGR-02", "AGR-03"])):
        b.append(Bloco("item", corpo, titulo=f"{_ROMANOS[i]} – {_tt(titulo_base(e, c))}", codigo=c))
    clausula("RISCOS EXCLUÍDOS")
    for i, (c, corpo) in enumerate(_exclusoes(e)):
        b.append(Bloco("item", corpo.upper(), titulo=f"{_ROMANOS[i]} – "
                       f"{titulo_base(e, c).replace('EXCLUSÃO — ', '')}", codigo=c, caixa_alta=True))
    clausula("LIMITES, SUBLIMITES E POS")
    for c, corpo in _presentes(e, ["LIM-01", "LIM-02", "LIM-03", "LIM-04", "OPE-04"]):
        b += [Bloco("subsecao", _tt(titulo_base(e, c)), codigo=c), Bloco("par", corpo, codigo=c)]
    clausula("RETROATIVIDADE, PRAZO ADICIONAL E AVISO DE CIRCUNSTÂNCIAS")
    for c, corpo in _presentes(e, ["TMP-01", "TMP-02", "TMP-03", "TMP-04"]):
        b += [Bloco("subsecao", _tt(titulo_base(e, c)), codigo=c), Bloco("par", corpo, codigo=c)]
    clausula("DISPOSIÇÕES DIVERSAS")
    for c, corpo in _presentes(e, ["ESC-05", "DEF-04", "OPE-01", "OPE-02", "OPE-03", "OPE-05"]):
        b += [Bloco("subsecao", _tt(titulo_base(e, c)), codigo=c), Bloco("par", corpo, codigo=c)]
    b.append(Bloco("par", AVISO_SIMULACAO))
    return b


# ==========================================================================
# 3. JAC — hierárquico 1.1.1, especificação NO FIM, prazo complementar
# ==========================================================================

def _modelo_hierarquico_legado(e: EspecApolice) -> list[Bloco]:
    b = _cabecalho_padrao(e, "Seguro de Responsabilidade Civil de Administradores e Diretores — D&O",
                          "Apólice à Base de Reclamações com Cláusula de Notificações")
    secao = 0

    def nova(titulo: str) -> int:
        nonlocal secao
        secao += 1
        b.append(Bloco("secao", f"{secao}. {titulo}"))
        return secao

    s = nova("OBJETO DO SEGURO")
    b.append(Bloco("par", f"{s}.1 Este contrato garante o reembolso das quantias que o Segurado "
                          "for obrigado a pagar em razão de Reclamação por Ato Danoso, observado o "
                          "Limite Máximo de Indenização e a Especificação ao final deste documento."))
    s = nova("COBERTURAS BÁSICAS")
    for i, (c, corpo) in enumerate(_presentes(e, ["ESC-01", "ESC-02", "ESC-03", "ESC-04", "ESC-05"]), 1):
        b += [Bloco("subsecao", f"{s}.{i} {_tt(titulo_base(e, c))}", codigo=c),
              Bloco("par", f"{s}.{i}.1 {corpo}", codigo=c)]
    s = nova("COBERTURAS ADICIONAIS")
    for i, (c, corpo) in enumerate(_presentes(e, ["DEF-05", "AGR-01", "AGR-02", "AGR-03", "ESC-06",
                                                  "DEF-02", "DEF-03"]), 1):
        b += [Bloco("subsecao", f"{s}.{i} {_tt(titulo_base(e, c))}", codigo=c),
              Bloco("par", f"{s}.{i}.1 {corpo}", codigo=c)]
    s = nova("LIMITES E FRANQUIAS")
    for i, (c, corpo) in enumerate(_presentes(e, ["LIM-01", "LIM-02", "LIM-03", "LIM-04", "DEF-01",
                                                  "OPE-04"]), 1):
        b += [Bloco("subsecao", f"{s}.{i} {_tt(titulo_base(e, c))}", codigo=c),
              Bloco("par", f"{s}.{i}.1 {corpo}", codigo=c)]
    s = nova("RISCOS NÃO COBERTOS E PREJUÍZOS NÃO INDENIZÁVEIS")
    b.append(Bloco("par", f"{s}.1 Além dos riscos excluídos nas Condições Gerais, não estão cobertas "
                          "as Reclamações descritas a seguir:"))
    for i, (c, corpo) in enumerate(_exclusoes(e), 1):
        b += [Bloco("subsecao", f"{s}.1.{i} {_tt(titulo_base(e, c))}",
                    codigo=c), Bloco("par", corpo, codigo=c)]
    s = nova("PRAZOS DE COBERTURA")
    for i, (c, corpo) in enumerate(_presentes(e, ["TMP-01", "TMP-02", "TMP-03", "TMP-04"]), 1):
        titulo = "Prazo Complementar e Prazo Suplementar" if c == "TMP-02" else _tt(titulo_base(e, c))
        b += [Bloco("subsecao", f"{s}.{i} {titulo}", codigo=c), Bloco("par", corpo, codigo=c)]
    s = nova("CONDIÇÕES GERAIS APLICÁVEIS")
    for i, (c, corpo) in enumerate(_presentes(e, ["DEF-04", "OPE-01", "OPE-02", "OPE-03", "OPE-05"]), 1):
        b += [Bloco("subsecao", f"{s}.{i} {_tt(titulo_base(e, c))}", codigo=c),
              Bloco("par", corpo, codigo=c)]
    b.append(Bloco("secao", "ESPECIFICAÇÃO DA APÓLICE"))
    b.append(Bloco("tabela", linhas=[
        ("Apólice nº", e.numero_apolice),
        ("Seguradora", f"{e.seguradora} (CNPJ {e.seguradora_cnpj})"),
        ("Tomador", e.tomadora), ("CNPJ do Tomador", e.tomadora_cnpj),
        ("Município/UF", f"{e.municipio} — {e.uf}"),
        ("Início de Vigência", _fd(e, e.vigencia_inicio)),
        ("Término de Vigência", _fd(e, e.vigencia_fim)),
        ("Retroatividade", _retro(e)),
        ("Limite Máximo de Indenização (LMI)", _fv(e, e.lmg)),
        ("Franquia", _fv(e, e.franquia)),
        ("Prêmio Líquido + IOF", _fv(e, e.premio)),
        ("Atividade", f"{e.segmento} — {PERFIS_ROTULO[e.perfil]}"),
    ]))
    b.append(Bloco("aviso", AVISO_SIMULACAO))
    return b


# ==========================================================================
# 4. XIQ — "Cláusula 1ª…", abertura em prosa, cláusulas particulares rurais
# ==========================================================================

def _modelo_ordinal_prosa(e: EspecApolice) -> list[Bloco]:
    rng = _rng(e)
    b = _cabecalho_padrao(e, "XIQUE-XIQUE SEGURO DE RESPONSABILIDADE CIVIL PARA CONSELHEIROS, "
                          "DIRETORES E ADMINISTRADORES (D&O)", f"Apólice {e.numero_apolice}")
    b.append(Bloco("secao", "PREÂMBULO"))
    retro = ("sem limitação de data retroativa" if e.retroatividade_ilimitada
             else f"com data de retroatividade fixada em {_fd(e, e.retroatividade)}")
    b.append(Bloco("par",
        f"A {e.seguradora}, inscrita no CNPJ sob o nº {e.seguradora_cnpj}, emite a presente apólice "
        f"em favor da Tomadora {e.tomadora}, CNPJ {e.tomadora_cnpj}, com sede em {e.municipio}/{e.uf}, "
        f"vigente de {_fd(e, e.vigencia_inicio)} a {_fd(e, e.vigencia_fim)}, {retro}, garantindo "
        f"os Segurados até o Limite Máximo de Garantia de {_fv(e, e.lmg)}, mediante o pagamento do "
        f"prêmio total de {_fv(e, e.premio)} e observada a participação obrigatória do Segurado "
        f"(franquia) de {_fv(e, e.franquia)} por Reclamação."))
    b.append(Bloco("par", descricao_risco(e)))
    ordem = ["ESC-01", "ESC-02", "ESC-03", "ESC-04", "TMP-01", "TMP-02", "TMP-03", "LIM-01",
             "LIM-02", "LIM-03", "LIM-04", "DEF-01", "DEF-02", "DEF-03", "DEF-04", "DEF-05",
             "ESC-05", "ESC-06", "TMP-04", "OPE-01", "OPE-02", "OPE-03", "OPE-04", "OPE-05"]
    # a ordem das cláusulas varia entre apólices da mesma seguradora (versões de wording)
    if rng.random() < 0.5:
        ordem = ordem[4:11] + ordem[:4] + ordem[11:]
    n = 1
    b += [Bloco("secao", f"Cláusula {_ORDINAIS(n)} – Glossário"),
          Bloco("par", "Reclamação: pedido formal de reparação contra o Segurado. Reclamação "
                "contínua: reclamações com o mesmo fato gerador consideradas uma só. "
                "Divisibilidade: nenhum ato de um Segurado será imputado a outro.")]
    for c, corpo in _presentes(e, ordem):
        n += 1
        b += [Bloco("secao", f"Cláusula {_ORDINAIS(n)} – {_tt(titulo_base(e, c))}", codigo=c),
              Bloco("par", corpo, codigo=c)]
    n += 1
    b.append(Bloco("secao", f"Cláusula {_ORDINAIS(n)} – Riscos Excluídos"))
    b.append(Bloco("par", f"{n}.1 Além das exclusões das Condições Gerais, não estão cobertas:"))
    for i, (c, corpo) in enumerate(_exclusoes(e), 1):
        b.append(Bloco("item", corpo, titulo=f"{n}.1.{i} {_tt(titulo_base(e, c))}", codigo=c))
    agro = _presentes(e, ["AGR-01", "AGR-02", "AGR-03"])
    if agro:
        b.append(Bloco("secao", "CLÁUSULAS PARTICULARES RURAIS"))
        for i, (c, corpo) in enumerate(agro, 1):
            b += [Bloco("subsecao", f"Cláusula Particular Rural nº {i} – {_tt(titulo_base(e, c))}",
                        codigo=c), Bloco("par", corpo, codigo=c)]
    b.append(Bloco("par", AVISO_SIMULACAO))
    return b


# ==========================================================================
# 5. MUT — linguagem simples, perguntas e respostas
# ==========================================================================

PERGUNTAS = {
    "ESC-01": "Quem fica protegido por este seguro?",
    "ESC-02": "E se a cooperativa não puder pagar a defesa do dirigente?",
    "ESC-03": "A cooperativa recebe de volta o que adiantar ao dirigente?",
    "ESC-04": "A própria cooperativa também está coberta?",
    "ESC-05": "Vale para processos fora do Brasil?",
    "ESC-06": "E as outras empresas ligadas à cooperativa?",
    "LIM-01": "Até quanto o seguro paga?",
    "LIM-02": "Existem valores menores para algumas situações?",
    "LIM-03": "Se o dinheiro do seguro acabar, ele é renovado no mesmo ano?",
    "LIM-04": "Existe uma parte que a cooperativa paga primeiro?",
    "DEF-01": "As despesas com advogado diminuem o valor do seguro?",
    "DEF-02": "O seguro adianta o pagamento do advogado?",
    "DEF-03": "O dirigente pode escolher o próprio advogado?",
    "DEF-04": "O erro de um dirigente prejudica os outros?",
    "DEF-05": "E as multas aplicadas por órgãos do governo?",
    "TMP-01": "Fatos de antes da contratação estão cobertos?",
    "TMP-02": "E se o seguro não for renovado?",
    "TMP-03": "Posso avisar um problema antes de virar processo?",
    "TMP-04": "E se a cooperativa se fundir ou for incorporada?",
    "EXC-01": "E quando o dirigente agiu de má-fé?",
    "EXC-02": "E se a própria cooperativa processar o dirigente?",
    "EXC-03": "Problemas ambientais estão cobertos?",
    "EXC-04": "E vazamento de dados de cooperados?",
    "EXC-05": "Problemas que já eram conhecidos estão cobertos?",
    "OPE-01": "A seguradora pode cancelar o seguro?",
    "OPE-02": "Se houver discordância, como se resolve?",
    "OPE-03": "A seguradora pode cobrar do dirigente depois?",
    "OPE-04": "Se o dinheiro não der para todos, quem recebe primeiro?",
    "OPE-05": "Em que moeda são os valores?",
    "AGR-01": "Processos do Banco Central sobre crédito rural e Proagro estão cobertos?",
    "AGR-02": "E processos do Ibama ou do órgão ambiental do estado?",
    "AGR-03": "E se a cooperativa entrar em recuperação judicial?",
}


def _modelo_linguagem_simples(e: EspecApolice) -> list[Bloco]:
    b = [Bloco("titulo_doc", "Seu Seguro de Responsabilidade dos Dirigentes (D&O)"),
         Bloco("subtitulo", f"Mutirão Seguros Mútuos · apólice {e.numero_apolice}"),
         Bloco("aviso", AVISO_SIMULACAO),
         Bloco("secao", "RESUMO DO SEU SEGURO"),
         Bloco("caixa", linhas=[
             ("Quem contratou", f"{e.tomadora} (CNPJ {e.tomadora_cnpj}), {e.municipio}/{e.uf}"),
             ("Quem está protegido", "os dirigentes eleitos da cooperativa/associação"),
             ("Até quanto o seguro paga", f"{_fv(e, e.lmg)} no ano (valor máximo do seguro — LMG)"),
             ("Quanto custa", f"{_fv(e, e.premio)} por ano"),
             ("Parte que a cooperativa paga primeiro (franquia)", _fv(e, e.franquia)),
             ("Quando vale", f"de {_fd(e, e.vigencia_inicio)} até {_fd(e, e.vigencia_fim)}"),
             ("Fatos anteriores cobertos a partir de",
              "qualquer data (sem limite)" if e.retroatividade_ilimitada else _fd(e, e.retroatividade)),
         ]),
         Bloco("par", "Sobre a sua cooperativa: " + descricao_risco(e))]
    grupos = [
        ("O QUE ESTE SEGURO COBRE", ["ESC-01", "ESC-02", "ESC-03", "ESC-04", "DEF-05", "AGR-01",
                                    "AGR-02", "AGR-03", "ESC-05", "ESC-06"]),
        ("O QUE NÃO ESTÁ COBERTO", None),
        ("VALORES E LIMITES", ["LIM-01", "LIM-02", "LIM-03", "LIM-04", "DEF-01", "OPE-04"]),
        ("ADVOGADOS E DEFESA", ["DEF-02", "DEF-03", "DEF-04"]),
        ("PRAZOS", ["TMP-01", "TMP-02", "TMP-03", "TMP-04"]),
        ("OUTRAS REGRAS", ["OPE-01", "OPE-02", "OPE-03", "OPE-05"]),
    ]
    for titulo, cods in grupos:
        pres = _exclusoes(e) if cods is None else _presentes(e, cods)
        if not pres:
            continue
        b.append(Bloco("secao", titulo))
        for c, corpo in pres:
            b += [Bloco("subsecao", PERGUNTAS[c], codigo=c), Bloco("par", corpo, codigo=c)]
    b += [Bloco("secao", "COMO AVISAR UM PROBLEMA"),
          Bloco("par", "Assim que um dirigente receber notificação, intimação ou cobrança, avise a "
                       "Mutirão pelo canal do cooperado, com cópia do documento. Quanto antes, melhor."),
          Bloco("par", AVISO_SIMULACAO)]
    return b


# ==========================================================================
# 6. MIN — Policy Schedule bilíngue (mercado de Londres)
# ==========================================================================

EN = {
    "ESC-01": "Definition of Insured Person / Definição de Segurado",
    "ESC-02": "Insuring Agreement A — Non-Indemnifiable Loss / Side A",
    "ESC-03": "Insuring Agreement B — Company Reimbursement / Side B",
    "ESC-04": "Insuring Agreement C — Securities Claims / Side C",
    "ESC-05": "Territory and Jurisdiction / Territorialidade",
    "ESC-06": "Subsidiaries / Controladas",
    "LIM-01": "Limit of Liability / Limite Máximo de Garantia",
    "LIM-02": "Sublimits / Sublimites",
    "LIM-03": "Reinstatement / Reintegração",
    "LIM-04": "Retention / Franquia",
    "DEF-01": "Defence Costs / Custos de Defesa",
    "DEF-02": "Advancement of Defence Costs / Adiantamento",
    "DEF-03": "Choice of Counsel / Escolha do Advogado",
    "DEF-04": "Severability / Separabilidade",
    "DEF-05": "Fines and Penalties / Multas e Penalidades",
    "TMP-01": "Retroactive Date / Retroatividade",
    "TMP-02": "Extended Reporting Period / Prazo Adicional",
    "TMP-03": "Notice of Circumstances / Notificação de Circunstâncias",
    "TMP-04": "Change in Control / Mudança de Controle",
    "EXC-01": "Conduct / Conduta Dolosa",
    "EXC-02": "Insured vs Insured / Segurado contra Segurado",
    "EXC-03": "Pollution / Poluição",
    "EXC-04": "Cyber / Riscos Cibernéticos",
    "EXC-05": "Prior and Pending Litigation / Fatos Anteriores",
    "OPE-01": "Cancellation / Cancelamento",
    "OPE-02": "Dispute Resolution / Solução de Controvérsias",
    "OPE-03": "Subrogation / Sub-rogação",
    "OPE-04": "Order of Payments / Ordem de Pagamento",
    "OPE-05": "Currency / Moeda",
    "AGR-01": "Brazil Rural Credit Regulatory Extension / Crédito Rural e Proagro",
    "AGR-02": "Environmental Defence Costs (Rural) / Defesa Ambiental Rural",
    "AGR-03": "Insolvency and Judicial Recovery / Recuperação Judicial",
}


def _modelo_schedule_bilingue(e: EspecApolice) -> list[Bloco]:
    b = _cabecalho_padrao(e, "DIRECTORS AND OFFICERS LIABILITY — POLICY WORDING / APÓLICE D&O",
                          f"Policy No. / Apólice nº {e.numero_apolice}")
    b.append(Bloco("secao", "POLICY SCHEDULE / ESPECIFICAÇÃO"))
    b.append(Bloco("tabela", linhas=[
        ("Item 1 — Insurer / Seguradora", f"{e.seguradora} (CNPJ {e.seguradora_cnpj})"),
        ("Item 2 — Named Insured / Companhia Tomadora", f"{e.tomadora} (CNPJ {e.tomadora_cnpj})"),
        ("Item 3 — Principal Address / Sede", f"{e.municipio}, {e.uf}, Brazil"),
        ("Item 4 — Policy Period / Vigência", f"{_fd(e, e.vigencia_inicio)} to {_fd(e, e.vigencia_fim)}"),
        ("Item 5 — Limit of Liability / Limite (LMG)", f"{_fv(e, e.lmg)} in the aggregate"),
        ("Item 6 — Retention / Franquia", f"{_fv(e, e.franquia)} each Claim (Sides B and C)"),
        ("Item 7 — Continuity / Retroactive Date", "Unlimited / Ilimitada" if e.retroatividade_ilimitada
         else _fd(e, e.retroatividade)),
        ("Item 8 — Premium / Prêmio", _fv(e, e.premio)),
        ("Item 9 — Business Description / Atividade", f"{e.segmento} ({PERFIS_ROTULO[e.perfil]})"),
    ]))
    b.append(Bloco("par", "Underwriting information / Informações de subscrição: " + descricao_risco(e)))
    secoes = [
        ("SECTION 1 — INSURING AGREEMENTS / COBERTURAS", ["ESC-01", "ESC-02", "ESC-03", "ESC-04"]),
        ("SECTION 2 — EXTENSIONS / EXTENSÕES", ["DEF-01", "DEF-02", "DEF-03", "DEF-05", "ESC-05",
                                               "ESC-06", "TMP-04", "LIM-03"]),
        ("SECTION 3 — LIMITS AND RETENTION / LIMITES", ["LIM-01", "LIM-02", "LIM-04", "OPE-04"]),
    ]
    for titulo, cods in secoes:
        b.append(Bloco("secao", titulo))
        for i, (c, corpo) in enumerate(_presentes(e, cods), 1):
            b.append(Bloco("item", corpo, titulo=f"({chr(96 + i)}) {EN[c]}", codigo=c))
    b.append(Bloco("secao", "SECTION 4 — EXCLUSIONS / EXCLUSÕES"))
    for i, (c, corpo) in enumerate(_exclusoes(e), 1):
        b.append(Bloco("item", corpo, titulo=f"({chr(96 + i)}) {EN[c]}", codigo=c))
    b.append(Bloco("secao", "SECTION 5 — CONDITIONS / CONDIÇÕES"))
    for i, (c, corpo) in enumerate(_presentes(e, ["TMP-01", "TMP-02", "TMP-03", "DEF-04", "OPE-01",
                                                  "OPE-02", "OPE-03", "OPE-05"]), 1):
        b.append(Bloco("item", corpo, titulo=f"5.{i} {EN[c]}", codigo=c))
    agro = _presentes(e, ["AGR-01", "AGR-02", "AGR-03"])
    if agro:
        b.append(Bloco("secao", "ENDORSEMENTS / ENDOSSOS"))
        for i, (c, corpo) in enumerate(agro, 1):
            b += [Bloco("subsecao", f"Endorsement No. {i} / Endosso nº {i} — {EN[c]}", codigo=c),
                  Bloco("par", corpo, codigo=c)]
    b.append(Bloco("aviso", "This wording is SIMULATED for academic purposes. " + AVISO_SIMULACAO))
    return b


MODELOS = {
    "decimal_glossario": _modelo_decimal_glossario,
    "clausulas_romanos": _modelo_clausulas_romanos,
    "hierarquico_legado": _modelo_hierarquico_legado,
    "ordinal_prosa": _modelo_ordinal_prosa,
    "linguagem_simples": _modelo_linguagem_simples,
    "schedule_bilingue": _modelo_schedule_bilingue,
}


def montar_documento(espec: EspecApolice) -> DocumentoApolice:
    return DocumentoApolice(espec, MODELOS[espec.modelo_documento](espec))


def codigos_presentes(doc: DocumentoApolice) -> set[str]:
    return {b.codigo for b in doc.blocos if b.codigo}
