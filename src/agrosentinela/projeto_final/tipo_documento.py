"""
Que documento é este? Ramo do seguro e tipo de documento.

Lição dos documentos reais testados no projeto: nem todo PDF que chega como
"apólice" é uma apólice de D&O. Dois dos cinco documentos reais enviados para
teste eram apólices de **Seguro Garantia** (garantia de contrato). Sem esta
etapa, o pipeline lia o documento, não achava quase nenhuma cláusula de D&O e
gravava uma "apólice D&O" cheia de lacunas — um resultado errado com cara de
certo. Agora o documento fora do escopo é reconhecido e não entra na base de
comparação.

Também distinguimos **condições gerais** (o texto-padrão do produto,
registrado na SUSEP, sem valores nem tomadora) de **apólice emitida**
(com especificação: tomadora, vigência, limite, prêmio). As duas podem ser
comparadas cláusula a cláusula, mas só a apólice tem números.

Classificação por vocabulário, pesando mais o início do documento (capa,
título, frontispício). É determinística e auditável: devolve os sinais que
encontrou.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .documentos import sem_acentos

# Expressões por ramo (minúsculas, sem acento).
_RAMOS: dict[str, tuple[str, tuple[str, ...]]] = {
    "do": ("D&O (responsabilidade civil de administradores)", (
        "responsabilidade civil de administradores", "responsabilidade civil de diretores",
        "responsabilidade civil para administradores", "responsabilidade dos dirigentes",
        "administradores e diretores", "diretores e administradores", "d&o",
        "directors and officers", "directors & officers", "directors' and officers'",
        "seguro de responsabilidade civil de conselheiros")),
    "garantia": ("Seguro Garantia", (
        "seguro garantia", "apolice seguro garantia", "garantia judicial",
        "garantia de execucao", "garantia do licitante", "performance bond",
        "garantia de adiantamento de pagamento", "objeto da garantia", "valor da garantia")),
    "rc_profissional": ("RC Profissional / E&O", (
        "responsabilidade civil profissional", "erros e omissoes", "e&o")),
    "rc_geral": ("RC Geral", (
        "responsabilidade civil geral", "rc geral", "responsabilidade civil operacoes")),
    "patrimonial": ("Patrimonial / Riscos Nomeados", (
        "riscos nomeados", "riscos operacionais", "incendio, queda de raio",
        "seguro empresarial", "seguro residencial")),
    "rural": ("Seguro Rural (agrícola, pecuário, penhor)", (
        "seguro agricola", "penhor rural", "seguro pecuario", "subvencao ao premio",
        "seguro rural")),
    "vida": ("Vida / Acidentes Pessoais", ("seguro de vida", "acidentes pessoais")),
}

_TIPOS = {"condicoes_gerais": "Condições gerais (texto-padrão do produto, sem valores)",
          "apolice": "Apólice emitida / proposta (com especificação)"}


@dataclass
class TipoDocumento:
    ramo: str
    ramo_nome: str
    tipo: str
    tipo_nome: str
    pontuacao: dict[str, float] = field(default_factory=dict)
    sinais: list[str] = field(default_factory=list)

    @property
    def e_do(self) -> bool:
        return self.ramo == "do"

    def resumo(self) -> str:
        return f"{self.ramo_nome} · {self.tipo_nome}"

    def to_dict(self) -> dict:
        return {"ramo": self.ramo, "ramo_nome": self.ramo_nome, "tipo": self.tipo,
                "tipo_nome": self.tipo_nome, "pontuacao": self.pontuacao,
                "sinais": self.sinais}


def _baixo(texto: str) -> str:
    return " ".join(sem_acentos(texto).lower().split())


def classificar(texto: str, cadastro: dict | None = None) -> TipoDocumento:
    """Ramo e tipo do documento. ``cadastro`` (opcional) é o resultado da
    leitura do quadro-resumo: valores e vigência indicam apólice emitida."""
    t = _baixo(texto)
    inicio = t[:4000]
    pont: dict[str, float] = {}
    sinais: list[str] = []
    for ramo, (_, termos) in _RAMOS.items():
        total = 0.0
        for termo in termos:
            n, n0 = t.count(termo), inicio.count(termo)
            if n:
                total += min(n, 20) + 3 * min(n0, 3)
                sinais.append(f"{ramo}: “{termo}” ×{n}")
        pont[ramo] = total
    melhor = max(pont, key=pont.get)
    if pont[melhor] < 2:
        ramo = "desconhecido"
    elif pont.get("do", 0) >= 0.6 * pont[melhor]:
        # D&O costuma citar outros ramos (ex.: "concorrência com seguro
        # garantia"); só sai do escopo se outro ramo dominar com folga.
        ramo = "do"
    else:
        ramo = melhor
    ramo_nome = _RAMOS[ramo][0] if ramo in _RAMOS else "Ramo não identificado"

    cad = cadastro or {}
    tem_valores = any(cad.get(k) for k in ("lmg", "premio", "vigencia_inicio"))
    cg_no_titulo = "condicoes gerais" in inicio[:2500]
    tipo = "condicoes_gerais" if cg_no_titulo and not tem_valores else "apolice"
    return TipoDocumento(ramo, ramo_nome, tipo, _TIPOS[tipo],
                         {k: round(v, 1) for k, v in pont.items() if v}, sinais[:12])
