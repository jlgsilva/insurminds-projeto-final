"""
Caixa de saída (outbox) persistente em SQLite.

Guarda o que foi **simulado** como enviado. Serve a três propósitos:

* **anti-fadiga de alerta** — permite saber se o mesmo destinatário já
  recebeu comunicação equivalente na janela de supressão;
* **auditoria** — todo alerta, mensagem e envio fica registrado com a
  regra que o originou e o modelo que o redigiu;
* **demonstração** — a interface mostra o histórico como uma central de
  comunicação real mostraria.

Nada aqui envia mensagem de verdade: o campo ``simulado`` é sempre
verdadeiro, conforme exigido pelo enunciado do desafio.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import pandas as pd

from ..config import get_settings
from ..models import Alerta, Envio, Mensagem
from ..utils.logging_setup import get_logger

log = get_logger(__name__)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS execucoes (
    id              TEXT PRIMARY KEY,
    iniciado_em     TEXT NOT NULL,
    data_ref        TEXT NOT NULL,
    origem_dados    TEXT,
    cenario         TEXT,
    n_operacoes     INTEGER,
    n_alertas       INTEGER,
    n_mensagens     INTEGER,
    n_envios        INTEGER,
    duracao_s       REAL,
    resumo_json     TEXT
);

CREATE TABLE IF NOT EXISTS alertas (
    id              TEXT PRIMARY KEY,
    execucao_id     TEXT,
    criado_em       TEXT,
    ref_bacen       TEXT,
    cd_ibge         INTEGER,
    municipio       TEXT,
    uf              TEXT,
    cultura         TEXT,
    fase            TEXT,
    evento          TEXT,
    severidade      TEXT,
    score           REAL,
    valor_credito   REAL,
    area_ha         REAL,
    persona         TEXT,
    regras          TEXT,
    payload_json    TEXT,
    FOREIGN KEY (execucao_id) REFERENCES execucoes(id)
);

CREATE TABLE IF NOT EXISTS mensagens (
    id              TEXT PRIMARY KEY,
    execucao_id     TEXT,
    criado_em       TEXT,
    destinatario_id TEXT,
    persona         TEXT,
    canal           TEXT,
    severidade      TEXT,
    score           REAL,
    municipio       TEXT,
    uf              TEXT,
    evento          TEXT,
    assunto         TEXT,
    texto           TEXT,
    gerado_por      TEXT,
    modelo          TEXT,
    caracteres      INTEGER,
    alertas_json    TEXT,
    payload_json    TEXT
);

CREATE TABLE IF NOT EXISTS envios (
    id              TEXT PRIMARY KEY,
    execucao_id     TEXT,
    mensagem_id     TEXT,
    criado_em       TEXT,
    canal           TEXT,
    destinatario    TEXT,
    status          TEXT,
    motivo          TEXT,
    tentativas      INTEGER,
    latencia_ms     INTEGER,
    custo_estimado  REAL,
    simulado        INTEGER
);

CREATE INDEX IF NOT EXISTS ix_envios_dest ON envios (destinatario, criado_em);
CREATE INDEX IF NOT EXISTS ix_mensagens_dest ON mensagens (destinatario_id, criado_em);
CREATE INDEX IF NOT EXISTS ix_alertas_exec ON alertas (execucao_id);
"""


class Outbox:
    """Repositório SQLite da central de comunicação."""

    def __init__(self, caminho: Path | str | None = None) -> None:
        self.caminho = Path(caminho or get_settings().outbox_db)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._criar_esquema()

    # ------------------------------------------------------------------
    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.caminho, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _criar_esquema(self) -> None:
        with self._conn() as c:
            c.executescript(ESQUEMA)

    # ------------------------------------------------------------------
    def registrar_execucao(
        self,
        execucao_id: str,
        *,
        data_ref: str,
        origem_dados: str,
        cenario: str | None,
        resumo: dict[str, Any],
    ) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT OR REPLACE INTO execucoes
                   (id, iniciado_em, data_ref, origem_dados, cenario, n_operacoes,
                    n_alertas, n_mensagens, n_envios, duracao_s, resumo_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    execucao_id,
                    datetime.now().isoformat(timespec="seconds"),
                    data_ref,
                    origem_dados,
                    cenario or "",
                    int(resumo.get("operações_monitoradas", 0)),
                    int(resumo.get("alertas_gerados", 0)),
                    int(resumo.get("mensagens_geradas", 0)),
                    int(resumo.get("envios_simulados", 0)),
                    float(resumo.get("duração_total_s", 0.0)),
                    json.dumps(resumo, ensure_ascii=False, default=str),
                ),
            )

    def gravar_alertas(self, execucao_id: str, alertas: Sequence[Alerta]) -> int:
        if not alertas:
            return 0
        with self._conn() as c:
            c.executemany(
                """INSERT OR REPLACE INTO alertas
                   (id, execucao_id, criado_em, ref_bacen, cd_ibge, municipio, uf,
                    cultura, fase, evento, severidade, score, valor_credito, area_ha,
                    persona, regras, payload_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        a.id, execucao_id, a.criado_em, a.ref_bacen, a.cd_ibge,
                        a.municipio, a.uf, a.cultura, a.fase, a.evento, a.severidade,
                        float(a.score), float(a.valor_credito), float(a.area_ha),
                        a.persona, ", ".join(a.regras),
                        json.dumps(a.to_row(), ensure_ascii=False, default=str),
                    )
                    for a in alertas
                ],
            )
        return len(alertas)

    def gravar_mensagens(self, execucao_id: str, mensagens: Sequence[Mensagem]) -> int:
        if not mensagens:
            return 0
        with self._conn() as c:
            c.executemany(
                """INSERT OR REPLACE INTO mensagens
                   (id, execucao_id, criado_em, destinatario_id, persona, canal,
                    severidade, score, municipio, uf, evento, assunto, texto,
                    gerado_por, modelo, caracteres, alertas_json, payload_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        m.id, execucao_id, m.criado_em, m.destinatario_id, m.persona,
                        m.canal, m.severidade, float(m.score), m.municipio, m.uf,
                        m.evento, m.assunto, m.texto, m.gerado_por, m.modelo,
                        int(m.caracteres),
                        json.dumps(m.alertas, ensure_ascii=False),
                        json.dumps(m.to_row(), ensure_ascii=False, default=str),
                    )
                    for m in mensagens
                ],
            )
        return len(mensagens)

    def gravar_envios(self, execucao_id: str, envios: Sequence[Envio]) -> int:
        if not envios:
            return 0
        with self._conn() as c:
            c.executemany(
                """INSERT OR REPLACE INTO envios
                   (id, execucao_id, mensagem_id, criado_em, canal, destinatario,
                    status, motivo, tentativas, latencia_ms, custo_estimado, simulado)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        e.id, execucao_id, e.mensagem_id, e.criado_em, e.canal,
                        e.destinatario, e.status, e.motivo, int(e.tentativas),
                        int(e.latencia_ms), float(e.custo_estimado), 1 if e.simulado else 0,
                    )
                    for e in envios
                ],
            )
        return len(envios)

    # ------------------------------------------------------------------
    def historico_envios(self, janela_h: int = 48) -> dict[str, datetime]:
        """Mapa ``destinatario|canal -> último envio`` na janela informada."""
        corte = (datetime.now() - timedelta(hours=janela_h)).isoformat(timespec="seconds")
        with self._conn() as c:
            linhas = c.execute(
                """SELECT destinatario, canal, MAX(criado_em) AS ultimo
                   FROM envios
                   WHERE criado_em >= ? AND status LIKE 'simulado_entregue%'
                   GROUP BY destinatario, canal""",
                (corte,),
            ).fetchall()
        saida: dict[str, datetime] = {}
        for l in linhas:
            try:
                saida[f"{l['destinatario']}|{l['canal']}"] = datetime.fromisoformat(l["ultimo"])
            except (TypeError, ValueError):
                continue
        return saida

    def contagem_hoje(self) -> dict[str, int]:
        """Quantas mensagens cada destinatário já recebeu hoje."""
        hoje = datetime.now().date().isoformat()
        with self._conn() as c:
            linhas = c.execute(
                """SELECT destinatario, COUNT(*) AS n FROM envios
                   WHERE substr(criado_em, 1, 10) = ?
                     AND status LIKE 'simulado_entregue%'
                   GROUP BY destinatario""",
                (hoje,),
            ).fetchall()
        return {l["destinatario"]: int(l["n"]) for l in linhas}

    # ------------------------------------------------------------------
    def tabela(self, nome: str, limite: int = 2000) -> pd.DataFrame:
        if nome not in {"execucoes", "alertas", "mensagens", "envios"}:
            raise ValueError(f"Tabela desconhecida: {nome}")
        with self._conn() as c:
            return pd.read_sql_query(
                f"SELECT * FROM {nome} ORDER BY rowid DESC LIMIT ?", c, params=(limite,)
            )

    def estatisticas(self) -> dict[str, Any]:
        with self._conn() as c:
            def _n(t: str) -> int:
                return int(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])

            por_canal = {
                r["canal"]: int(r["n"])
                for r in c.execute(
                    "SELECT canal, COUNT(*) n FROM envios GROUP BY canal"
                ).fetchall()
            }
            por_status = {
                r["status"]: int(r["n"])
                for r in c.execute(
                    "SELECT status, COUNT(*) n FROM envios GROUP BY status"
                ).fetchall()
            }
            return {
                "execucoes": _n("execucoes"),
                "alertas": _n("alertas"),
                "mensagens": _n("mensagens"),
                "envios": _n("envios"),
                "por_canal": por_canal,
                "por_status": por_status,
                "arquivo": str(self.caminho),
            }

    def limpar(self) -> None:
        """Zera a caixa de saída (usado em testes e no botão de reset da UI)."""
        with self._conn() as c:
            for t in ("envios", "mensagens", "alertas", "execucoes"):
                c.execute(f"DELETE FROM {t}")
        log.info("Outbox limpa: %s", self.caminho)

    def exportar(self, destino: Path | str) -> list[Path]:
        """Exporta todas as tabelas em CSV (usado para compor os entregáveis)."""
        destino = Path(destino)
        destino.mkdir(parents=True, exist_ok=True)
        saidas: list[Path] = []
        for nome in ("execucoes", "alertas", "mensagens", "envios"):
            df = self.tabela(nome, limite=100_000)
            caminho = destino / f"outbox_{nome}.csv"
            df.to_csv(caminho, index=False)
            saidas.append(caminho)
        return saidas
