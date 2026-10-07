"""
Melhorias motivadas pelos documentos reais (condições gerais de D&O com
50–100 páginas e apólices de Seguro Garantia).

Os testes usam textos FICTÍCIOS que imitam a estrutura encontrada nos
documentos reais; os PDFs reais não estão no repositório. Se estiverem na
máquina (data/apolices_reais/ ou na pasta indicada em AGRO_REAIS_DIR), o
último teste roda a validação completa contra o gabarito.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agrosentinela.projeto_final import extracao as ex  # noqa: E402
from agrosentinela.projeto_final.agentes import OrquestradorApolices  # noqa: E402
from agrosentinela.projeto_final.clausulas import CLAUSULAS  # noqa: E402
from agrosentinela.projeto_final.documentos import (  # noqa: E402
    Pagina, remover_sumario, segmentar,
)
from agrosentinela.projeto_final.repositorio import Repositorio  # noqa: E402
from agrosentinela.projeto_final.tipo_documento import classificar  # noqa: E402

GARANTIA_FICTICIA = """FRONTISPÍCIO DE APÓLICE SEGURO GARANTIA
DADOS DA SEGURADORA: SEGURADORA EXEMPLO S.A. (FICTÍCIA)
Nº Apólice Seguro Garantia: 00-0000-0000000
DADOS DO SEGURADO: ÓRGÃO PÚBLICO FICTÍCIO
DADOS DO TOMADOR: EMPRESA FICTÍCIA LTDA
Objeto da garantia: garantir a execução do contrato nº 1/2024.
Valor da garantia: R$ 100.000,00. Vigência: das 24h de 01/01/2024 às 24h de 01/01/2025.
CLÁUSULA ÚNICA — o seguro garantia garante o fiel cumprimento
das obrigações assumidas pelo tomador no contrato principal.
"""


def _cg_ficticia(n_cap: int = 40) -> str:
    """Condições gerais fictícias e longas, com sumário, glossário e exclusões."""
    linhas = ["CONDIÇÕES GERAIS", "SEGURO DE RESPONSABILIDADE CIVIL DE ADMINISTRADORES E DIRETORES – D&O",
              "Ipê Branco Seguros S.A. (fictícia)", "SUMÁRIO",
              "1. DEFINIÇÕES .................................... 3",
              "2. OBJETIVO DO SEGURO ............................. 9",
              "3. EXCLUSÕES ...................................... 12",
              "4. ARBITRAGEM ..................................... 40",
              "1. DEFINIÇÕES",
              "1.1 Multa",
              "Penalidade pecuniária aplicada por autoridade. " * 5,
              "1.2 Segurado",
              "Pessoa física eleita para cargo de administrador. " * 5,
              "2. OBJETIVO DO SEGURO",
              "Este seguro garante o pagamento de perdas decorrentes de reclamações. " * 5,
              "3. EXCLUSÕES",
              "3.1 Poluição",
              "Esta apólice não cobre reclamações por poluição ou dano ambiental. " * 4,
              "3.2 Recuperação Judicial",
              "Excluem-se reclamações decorrentes de recuperação judicial ou falência. " * 4]
    for i in range(5, 5 + n_cap):
        linhas += [f"{i}. DISPOSIÇÃO OPERACIONAL NÚMERO {i}",
                   ("Texto operacional sem relação com as cláusulas da taxonomia, apenas para "
                    "alongar o documento como numa condição geral real. ") * 6]
    linhas += ["60. ARBITRAGEM",
               "As controvérsias serão resolvidas por arbitragem, conforme a Lei 9.307/1996. " * 3]
    return "\n".join(linhas)


# --------------------------------------------------------------- tipo de documento
def test_reconhece_seguro_garantia_como_fora_do_escopo():
    t = classificar(GARANTIA_FICTICIA)
    assert t.ramo == "garantia" and not t.e_do


def test_reconhece_condicoes_gerais_de_do():
    texto = _cg_ficticia()
    t = classificar(texto, ex.extrair_cadastro_regex(texto))
    assert t.e_do and t.tipo == "condicoes_gerais"


def test_acervo_simulado_e_todo_do_e_apolice():
    from agrosentinela.config import APOLICES_DIR
    from agrosentinela.projeto_final.documentos import ler_documento

    pasta = APOLICES_DIR / "documentos"
    for seg in ("ATA", "IPE", "JAC", "XIQ", "MUT", "MIN"):
        p = next(x for x in sorted(pasta.glob(f"*-{seg}-*.pdf")) if "digital" not in x.name)
        doc = ler_documento(p.name, [(p.name, p.read_bytes())], permitir_ocr=False)
        t = classificar(doc.texto, ex.extrair_cadastro_regex(doc.texto))
        assert (t.ramo, t.tipo) == ("do", "apolice"), p.name


def test_pipeline_recusa_documento_de_outro_ramo(tmp_path):
    repo = Repositorio(tmp_path / "g.sqlite", semear=False)
    ctx = OrquestradorApolices(repo=repo).ingerir(
        [("garantia.txt", GARANTIA_FICTICIA.encode("utf-8"))], usar_llm=False)
    it = ctx.itens[0]
    assert it.ignorado.startswith("fora do escopo") and "Seguro Garantia" in it.ignorado
    assert repo.contagem()["apolices"] == 0


def test_pipeline_grava_condicoes_gerais_com_tipo(tmp_path):
    repo = Repositorio(tmp_path / "cg.sqlite", semear=False)
    ctx = OrquestradorApolices(repo=repo).ingerir(
        [("cg.txt", _cg_ficticia().encode("utf-8"))], usar_llm=False)
    it = ctx.itens[0]
    assert not it.ignorado and it.extracao.tipo_documento == "condicoes_gerais"
    assert repo.apolices()["tipo_documento"].tolist() == ["condicoes_gerais"]
    assert any("Condições gerais" in a for a in it.validacao.alertas)


# --------------------------------------------------------------- leitura
def test_remove_sumario():
    pg = Pagina(1, "SUMÁRIO\n1. DEFINIÇÕES ....... 3\n2. OBJETIVO ........ 9\n"
                   "3. EXCLUSÕES ....... 12\nTexto que fica.", "texto_pdf")
    assert remover_sumario([pg]) >= 4
    assert pg.texto.strip() == "Texto que fica."


def test_marca_glossario_e_exclusoes():
    secoes = segmentar(_cg_ficticia(3))
    parte = {s.titulo: s.parte for s in secoes}
    assert parte["1.1 Multa"] == "glossario"
    assert parte["3.1 Poluição"] == "exclusoes"
    assert parte["2. OBJETIVO DO SEGURO"] == "geral"


def test_regras_nao_tomam_definicao_por_cobertura_e_entendem_exclusao():
    cl = ex.extrair_clausulas_deterministico(segmentar(_cg_ficticia(3)))
    assert cl["AGR-03"].nivel == "excluida"          # recuperação judicial só nas exclusões
    assert cl["EXC-03"].nivel != "ausente"           # poluição dentro das exclusões
    assert cl["OPE-02"].nivel != "ausente"           # arbitragem no fim do documento


def test_seguradora_provavel_no_rodape():
    texto = "Condições gerais sem quadro-resumo."
    assert ex.seguradora_provavel(texto, ["Ipê Branco Seguros S.A. Página 2 de 75"]) \
        == "Ipê Branco Seguros S.A."


def test_documento_longo_vai_ao_llm_por_trechos_e_alcanca_o_fim():
    secoes = segmentar(_cg_ficticia(60))
    assert ex.documento_longo(secoes)
    trechos = ex.selecionar_trechos(secoes, codigos=ex.LOTES_CODIGOS[1], por_codigo=4, tamanho=600)
    assert len(trechos) <= 14500
    assert "ARBITRAGEM" in trechos            # seção do fim do documento
    assert "· exclusões" in trechos


class _LLMLotes:
    disponivel = True

    def __init__(self):
        self.pedidos: list[str] = []

    def json(self, *, usuario: str, **_k):
        self.pedidos.append(usuario)
        codigos = [c.codigo for c in CLAUSULAS if c.codigo in usuario.split("TRECHOS")[0]]
        return {"clausulas": [{"codigo": c, "nivel": "padrao", "secao": "S1",
                               "evidencia": "x", "justificativa": "t"} for c in codigos]}


def test_llm_em_lotes_para_documento_longo():
    falso = _LLMLotes()
    out = ex.extrair_clausulas_llm(falso, segmentar(_cg_ficticia(60)))
    assert len(falso.pedidos) == len(ex.LOTES_CODIGOS)
    assert all(out[c.codigo].nivel == "padrao" for c in CLAUSULAS)


# --------------------------------------------------------------- documentos reais (opcional)
def _pasta_reais() -> Path | None:
    for p in (os.environ.get("AGRO_REAIS_DIR"), ROOT / "data" / "apolices_reais"):
        if p and Path(p).exists() and list(Path(p).glob("*.pdf")):
            return Path(p)
    return None


@pytest.mark.skipif(_pasta_reais() is None, reason="PDFs reais não disponíveis nesta máquina")
def test_documentos_reais_contra_o_gabarito(tmp_path):
    gab = json.loads((ROOT / "data" / "apolices_reais" / "gabarito_reais.json").read_text(encoding="utf-8"))
    por_hash = {d["sha256"]: d for d in gab["documentos"]}
    repo = Repositorio(tmp_path / "r.sqlite", semear=False)
    orq = OrquestradorApolices(repo=repo)
    vistos = 0
    for p in _pasta_reais().glob("*.pdf"):
        d = por_hash.get(hashlib.sha256(p.read_bytes()).hexdigest())
        if not d:
            continue
        vistos += 1
        it = orq.ingerir([(p.name, p.read_bytes())], usar_llm=False, reprocessar=True).itens[0]
        assert it.tipo.ramo == d["ramo"] and it.tipo.tipo == d["tipo"]
        if d["ramo"] != "do":
            assert it.ignorado.startswith("fora do escopo")
            continue
        esp = {c["codigo"]: c["nivel"] for c in d["clausulas"]}
        ok = sum((it.extracao.clausulas[k].nivel in ("ausente", "excluida"))
                 == (v in ("ausente", "excluida")) for k, v in esp.items())
        assert ok / len(esp) >= 0.70, (d["identificador"], ok)
    assert vistos >= 1
