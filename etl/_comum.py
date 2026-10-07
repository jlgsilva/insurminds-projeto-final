"""
Utilidades compartilhadas pelos scripts de ETL.

Os arquivos do Sicor têm particularidades que quebram um ``read_csv``
ingênuo:

* **codificação** — em geral Latin-1/Windows-1252, não UTF-8;
* **delimitador** — ponto e vírgula na maioria, vírgula em alguns;
* **separador decimal** — vírgula;
* **cabeçalhos** — variam em maiúsculas/minúsculas e acentuação;
* **tamanho** — alguns ``.gz`` passam de 1 GB descomprimido.

As funções abaixo tratam tudo isso de forma defensiva: detectam
delimitador e codificação, normalizam nomes de coluna, processam em
blocos e verificam integridade pelo arquivo ``.hash`` quando o BCB o
publica.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agrosentinela.config import CURATED_DIR, RAW_DIR  # noqa: E402
from agrosentinela.etl_catalogo import ArquivoBCB  # noqa: E402
from agrosentinela.utils.logging_setup import configurar_logging, get_logger  # noqa: E402

log = get_logger("etl")

CODIFICACOES = ("utf-8-sig", "latin-1", "cp1252")
DELIMITADORES = (";", ",", "\t", "|")
TAMANHO_BLOCO = 400_000
TEMPO_LIMITE = 900  # s — arquivos grandes do BCB são lentos


# ==========================================================================
# Download
# ==========================================================================

@dataclass
class ResultadoDownload:
    caminho: Path
    baixado: bool
    tamanho_bytes: int
    hash_ok: bool | None = None
    erro: str | None = None

    @property
    def tamanho_mb(self) -> float:
        return round(self.tamanho_bytes / 1e6, 2)


def baixar(
    arquivo: ArquivoBCB,
    destino: Path | None = None,
    *,
    forcar: bool = False,
    verificar_hash: bool = True,
    tentativas: int = 3,
) -> ResultadoDownload:
    """
    Baixa um arquivo do catálogo do BCB, com retomada e verificação.

    Requer a biblioteca ``requests``. O download é feito em fluxo
    (``stream=True``), de modo que arquivos de vários gigabytes não
    precisem caber na memória.
    """
    import requests

    destino = Path(destino or RAW_DIR)
    destino.mkdir(parents=True, exist_ok=True)
    nome = arquivo.url.rsplit("/", 1)[-1]
    caminho = destino / nome

    if caminho.exists() and not forcar:
        tamanho = caminho.stat().st_size
        log.info("• %-46s já existe (%.1f MB)", nome, tamanho / 1e6)
        return ResultadoDownload(caminho, False, tamanho)

    ultimo_erro = ""
    for tentativa in range(1, tentativas + 1):
        try:
            log.info("↓ %-46s (tentativa %d)", nome, tentativa)
            parcial = caminho.with_suffix(caminho.suffix + ".part")
            inicio = time.perf_counter()
            with requests.get(arquivo.url, stream=True, timeout=TEMPO_LIMITE) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                baixados = 0
                with parcial.open("wb") as fh:
                    for bloco in r.iter_content(chunk_size=1 << 20):
                        if not bloco:
                            continue
                        fh.write(bloco)
                        baixados += len(bloco)
                        if total and baixados % (32 << 20) < (1 << 20):
                            log.info("   %s: %.0f%% (%.0f MB)", nome,
                                     100 * baixados / total, baixados / 1e6)
            parcial.replace(caminho)
            duracao = time.perf_counter() - inicio
            tamanho = caminho.stat().st_size
            log.info("✔ %-46s %.1f MB em %.0fs", nome, tamanho / 1e6, duracao)

            hash_ok = None
            if verificar_hash and arquivo.hash_url:
                hash_ok = _verificar_hash(caminho, arquivo.hash_url)
            return ResultadoDownload(caminho, True, tamanho, hash_ok)
        except Exception as exc:  # noqa: BLE001
            ultimo_erro = str(exc)
            log.warning("✖ %s falhou: %s", nome, exc)
            time.sleep(min(2 ** tentativa, 15))

    return ResultadoDownload(caminho, False, 0, None, ultimo_erro)


def _verificar_hash(caminho: Path, hash_url: str) -> bool | None:
    """Compara o SHA-256 local com o publicado pelo BCB."""
    import requests

    try:
        r = requests.get(hash_url, timeout=60)
        if r.status_code != 200:
            return None
        esperado = re.findall(r"[0-9a-fA-F]{32,64}", r.text)
        if not esperado:
            return None
        esperado = esperado[0].lower()
    except Exception:  # noqa: BLE001
        return None

    algoritmo = hashlib.sha256() if len(esperado) == 64 else hashlib.md5()
    with caminho.open("rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 22), b""):
            algoritmo.update(bloco)
    obtido = algoritmo.hexdigest().lower()
    ok = obtido == esperado
    log.info("   integridade %s: %s", caminho.name, "OK" if ok else "DIVERGENTE")
    return ok


# ==========================================================================
# Leitura tolerante
# ==========================================================================

def _abrir(caminho: Path, codificacao: str):
    if caminho.suffix == ".gz" or caminho.name.endswith(".csv.gz"):
        return gzip.open(caminho, "rt", encoding=codificacao, errors="replace", newline="")
    return caminho.open("r", encoding=codificacao, errors="replace", newline="")


def detectar_formato(caminho: Path) -> tuple[str, str]:
    """Descobre (codificação, delimitador) lendo apenas a primeira linha."""
    for codificacao in CODIFICACOES:
        try:
            with _abrir(caminho, codificacao) as fh:
                primeira = fh.readline()
            if not primeira:
                continue
            contagens = {d: primeira.count(d) for d in DELIMITADORES}
            delim = max(contagens, key=lambda k: contagens[k])
            if contagens[delim] == 0:
                delim = ";"
            # Rejeita codificação que produziu caractere de substituição
            if "�" in primeira and codificacao != CODIFICACOES[-1]:
                continue
            return codificacao, delim
        except (UnicodeDecodeError, OSError):
            continue
    return "latin-1", ";"


def normalizar_coluna(nome: str) -> str:
    """``  Nº Ordem `` -> ``NU_ORDEM``-like: maiúsculas, sem acento, com _."""
    s = unicodedata.normalize("NFKD", str(nome))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^0-9A-Za-z]+", "_", s).strip("_")
    return s.upper()


def ler_csv(
    caminho: Path,
    *,
    colunas: Sequence[str] | None = None,
    nrows: int | None = None,
    decimal: str | None = None,
) -> pd.DataFrame:
    """Lê um CSV do BCB (comprimido ou não) normalizando os nomes de coluna."""
    codificacao, delim = detectar_formato(caminho)
    log.debug("Lendo %s (%s, delim %r)", caminho.name, codificacao, delim)

    df = pd.read_csv(
        caminho,
        sep=delim,
        encoding=codificacao,
        encoding_errors="replace",
        dtype=str,
        nrows=nrows,
        low_memory=False,
        compression="gzip" if caminho.name.endswith(".gz") else "infer",
        on_bad_lines="warn",
    )
    df.columns = [normalizar_coluna(c) for c in df.columns]
    if colunas:
        faltando = [c for c in colunas if c not in df.columns]
        if faltando:
            log.warning("%s: colunas ausentes %s (disponíveis: %s)",
                        caminho.name, faltando, list(df.columns)[:20])
        df = df[[c for c in colunas if c in df.columns]]
    return df


def ler_csv_em_blocos(
    caminho: Path,
    *,
    colunas: Sequence[str] | None = None,
    tamanho: int = TAMANHO_BLOCO,
) -> Iterator[pd.DataFrame]:
    """Itera um CSV grande em blocos, já com colunas normalizadas."""
    codificacao, delim = detectar_formato(caminho)
    leitor = pd.read_csv(
        caminho,
        sep=delim,
        encoding=codificacao,
        encoding_errors="replace",
        dtype=str,
        chunksize=tamanho,
        low_memory=False,
        compression="gzip" if caminho.name.endswith(".gz") else "infer",
        on_bad_lines="warn",
    )
    for i, bloco in enumerate(leitor, start=1):
        bloco.columns = [normalizar_coluna(c) for c in bloco.columns]
        if colunas:
            bloco = bloco[[c for c in colunas if c in bloco.columns]]
        if i % 10 == 0:
            log.info("   %s: %d blocos processados", caminho.name, i)
        yield bloco


def espiar(caminho: Path, linhas: int = 5) -> pd.DataFrame:
    """Amostra rápida — útil para conferir layout antes de processar tudo."""
    return ler_csv(caminho, nrows=linhas)


# ==========================================================================
# Conversões
# ==========================================================================

def para_numero(serie: pd.Series, decimal: str = ",") -> pd.Series:
    """Converte texto do BCB ('1.234,56' ou '1234.56') em float."""
    if serie is None:
        return pd.Series(dtype="float64")
    s = serie.astype(str).str.strip()
    s = s.replace({"": None, "nan": None, "None": None, "-": None})
    if decimal == ",":
        s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def para_data(serie: pd.Series) -> pd.Series:
    """Converte as datas do Sicor, que aparecem em vários formatos."""
    if serie is None:
        return pd.Series(dtype="datetime64[ns]")
    s = serie.astype(str).str.strip()
    s = s.replace({"": None, "nan": None, "None": None, "0": None, "00000000": None})
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d", "%d-%m-%Y", "%Y/%m/%d"):
        convertido = pd.to_datetime(s, format=formato, errors="coerce")
        if convertido.notna().mean() > 0.5:
            return convertido
    return pd.to_datetime(s, errors="coerce", dayfirst=True)


def normalizar_texto(serie: pd.Series) -> pd.Series:
    return serie.astype(str).str.strip().str.replace(r"\s+", " ", regex=True)


# ==========================================================================
# Gravação
# ==========================================================================

def gravar(df: pd.DataFrame, nome: str, destino: Path | None = None) -> list[Path]:
    """
    Grava o conjunto curado em Parquet (se ``pyarrow`` existir) e em
    ``.csv.gz`` — este último garante que o aplicativo leia em qualquer
    instalação de pandas.
    """
    destino = Path(destino or CURATED_DIR)
    destino.mkdir(parents=True, exist_ok=True)
    saidas: list[Path] = []

    caminho_csv = destino / f"{nome}.csv.gz"
    df.to_csv(caminho_csv, index=False, compression="gzip")
    saidas.append(caminho_csv)

    try:
        caminho_parquet = destino / f"{nome}.parquet"
        df.to_parquet(caminho_parquet, index=False)
        saidas.append(caminho_parquet)
    except Exception as exc:  # noqa: BLE001 - pyarrow ausente é aceitável
        log.debug("Parquet não gravado (%s): %s", nome, exc)

    total = sum(p.stat().st_size for p in saidas) / 1e6
    log.info("💾 %-22s %7d linhas × %2d colunas (%.1f MB)",
             nome, len(df), df.shape[1], total)
    return saidas


def carregar_curado(nome: str, destino: Path | None = None) -> pd.DataFrame | None:
    destino = Path(destino or CURATED_DIR)
    for ext in (".parquet", ".csv.gz"):
        caminho = destino / f"{nome}{ext}"
        if caminho.exists():
            try:
                return (pd.read_parquet(caminho) if ext == ".parquet"
                        else pd.read_csv(caminho, low_memory=False))
            except Exception as exc:  # noqa: BLE001
                log.warning("Falha ao ler %s: %s", caminho.name, exc)
    return None


def iniciar(nivel: str = "INFO") -> None:
    configurar_logging(nivel)


def cabecalho(titulo: str) -> None:
    log.info("")
    log.info("═" * 74)
    log.info("  %s", titulo)
    log.info("═" * 74)
