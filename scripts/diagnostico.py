#!/usr/bin/env python3
"""
Diagnóstico completo do AgroSentinela.

Roda tudo que dá para rodar sem interface: confere o ambiente, as
dependências, os dados disponíveis, executa o pipeline de ponta a ponta,
exercita as onze páginas com dublês de interface e testa as fontes externas.

No fim imprime uma lista de **problemas encontrados**, cada um com o que
fazer a respeito.

Este script **nunca interrompe por causa de um erro**: quando algo falha, ele
registra, explica e segue para a próxima verificação. Um diagnóstico que para
no primeiro problema só conta metade da história.

Uso:
    python scripts/diagnostico.py

O relatório sai no terminal e também em `diagnostico.txt`, na raiz do
projeto — é esse arquivo que você manda para quem for ajudar.
"""

from __future__ import annotations

import io
import os
import platform
import shutil
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "tests"))

SAIDA = RAIZ / "diagnostico.txt"

# Cada item: (gravidade, título, o que fazer)
PROBLEMAS: list[tuple[str, str, str]] = []
LINHAS: list[str] = []

GRAVE = "GRAVE"
AVISO = "AVISO"
NOTA = "NOTA"


# ==========================================================================
# Impressão
# ==========================================================================

def p(texto: str = "") -> None:
    LINHAS.append(texto)
    try:
        print(texto)
    except UnicodeEncodeError:          # console Windows antigo
        print(texto.encode("ascii", "replace").decode("ascii"))


def secao(titulo: str) -> None:
    p("")
    p("=" * 74)
    p(f"  {titulo}")
    p("=" * 74)


def item(rotulo: str, valor: Any) -> None:
    p(f"  {rotulo:.<42} {valor}")


def problema(gravidade: str, titulo: str, o_que_fazer: str) -> None:
    PROBLEMAS.append((gravidade, titulo, o_que_fazer))
    p(f"  [{gravidade}] {titulo}")


def tentar(rotulo: str, funcao: Callable[[], Any], *,
           gravidade: str = GRAVE, dica: str = "") -> Any:
    """Executa uma verificação e registra a falha em vez de interromper."""
    try:
        return funcao()
    except Exception as exc:  # noqa: BLE001 — é um diagnóstico
        p(f"  [{gravidade}] {rotulo}: {type(exc).__name__}: {exc}")
        detalhe = traceback.format_exc().strip().splitlines()
        for linha in detalhe[-4:]:
            p(f"        {linha}")
        PROBLEMAS.append((gravidade, f"{rotulo}: {type(exc).__name__}: {exc}",
                          dica or "Envie este relatório para análise."))
        return None


# ==========================================================================
# 1. Ambiente
# ==========================================================================

def verificar_ambiente() -> None:
    secao("1. AMBIENTE")
    item("Sistema", f"{platform.system()} {platform.release()}")
    item("Python", sys.version.split()[0])
    item("Executável", sys.executable)
    item("Em ambiente virtual", "sim" if sys.prefix != sys.base_prefix else "NÃO")
    item("Pasta do projeto", str(RAIZ))
    try:
        from agrosentinela import __version__

        item("Versão do AgroSentinela", __version__)
    except Exception:  # noqa: BLE001
        item("Versão do AgroSentinela", "não foi possível ler")
    item("Codificação do terminal", sys.stdout.encoding)
    item("Codificação padrão de arquivo",
         __import__("locale").getpreferredencoding(False))

    if sys.version_info < (3, 11):
        problema(GRAVE, f"Python {sys.version.split()[0]} é antigo demais",
                 "Instale o Python 3.11 ou superior.")
    if sys.prefix == sys.base_prefix:
        problema(AVISO, "Você não está num ambiente virtual",
                 "Rode: python -m venv .venv  e depois  .venv\\Scripts\\activate")

    caminho = str(RAIZ).lower()
    for pasta, motivo in (
        ("downloads", "o antivírus examina arquivos de Downloads e pode travar "
                      "a leitura no meio de uma importação"),
        ("onedrive", "a sincronização do OneDrive pode deixar arquivos "
                     "temporariamente indisponíveis"),
    ):
        if pasta in caminho:
            problema(AVISO, f"O projeto está dentro de «{pasta}»",
                     f"Mova para algo como C:\\Projetos\\agrosentinela — {motivo}.")


# ==========================================================================
# 2. Dependências
# ==========================================================================

def verificar_dependencias() -> None:
    secao("2. DEPENDÊNCIAS")
    obrigatorias = ["pandas", "numpy", "streamlit", "plotly", "requests", "yaml"]
    opcionais = ["pyarrow", "docx", "pytest", "matplotlib"]

    for nome in obrigatorias + opcionais:
        try:
            mod = __import__(nome)
            versao = getattr(mod, "__version__", "instalado")
            item(nome, versao)
        except ImportError:
            if nome in obrigatorias:
                item(nome, "AUSENTE")
                problema(GRAVE, f"Dependência obrigatória ausente: {nome}",
                         "Rode: pip install -r requirements.txt")
            else:
                item(nome, "ausente (opcional)")

    exe = shutil.which("wkhtmltopdf")
    item("wkhtmltopdf", exe or "ausente (opcional)")
    if not exe:
        problema(NOTA, "wkhtmltopdf não encontrado",
                 "Só é necessário para gerar os PDFs. Instale de "
                 "https://wkhtmltopdf.org/downloads.html, ou abra o HTML no "
                 "navegador e use Imprimir → Salvar como PDF.")


# ==========================================================================
# 3. Dados disponíveis
# ==========================================================================

def verificar_dados() -> None:
    secao("3. DADOS DISPONÍVEIS")
    from agrosentinela.config import CURATED_DIR, RAW_DIR, SEED_DIR

    conjuntos = ("municipios", "carteira", "proagro_sinistros", "serie_credito",
                 "glebas", "exposicao", "contexto_externo")

    for rotulo, pasta in (("Demonstração (seed)", SEED_DIR),
                          ("Oficiais do BCB (curated)", CURATED_DIR)):
        p("")
        p(f"  {rotulo} — {pasta}")
        if not pasta.exists():
            p("     pasta não existe")
            continue
        achou = False
        for nome in conjuntos:
            for ext in (".parquet", ".csv.gz", ".csv"):
                arquivo = pasta / f"{nome}{ext}"
                if arquivo.exists():
                    tam = arquivo.stat().st_size / 1024
                    p(f"     {nome + ext:<34} {tam:>10.1f} KB")
                    achou = True
                    break
            else:
                p(f"     {nome:<34} {'—':>10}")
        if not achou:
            p("     (vazia)")

    brutos = list(RAW_DIR.rglob("*.gz")) if RAW_DIR.exists() else []
    p("")
    item("Arquivos brutos baixados do BCB", len(brutos))

    curados = list(CURATED_DIR.glob("carteira.*")) if CURATED_DIR.exists() else []
    if not curados:
        problema(
            NOTA,
            "Os dados oficiais do BCB não foram baixados nesta máquina",
            "É esperado: são dezenas de gigabytes e não vêm no repositório. "
            "Por isso a opção «Somente dados curados do BCB» aparece vazia — "
            "use «Automática». Para baixar de verdade: "
            "python etl/run_etl.py --anos 2025 2026",
        )


# ==========================================================================
# 4. Carga e validação
# ==========================================================================

def verificar_carga() -> Any:
    secao("4. CARGA DOS CONJUNTOS")
    from agrosentinela.data.loader import carregar_base
    from agrosentinela.data.schemas import DATASETS_POR_NOME, validar

    base = tentar("carregar_base()", lambda: carregar_base("auto"),
                  dica="Verifique se a pasta data/seed existe e tem os .csv.gz.")
    if base is None:
        return None

    item("Origem em uso", base.origem)
    item("Operações na carteira", f"{len(base.carteira):,}".replace(",", "."))
    item("Municípios", len(base.municipios))
    item("Registros de sinistro", f"{len(base.proagro_sinistros):,}".replace(",", "."))

    # `getattr` em tudo que é recente de propósito: este script precisa rodar
    # numa cópia antiga do projeto — é justamente ela que costuma ter o
    # problema que se quer diagnosticar. Exigir a versão nova para poder
    # diagnosticar a antiga inverte a ordem das coisas.
    enriquecimentos = getattr(base, "enriquecimentos", None)
    if callable(enriquecimentos):
        for nome, ativo in enriquecimentos().items():
            item(nome, "sim" if ativo else "não")
    else:
        item("Enriquecimentos", "versão antiga do projeto (sem esta informação)")

    carteira_vazia = base.carteira is None or base.carteira.empty
    if carteira_vazia:
        problema(GRAVE, "A carteira carregada está vazia",
                 "Rode: python -m agrosentinela.data.seed_builder")

    if getattr(base, "precisa_de_etl", False):
        problema(
            AVISO,
            "A fonte escolhida é «dados oficiais do BCB», mas eles não existem aqui",
            "Na barra lateral, abra «Fonte dos dados» e volte para «Automática».",
        )

    p("")
    p("  Validação de esquema:")
    for nome, quadro in base.como_dict().items():
        if nome not in DATASETS_POR_NOME:
            continue
        if quadro is None or quadro.empty:
            p(f"     {nome:<22} vazio (opcional)" if nome not in
              ("municipios", "carteira") else f"     {nome:<22} VAZIO")
            continue
        erros = validar(quadro, nome)
        if erros:
            for e in erros:
                p(f"     {nome:<22} {e}")
                problema(AVISO, f"Esquema de {nome}: {e}",
                         "Regere a amostra: python -m agrosentinela.data.seed_builder")
        else:
            p(f"     {nome:<22} OK  ({len(quadro):,} linhas, "
              f"{quadro.shape[1]} colunas)".replace(",", "."))
    return base


# ==========================================================================
# 5. Pipeline
# ==========================================================================

def verificar_pipeline(base: Any) -> Any:
    secao("5. PIPELINE COMPLETO (offline, sem IA)")
    if base is None:
        p("  pulado: a base não carregou")
        return None

    from agrosentinela.orchestrator import Orquestrador

    def executar() -> Any:
        return Orquestrador(base=base).executar(
            horizonte_dias=7, cenario="seca", intensidade_cenario=1.4,
            modo_clima="sintetico", usar_llm=False, max_mensagens=8,
            persistir=False, respeitar_supressao=False,
        )

    silencio = io.StringIO()
    with redirect_stdout(silencio), redirect_stderr(silencio):
        resultado = tentar("Orquestrador.executar()", executar,
                           dica="Envie o relatório completo.")
    if resultado is None:
        return None

    for etapa in resultado.contexto.rastro:
        marca = "OK " if etapa.sucesso else "FALHOU"
        p(f"  {marca} {etapa.agente:<20} {etapa.duracao_s:6.2f}s  {etapa.resumo[:70]}")
        if not etapa.sucesso:
            problema(GRAVE, f"Agente {etapa.agente} falhou",
                     "Envie o relatório completo.")

    p("")
    item("Alertas gerados", len(resultado.contexto.alertas))
    item("Mensagens geradas", len(resultado.contexto.mensagens))
    item("Tempo total", f"{resultado.contexto.duracao_total_s:.2f}s")

    if not resultado.contexto.alertas:
        problema(AVISO, "O cenário de seca não gerou alerta nenhum",
                 "Esperava-se pelo menos um. Envie o relatório.")

    # Colunas que a interface consome
    quadro = resultado.alertas_df
    essenciais = ("lat", "lon", "municipio", "uf", "severidade", "score")
    recentes = ("setor", "perda_estimada_reais", "protecao_municipio")

    faltando = [c for c in essenciais if c not in quadro.columns]
    item("Colunas essenciais nos alertas",
         "todas presentes" if not faltando else f"FALTAM {faltando}")
    if faltando:
        problema(GRAVE, f"Colunas essenciais ausentes nos alertas: {faltando}",
                 "Envie o relatório completo.")

    sem_recentes = [c for c in recentes if c not in quadro.columns]
    if sem_recentes:
        item("Colunas da versão nova", f"ausentes: {sem_recentes}")
        problema(NOTA, "Esta cópia do projeto é anterior às últimas correções",
                 "Substitua a pasta pelo ZIP mais recente.")
    else:
        item("Colunas da versão nova", "todas presentes")
    return resultado


# ==========================================================================
# 6. Páginas
# ==========================================================================

def verificar_paginas(resultado: Any) -> None:
    secao("6. PÁGINAS DO APLICATIVO")
    p("  Cada página é executada de cima a baixo com dublês de interface.")
    p("  Isto reproduz o que acontece quando você clica na aba.")
    p("")

    try:
        from conftest_stubs import _ParouAPagina, instalar_dubles
    except ImportError:
        p("  PULADO: tests/conftest_stubs.py não existe nesta cópia do projeto.")
        p("  (faz parte da versão nova — substitua a pasta pelo ZIP mais recente)")
        problema(NOTA, "Não foi possível testar as páginas",
                 "Esta cópia não tem tests/conftest_stubs.py. Use o ZIP novo.")
        return

    instalar_dubles()
    import streamlit as st

    if resultado is not None:
        st.session_state["resultado"] = resultado

    arquivos = [RAIZ / "app.py", *sorted((RAIZ / "pages").glob("*.py"))]
    for caminho in arquivos:
        nome = caminho.name
        silencio = io.StringIO()
        try:
            with redirect_stdout(silencio), redirect_stderr(silencio):
                codigo = compile(caminho.read_text(encoding="utf-8"),
                                 str(caminho), "exec")
                exec(codigo, {"__name__": "__main__", "__file__": str(caminho)})  # noqa: S102
            p(f"  OK      {nome}")
        except _ParouAPagina:
            p(f"  OK      {nome}  (parou em st.stop, normal)")
        except Exception as exc:  # noqa: BLE001
            p(f"  FALHOU  {nome}: {type(exc).__name__}: {exc}")
            for linha in traceback.format_exc().strip().splitlines()[-5:]:
                p(f"            {linha}")
            problema(GRAVE, f"A página {nome} quebra: {type(exc).__name__}: {exc}",
                     "Envie o relatório completo.")


# ==========================================================================
# 7. Regras, personas e fontes externas
# ==========================================================================

def verificar_componentes() -> None:
    secao("7. REGRAS, PERSONAS E CATÁLOGOS")

    def regras() -> Any:
        from agrosentinela.rules.engine import MotorRegras

        motor = MotorRegras()
        item("Regras carregadas", f"{len(motor.regras)} (v{motor.versao})")
        return motor

    tentar("MotorRegras()", regras,
           dica="Confira se src/agrosentinela/rules/rules.yaml está íntegro.")

    def personas() -> None:
        from agrosentinela.personas import PERSONAS, SETORES

        item("Personas", len(PERSONAS))
        item("Setores", len(SETORES))

    tentar("personas", personas)

    def catalogo() -> None:
        from agrosentinela.etl_catalogo import resumo

        r = resumo()
        item("Arquivos do BCB catalogados", r["total"])
        item("Arquivos consumidos", f"{r['usados']} ({r['cobertura_pct']}%)")

    tentar("etl_catalogo", catalogo)

    def modelo() -> None:
        from agrosentinela.data.modelo_integrado import resumo

        r = resumo()
        item("Entidades no modelo integrado", r["entidades"])
        item("Ligações declaradas", r["ligacoes"])
        item("Grafo conexo", "sim" if r["grafo_conexo"] else "NÃO")
        if not r["grafo_conexo"]:
            problema(AVISO, "O grafo de integração não está conexo",
                     "Envie o relatório.")

    tentar("modelo_integrado", modelo)

    secao("8. FONTES EXTERNAS (modo offline)")
    def fontes() -> None:
        from agrosentinela.external import CONECTORES, obter_conector
        from agrosentinela.fontes_externas import resumo

        r = resumo()
        item("Fontes catalogadas", r["total"])
        item("Todas gratuitas", "sim" if r["todas_gratuitas"] else "NÃO")
        p("")
        for chave in sorted(set(CONECTORES)):
            try:
                conector = obter_conector(chave, offline=True)
                res = conector.obter(**conector._params_sonda())
                estado = "vazio (esperado)" if res.vazio else f"{len(res.dados)} linhas"
                p(f"     {chave:<20} {res.origem:<22} {estado}")
            except Exception as exc:  # noqa: BLE001
                p(f"     {chave:<20} FALHOU: {type(exc).__name__}: {exc}")
                problema(GRAVE, f"Conector {chave} falha mesmo offline: {exc}",
                         "Envie o relatório.")

    tentar("fontes externas", fontes)


# ==========================================================================
# 9. Configuração e segredos
# ==========================================================================

def verificar_configuracao() -> None:
    secao("9. CONFIGURAÇÃO")
    from agrosentinela.config import get_settings

    s = get_settings()
    item("Fonte de dados padrão", s.fonte_dados)
    item("Nível de log", s.log_level)

    tem_chave = bool(os.environ.get("GROQ_API_KEY"))
    item("GROQ_API_KEY no ambiente", "sim" if tem_chave else "não")
    if not tem_chave:
        p("        (não é problema: sem chave, as mensagens saem por")
        p("         modelos de texto determinísticos, e a interface avisa)")

    env = RAIZ / ".env"
    item("Arquivo .env presente", "sim" if env.exists() else "não")

    gitignore = RAIZ / ".gitignore"
    if env.exists() and gitignore.exists():
        protegido = ".env" in gitignore.read_text(encoding="utf-8")
        item(".env protegido no .gitignore", "sim" if protegido else "NÃO")
        if not protegido:
            problema(GRAVE, ".env NÃO está no .gitignore",
                     "Acrescente a linha '.env' ao .gitignore ANTES de publicar "
                     "no GitHub — senão a sua chave da Groq vai junto.")


# ==========================================================================
# Resumo
# ==========================================================================

def resumo_final() -> int:
    secao("RESUMO")
    if not PROBLEMAS:
        p("  Nenhum problema encontrado. O aplicativo está saudável.")
        return 0

    graves = [x for x in PROBLEMAS if x[0] == GRAVE]
    avisos = [x for x in PROBLEMAS if x[0] == AVISO]
    notas = [x for x in PROBLEMAS if x[0] == NOTA]

    item("Problemas graves", len(graves))
    item("Avisos", len(avisos))
    item("Notas", len(notas))

    for gravidade, lista in ((GRAVE, graves), (AVISO, avisos), (NOTA, notas)):
        if not lista:
            continue
        p("")
        p(f"  --- {gravidade} ---")
        for i, (_, titulo, acao) in enumerate(lista, start=1):
            p(f"  {i}. {titulo}")
            p(f"     → {acao}")

    p("")
    if graves:
        p("  Há problemas graves: o aplicativo pode não funcionar corretamente.")
    else:
        p("  Nada grave. Avisos e notas não impedem o uso.")
    return 1 if graves else 0


def main() -> int:
    p("")
    p("#" * 74)
    p("#  DIAGNÓSTICO DO AGROSENTINELA")
    p(f"#  {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}")
    p("#" * 74)

    try:
        from agrosentinela.utils.logging_setup import (
            _preparar_saida_unicode, configurar_logging,
        )

        _preparar_saida_unicode()
        configurar_logging("ERROR")      # só erros; o relatório é o que importa
    except Exception:  # noqa: BLE001
        pass

    verificar_ambiente()
    verificar_dependencias()
    verificar_dados()
    base = verificar_carga()
    resultado = verificar_pipeline(base)
    verificar_paginas(resultado)
    verificar_componentes()
    verificar_configuracao()
    codigo = resumo_final()

    p("")
    p("=" * 74)
    try:
        SAIDA.write_text("\n".join(LINHAS), encoding="utf-8")
        p(f"  Relatório salvo em: {SAIDA}")
        p("  Envie esse arquivo (ou cole o conteúdo) para análise.")
    except Exception as exc:  # noqa: BLE001
        p(f"  Não foi possível gravar {SAIDA}: {exc}")
    p("=" * 74)
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
