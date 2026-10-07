"""
Testes de portabilidade — o projeto tem de rodar em Windows, macOS e Linux.

A aplicação é publicada no Streamlit Cloud (Linux), mas é **desenvolvida e
avaliada em Windows**. Essa combinação produz uma classe de defeito que só
aparece na máquina de quem avalia, e nunca na de quem escreveu — o pior tipo.

Três armadilhas são verificadas aqui, todas já causadoras de problema real em
projetos Python:

1. **Leitura e escrita sem `encoding` declarado.** No Linux o padrão é UTF-8 e
   tudo funciona; no Windows o padrão é a codificação local (`cp1252`), e
   qualquer acento em arquivo lido sem `encoding` vira `UnicodeDecodeError`.
   Como todo texto deste projeto é em português, o defeito seria imediato.

2. **Caminhos montados com barra literal.** `"data/curated/x.csv"` funciona no
   Windows por acidente do próprio Windows aceitar `/`, mas `"pasta\\arquivo"`
   e concatenações à mão não funcionam no Unix. A regra aqui é `pathlib` para
   tudo.

3. **Chamadas exclusivas de Unix.** `os.fork`, `fcntl`, `signal.SIGKILL`,
   caminhos absolutos tipo `/tmp` ou `/etc`.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent

PASTAS = ("src", "etl", "scripts", "pages", "tests")

# Testes podem usar caminhos Unix como *dado* (é o caso do teste que garante
# que o avaliador de expressões recusa `open('/etc/passwd')`).
ARQUIVOS_ISENTOS = {"test_regras.py", "test_portabilidade.py"}


def arquivos_python() -> list[Path]:
    encontrados: list[Path] = []
    for pasta in PASTAS:
        encontrados.extend(
            p for p in (RAIZ / pasta).rglob("*.py")
            if "__pycache__" not in p.parts
        )
    encontrados.append(RAIZ / "app.py")
    return sorted(p for p in encontrados if p.exists())


def test_ha_arquivos_para_verificar():
    """Guarda contra a varredura silenciosamente vazia."""
    assert len(arquivos_python()) > 40


# ==========================================================================
# 1. Codificação declarada
# ==========================================================================

def _chamadas_de_texto(arvore: ast.AST):
    """Chamadas a open / read_text / write_text que lidam com texto."""
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        nome = ""
        if isinstance(no.func, ast.Name):
            nome = no.func.id
        elif isinstance(no.func, ast.Attribute):
            nome = no.func.attr
        if nome not in {"open", "read_text", "write_text"}:
            continue

        # Modo binário não tem codificação — `open(p, "rb")` está correto.
        # Atenção à posição do argumento: em `open(caminho, "rb")` o modo é o
        # segundo; em `Path(caminho).open("rb")` é o **primeiro**. Confundir
        # os dois faz o teste acusar código correto, que foi exatamente o que
        # aconteceu na primeira versão desta verificação.
        posicao_modo = 0 if isinstance(no.func, ast.Attribute) and nome == "open" else 1
        candidatos = list(no.args[posicao_modo:posicao_modo + 1])
        candidatos += [k.value for k in no.keywords if k.arg == "mode"]
        modo_binario = any(
            isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            and "b" in arg.value
            for arg in candidatos
        )
        if modo_binario:
            continue
        yield no, nome


def test_toda_leitura_e_escrita_de_texto_declara_encoding():
    """
    No Windows, `open(caminho)` usa cp1252. Todo arquivo de texto deste
    projeto tem acento; sem `encoding="utf-8"` explícito, quebra na primeira
    linha — na máquina de quem avalia, não na de quem escreveu.
    """
    faltando: list[str] = []
    for caminho in arquivos_python():
        if caminho.name in ARQUIVOS_ISENTOS:
            continue
        try:
            arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for no, nome in _chamadas_de_texto(arvore):
            tem_encoding = any(k.arg == "encoding" for k in no.keywords)
            # `**kwargs` repassados contam como possível encoding.
            tem_kwargs = any(k.arg is None for k in no.keywords)
            if not tem_encoding and not tem_kwargs:
                faltando.append(
                    f"{caminho.relative_to(RAIZ)}:{no.lineno} → {nome}()"
                )
    assert not faltando, (
        "chamadas sem encoding declarado (quebram no Windows):\n  "
        + "\n  ".join(faltando)
    )


# ==========================================================================
# 2. Caminhos
# ==========================================================================

PADRAO_CAMINHO_WINDOWS = re.compile(r'"[A-Za-z]:\\\\|\'[A-Za-z]:\\\\')


def test_sem_caminho_absoluto_de_windows():
    ofensores = []
    for caminho in arquivos_python():
        texto = caminho.read_text(encoding="utf-8")
        if PADRAO_CAMINHO_WINDOWS.search(texto):
            ofensores.append(str(caminho.relative_to(RAIZ)))
    assert not ofensores, f"caminho absoluto de Windows em: {ofensores}"


def test_sem_caminho_absoluto_de_unix():
    """
    `/tmp`, `/etc`, `/home`, `/var` não existem no Windows. Diretório
    temporário se obtém com `tempfile`, não com uma constante.
    """
    padrao = re.compile(r'["\'](?:/tmp|/etc|/var|/home|/usr)/')
    ofensores = []
    for caminho in arquivos_python():
        if caminho.name in ARQUIVOS_ISENTOS:
            continue
        for i, linha in enumerate(
            caminho.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if padrao.search(linha) and not linha.strip().startswith("#"):
                ofensores.append(f"{caminho.relative_to(RAIZ)}:{i}")
    assert not ofensores, f"caminho absoluto de Unix em: {ofensores}"


# ==========================================================================
# 3. Chamadas exclusivas de Unix
# ==========================================================================

MODULOS_SO_UNIX = {"fcntl", "pwd", "grp", "termios", "resource", "posix"}


def test_sem_modulo_exclusivo_de_unix():
    ofensores = []
    for caminho in arquivos_python():
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            nomes: list[str] = []
            if isinstance(no, ast.Import):
                nomes = [a.name.split(".")[0] for a in no.names]
            elif isinstance(no, ast.ImportFrom) and no.module:
                nomes = [no.module.split(".")[0]]
            for nome in nomes:
                if nome in MODULOS_SO_UNIX:
                    ofensores.append(
                        f"{caminho.relative_to(RAIZ)}:{no.lineno} → {nome}"
                    )
    assert not ofensores, f"módulo exclusivo de Unix em: {ofensores}"


def test_sem_chamada_exclusiva_de_unix():
    padrao = re.compile(r"\bos\.(fork|getuid|geteuid|setuid|kill)\b"
                        r"|\bsignal\.SIG(KILL|USR1|USR2|HUP)\b")
    ofensores = []
    for caminho in arquivos_python():
        if caminho.name in ARQUIVOS_ISENTOS:
            continue
        for i, linha in enumerate(
            caminho.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if padrao.search(linha):
                ofensores.append(f"{caminho.relative_to(RAIZ)}:{i}")
    assert not ofensores, f"chamada exclusiva de Unix em: {ofensores}"


# ==========================================================================
# 4. Saída de console segura
# ==========================================================================

def test_saida_e_preparada_para_unicode():
    """
    Redirecionar a saída no Windows (`> log.txt`) faz o Python voltar à
    codificação local. Sem reconfigurar para UTF-8, um símbolo do log derruba
    uma execução que pode ter levado uma hora.
    """
    from agrosentinela.utils.logging_setup import _preparar_saida_unicode

    _preparar_saida_unicode()   # não pode levantar exceção em nenhum sistema


def test_cor_desligada_quando_o_terminal_nao_aceita():
    """
    O `cmd.exe` antigo não interpreta ANSI e mostraria `←[38;5;39m` no meio
    do texto. Sem terminal (saída redirecionada), não se emite cor.
    """
    import io

    from agrosentinela.utils.logging_setup import _terminal_aceita_cor

    assert _terminal_aceita_cor(io.StringIO()) is False


def test_arquivos_de_pagina_tem_nome_valido_no_windows():
    """
    O Windows proíbe < > : " | ? * e \\ em nome de arquivo. As páginas do
    Streamlit usam emoji no nome — o que é aceito —, mas um `&` ou `:` ali
    impediria o `git clone` de funcionar no Windows.
    """
    proibidos = set('<>:"|?*\\')
    ruins = [
        p.name for p in (RAIZ / "pages").glob("*.py")
        if proibidos & set(p.name)
    ]
    assert not ruins, f"nome de arquivo inválido no Windows: {ruins}"
