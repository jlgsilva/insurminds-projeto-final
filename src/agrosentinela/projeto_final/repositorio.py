"""
Armazenamento estruturado das apólices (SQLite).

Por que SQLite: zero infraestrutura, um arquivo, transacional, roda igual no
Windows, no Linux e no Streamlit Cloud — e o esquema abaixo migra sem
alteração para PostgreSQL se o projeto crescer.

Tabelas
-------
* ``documentos``  — o que foi recebido (hash, páginas, método de leitura, OCR).
* ``apolices``    — dados cadastrais extraídos e validados + metadados de
  extração (método, modelo, confiança).
* ``clausulas``   — uma linha por apólice × cláusula da taxonomia, com nível,
  seção, evidência literal e se a evidência foi verificada no texto.
* ``secoes``      — o texto segmentado, para busca e para o agente de consulta.
* ``comparacoes`` — cada comparação executada, com o relatório gerado.
* ``auditoria``   — rastro de cada agente (quem fez o quê, quando, com qual
  resultado). É a evidência de funcionamento exigida pelo projeto.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from ..config import APOLICES_DIR, DATA_DIR

BANCO_PADRAO = DATA_DIR / "apolices.sqlite"
BASE_INICIAL = APOLICES_DIR / "base_inicial.sqlite"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS documentos (
    id              TEXT PRIMARY KEY,
    nome            TEXT NOT NULL,
    arquivos        TEXT,
    hash            TEXT UNIQUE,
    tipo            TEXT,
    paginas         INTEGER,
    metodo_leitura  TEXT,
    confianca_ocr   REAL,
    caracteres      INTEGER,
    recebido_em     TEXT
);
CREATE TABLE IF NOT EXISTS apolices (
    id                       TEXT PRIMARY KEY REFERENCES documentos(id),
    seguradora               TEXT,
    numero_apolice           TEXT,
    tomadora                 TEXT,
    tomadora_cnpj            TEXT,
    segmento                 TEXT,
    municipio                TEXT,
    uf                       TEXT,
    vigencia_inicio          TEXT,
    vigencia_fim             TEXT,
    retroatividade           TEXT,
    retroatividade_ilimitada INTEGER,
    lmg                      REAL,
    premio                   REAL,
    franquia                 REAL,
    metodo_cadastro          TEXT,
    metodo_clausulas         TEXT,
    modelo                   TEXT,
    confianca                REAL,
    alertas_validacao        TEXT,
    extraido_em              TEXT,
    tipo_documento           TEXT DEFAULT 'apolice'
);
CREATE TABLE IF NOT EXISTS clausulas (
    apolice_id            TEXT REFERENCES apolices(id),
    codigo                TEXT,
    nivel                 TEXT,
    secao                 TEXT,
    evidencia             TEXT,
    justificativa         TEXT,
    metodo                TEXT,
    evidencia_verificada  INTEGER,
    PRIMARY KEY (apolice_id, codigo)
);
CREATE TABLE IF NOT EXISTS secoes (
    apolice_id  TEXT REFERENCES apolices(id),
    indice      INTEGER,
    titulo      TEXT,
    texto       TEXT,
    PRIMARY KEY (apolice_id, indice)
);
CREATE TABLE IF NOT EXISTS comparacoes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    apolices    TEXT,
    resumo      TEXT,
    relatorio   TEXT,
    persona     TEXT,
    metodo      TEXT,
    criado_em   TEXT
);
CREATE TABLE IF NOT EXISTS auditoria (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT,
    agente      TEXT,
    referencia  TEXT,
    evento      TEXT,
    detalhe     TEXT
);
"""


def _conv(v: Any) -> Any:
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v


class Repositorio:
    def __init__(self, caminho: Path | str | None = None, *, semear: bool = True) -> None:
        self.caminho = Path(caminho) if caminho else BANCO_PADRAO
        if semear and not self.caminho.exists() and BASE_INICIAL.exists() \
                and self.caminho != BASE_INICIAL:
            # Primeira execução: parte da base já processada do acervo
            # simulado (inclusive o OCR das digitalizadas, que é lento).
            shutil.copyfile(BASE_INICIAL, self.caminho)
        with self._con() as con:
            con.executescript(ESQUEMA)
            # bases criadas antes da coluna tipo_documento (condições gerais × apólice)
            colunas = {r[1] for r in con.execute("PRAGMA table_info(apolices)")}
            if "tipo_documento" not in colunas:
                con.execute("ALTER TABLE apolices ADD COLUMN tipo_documento TEXT DEFAULT 'apolice'")

    @contextmanager
    def _con(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.caminho)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    # ------------------------------------------------------------ escrita
    def salvar_documento(self, ident: str, doc: Any) -> None:
        with self._con() as con:
            con.execute("DELETE FROM documentos WHERE id = ? OR hash = ?", (ident, doc.hash))
            con.execute(
                "INSERT INTO documentos VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ident, doc.nome, json.dumps(doc.arquivos, ensure_ascii=False), doc.hash,
                 doc.tipo, len(doc.paginas), doc.metodo_resumo, doc.confianca_ocr_media,
                 len(doc.texto), datetime.now().isoformat(timespec="seconds")))

    def salvar_extracao(self, ident: str, extracao: Any, secoes: list[Any],
                        confianca: float, alertas: list[str]) -> None:
        c = extracao.cadastro
        with self._con() as con:
            con.execute("DELETE FROM apolices WHERE id = ?", (ident,))
            con.execute("DELETE FROM clausulas WHERE apolice_id = ?", (ident,))
            con.execute("DELETE FROM secoes WHERE apolice_id = ?", (ident,))
            con.execute(
                "INSERT INTO apolices (id, seguradora, numero_apolice, tomadora, tomadora_cnpj, "
                "segmento, municipio, uf, vigencia_inicio, vigencia_fim, retroatividade, "
                "retroatividade_ilimitada, lmg, premio, franquia, metodo_cadastro, "
                "metodo_clausulas, modelo, confianca, alertas_validacao, extraido_em, "
                "tipo_documento) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ident, c.get("seguradora"), c.get("numero_apolice"), c.get("tomadora"),
                 c.get("tomadora_cnpj"), c.get("segmento"), c.get("municipio"), c.get("uf"),
                 _conv(c.get("vigencia_inicio")), _conv(c.get("vigencia_fim")),
                 _conv(c.get("retroatividade")), _conv(c.get("retroatividade_ilimitada")),
                 c.get("lmg"), c.get("premio"), c.get("franquia"),
                 extracao.metodo_cadastro, extracao.metodo_clausulas, extracao.modelo,
                 confianca, json.dumps(alertas, ensure_ascii=False),
                 datetime.now().isoformat(timespec="seconds"),
                 getattr(extracao, "tipo_documento", "apolice")))
            con.executemany(
                "INSERT INTO clausulas VALUES (?,?,?,?,?,?,?,?)",
                [(ident, k, v.nivel, v.secao, v.evidencia, v.justificativa, v.metodo,
                  _conv(v.evidencia_verificada)) for k, v in extracao.clausulas.items()])
            con.executemany(
                "INSERT INTO secoes VALUES (?,?,?,?)",
                [(ident, s.indice, s.titulo, s.texto) for s in secoes])

    def auditar(self, agente: str, referencia: str, evento: str, detalhe: Any = "") -> None:
        with self._con() as con:
            con.execute(
                "INSERT INTO auditoria (ts, agente, referencia, evento, detalhe) VALUES (?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), agente, referencia, evento,
                 detalhe if isinstance(detalhe, str) else json.dumps(detalhe, ensure_ascii=False,
                                                                    default=str)))

    def salvar_comparacao(self, ids: list[str], resumo: dict, relatorio: str,
                          persona: str, metodo: str) -> int:
        with self._con() as con:
            cur = con.execute(
                "INSERT INTO comparacoes (apolices, resumo, relatorio, persona, metodo, criado_em) "
                "VALUES (?,?,?,?,?,?)",
                (json.dumps(ids), json.dumps(resumo, ensure_ascii=False, default=str), relatorio,
                 persona, metodo, datetime.now().isoformat(timespec="seconds")))
            return int(cur.lastrowid)

    def remover(self, ident: str) -> None:
        with self._con() as con:
            for t, col in (("clausulas", "apolice_id"), ("secoes", "apolice_id"),
                           ("apolices", "id"), ("documentos", "id")):
                con.execute(f"DELETE FROM {t} WHERE {col} = ?", (ident,))

    # ------------------------------------------------------------ leitura
    def df(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        with self._con() as con:
            return pd.read_sql_query(sql, con, params=params)

    def apolices(self) -> pd.DataFrame:
        return self.df("""
            SELECT a.*, d.nome AS documento, d.tipo, d.metodo_leitura, d.confianca_ocr,
                   d.paginas
            FROM apolices a JOIN documentos d ON d.id = a.id ORDER BY a.id""")

    def clausulas(self, ids: list[str] | None = None) -> pd.DataFrame:
        if ids:
            marc = ",".join("?" * len(ids))
            return self.df(f"SELECT * FROM clausulas WHERE apolice_id IN ({marc})", tuple(ids))
        return self.df("SELECT * FROM clausulas")

    def secoes(self, ident: str) -> pd.DataFrame:
        return self.df("SELECT * FROM secoes WHERE apolice_id = ? ORDER BY indice", (ident,))

    def buscar_texto(self, termo: str, ident: str | None = None, limite: int = 20) -> pd.DataFrame:
        sql = ("SELECT apolice_id, indice, titulo, texto FROM secoes "
               "WHERE (texto LIKE ? OR titulo LIKE ?)")
        params: list[Any] = [f"%{termo}%", f"%{termo}%"]
        if ident:
            sql += " AND apolice_id = ?"
            params.append(ident)
        return self.df(sql + f" LIMIT {int(limite)}", tuple(params))

    def auditoria(self, limite: int = 300) -> pd.DataFrame:
        return self.df(f"SELECT * FROM auditoria ORDER BY id DESC LIMIT {int(limite)}")

    def comparacoes(self) -> pd.DataFrame:
        return self.df("SELECT * FROM comparacoes ORDER BY id DESC")

    def existe_hash(self, h: str) -> str | None:
        with self._con() as con:
            r = con.execute("SELECT id FROM documentos WHERE hash = ?", (h,)).fetchone()
            return r["id"] if r else None

    def contagem(self) -> dict[str, int]:
        with self._con() as con:
            return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in ("documentos", "apolices", "clausulas", "secoes",
                              "comparacoes", "auditoria")}
