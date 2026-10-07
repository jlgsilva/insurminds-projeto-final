"""Objetos de domínio que trafegam entre os agentes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .personas import PESO_SEVERIDADE, setor_da_persona


def _id_curto(*partes: Any) -> str:
    bruto = "|".join(str(p) for p in partes)
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()[:10].upper()


@dataclass
class Alerta:
    """
    Um alerta é a decisão de que **uma operação específica** está exposta a
    **um evento climático específico** em um horizonte definido.

    Guarda tudo que é necessário para (a) explicar a decisão, (b) redigir a
    mensagem e (c) auditar depois.
    """

    # identificação
    id: str
    ref_bacen: str
    nu_ordem: int

    # território
    cd_ibge: int
    municipio: str
    uf: str
    regiao: str
    lat: float
    lon: float
    cell_id: str

    # lavoura / operação
    cultura: str
    produto: str
    fase: str
    fase_nome: str
    recomendacao_fase: str
    area_ha: float
    valor_credito: float
    programa: str
    instituicao: str
    tipo_seguro: str
    tem_cobertura: bool
    irrigada: bool
    dias_para_colheita: float | None
    dias_para_vencimento: float | None
    persona: str

    # evento e decisão
    evento: str
    evento_nome: str
    severidade: str
    score: float
    dia_pico: str
    janela_acao_h: int
    cobertura_proagro_evento: bool
    acionamentos: list[dict[str, Any]] = field(default_factory=list)
    indicadores: dict[str, Any] = field(default_factory=dict)
    historico_municipio: dict[str, Any] = field(default_factory=dict)
    contexto_externo: dict[str, Any] = field(default_factory=dict)
    """
    Fatos vindos de fontes externas gratuitas e públicas — perda estimada em
    reais (IBGE/PAM + CONAB), aderência ao Zarc, proteção do município
    (Proagro + PSR) e anomalia climática (NASA POWER).

    Tudo aqui é determinístico e conferível. O redator **usa** estes números;
    nunca os inventa. Campos sem fonte disponível saem vazios em vez de
    aproximados: é o que separa uma mensagem que o produtor pode levar ao
    banco de uma que ele não pode.
    """
    criado_em: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def severidade_peso(self) -> int:
        return PESO_SEVERIDADE.get(self.severidade, 1)

    @property
    def regras(self) -> list[str]:
        return [a.get("regra_id", "") for a in self.acionamentos]

    @property
    def acoes_recomendadas(self) -> list[str]:
        vistas: list[str] = []
        for a in self.acionamentos:
            acao = (a.get("acao") or "").strip()
            if acao and acao not in vistas:
                vistas.append(acao)
        return vistas

    def to_row(self) -> dict[str, Any]:
        """Linha achatada, para tabelas e exportação."""
        return {
            "id": self.id,
            "ref_bacen": self.ref_bacen,
            "municipio": self.municipio,
            "uf": self.uf,
            "regiao": self.regiao,
            "cd_ibge": self.cd_ibge,
            "lat": self.lat,
            "lon": self.lon,
            "cultura": self.cultura,
            "produto": self.produto,
            "fase": self.fase,
            "fase_nome": self.fase_nome,
            "evento": self.evento,
            "evento_nome": self.evento_nome,
            "severidade": self.severidade,
            "severidade_peso": self.severidade_peso,
            "score": round(self.score, 1),
            "dia_pico": self.dia_pico,
            "janela_acao_h": self.janela_acao_h,
            "area_ha": self.area_ha,
            "valor_credito": self.valor_credito,
            "programa": self.programa,
            "instituicao": self.instituicao,
            "tipo_seguro": self.tipo_seguro,
            "tem_cobertura": self.tem_cobertura,
            "coberto_proagro_evento": self.cobertura_proagro_evento,
            "irrigada": self.irrigada,
            "dias_para_colheita": self.dias_para_colheita,
            "dias_para_vencimento": self.dias_para_vencimento,
            "persona": self.persona,
            "setor": setor_da_persona(self.persona),
            "regras": ", ".join(self.regras),
            "n_regras": len(self.acionamentos),
            "perda_estimada_reais": (
                (self.contexto_externo.get("perda_estimada") or {}).get("perda_reais", 0.0)
            ),
            "dentro_janela_zarc": (
                (self.contexto_externo.get("zarc") or {}).get("dentro_janela")
            ),
            "protecao_municipio": (
                (self.contexto_externo.get("protecao_municipio") or {}).get("nivel", "")
            ),
            "anomalia_chuva": (
                (self.contexto_externo.get("anomalia_chuva") or {}).get("classificacao", "")
            ),
            "criado_em": self.criado_em,
        }

    @staticmethod
    def novo_id(ref_bacen: Any, nu_ordem: Any, evento: Any, data_ref: Any) -> str:
        return "ALT-" + _id_curto(ref_bacen, nu_ordem, evento, data_ref)


@dataclass
class Mensagem:
    """Comunicação redigida para um destinatário, em um canal."""

    id: str
    destinatario_id: str
    destinatario_nome: str
    persona: str
    persona_nome: str
    canal: str
    assunto: str
    texto: str
    alertas: list[str] = field(default_factory=list)     # ids de Alerta
    severidade: str = "atencao"
    score: float = 0.0
    municipio: str = ""
    uf: str = ""
    evento: str = ""
    gerado_por: str = "template"        # "llm" | "template"
    modelo: str = ""
    resumo_interno: str = ""
    acoes: list[str] = field(default_factory=list)
    caracteres: int = 0
    limite_canal: int = 0
    revisao: dict[str, Any] = field(default_factory=dict)
    explicacao: str = ""
    criado_em: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def dentro_do_limite(self) -> bool:
        return self.limite_canal <= 0 or self.caracteres <= self.limite_canal

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "destinatário": self.destinatario_nome,
            "persona": self.persona_nome,
            "canal": self.canal,
            "severidade": self.severidade,
            "score": round(self.score, 1),
            "município": self.municipio,
            "uf": self.uf,
            "evento": self.evento,
            "assunto": self.assunto,
            "caracteres": self.caracteres,
            "limite": self.limite_canal,
            "dentro_do_limite": self.dentro_do_limite,
            "gerado_por": self.gerado_por,
            "modelo": self.modelo,
            "alertas": len(self.alertas),
            "criado_em": self.criado_em,
        }

    @staticmethod
    def novo_id(destinatario: Any, canal: Any, evento: Any, data_ref: Any) -> str:
        return "MSG-" + _id_curto(destinatario, canal, evento, data_ref)


@dataclass
class Envio:
    """Resultado da **simulação** de despacho de uma mensagem."""

    id: str
    mensagem_id: str
    canal: str
    destinatario: str
    status: str                     # "simulado_entregue" | "simulado_falha" | "suprimido"
    motivo: str = ""
    tentativas: int = 1
    latencia_ms: int = 0
    custo_estimado: float = 0.0
    agendado_para: str = ""
    simulado: bool = True
    criado_em: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mensagem": self.mensagem_id,
            "canal": self.canal,
            "destinatário": self.destinatario,
            "status": self.status,
            "motivo": self.motivo,
            "tentativas": self.tentativas,
            "latência_ms": self.latencia_ms,
            "custo_estimado_R$": round(self.custo_estimado, 4),
            "agendado_para": self.agendado_para,
            "simulado": self.simulado,
            "criado_em": self.criado_em,
        }
