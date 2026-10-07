"""
Testes do Projeto Final — análise e comparação de apólices D&O.

O caminho com LLM é testado com um *dublê* do cliente Groq que responde a
partir do gabarito (e, de propósito, inventa uma evidência e erra um número),
para verificar o encanamento, o esquema e — principalmente — os guarda-corpos
de validação. A qualidade real do modelo é medida pelo script
``scripts/processar_acervo.py --llm``.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from agrosentinela.config import APOLICES_DIR, get_settings  # noqa: E402
from agrosentinela.projeto_final import avaliacao as av  # noqa: E402
from agrosentinela.projeto_final import extracao as ex  # noqa: E402
from agrosentinela.projeto_final.agentes import OrquestradorApolices  # noqa: E402
from agrosentinela.projeto_final.clausulas import CLAUSULAS  # noqa: E402
from agrosentinela.projeto_final.consulta import AgenteConsulta  # noqa: E402
from agrosentinela.projeto_final.documentos import (  # noqa: E402
    agrupar_arquivos, ler_documento, segmentar,
)
from agrosentinela.projeto_final.perfil_risco import montar_perfil  # noqa: E402
from agrosentinela.projeto_final.relator import numeros_orfaos  # noqa: E402
from agrosentinela.projeto_final.repositorio import Repositorio  # noqa: E402
from agrosentinela.projeto_final.simulador import AVISO_SIMULACAO, acervo  # noqa: E402

DOCS = APOLICES_DIR / "documentos"


def _pdf(ident: str) -> tuple[str, bytes]:
    f = next(p for p in sorted(DOCS.glob(f"{ident}*.pdf")) if "digital" not in p.name)
    return f.name, f.read_bytes()


def _ids_pdf(seguradora: str | None = None, tomadora: str | None = None) -> list[str]:
    """Identificadores com PDF nativo, filtrados por seguradora/tomadora."""
    out = []
    for g in av.gabarito().values():
        if g["formato"] != "pdf":
            continue
        if seguradora and g["seguradora_codigo"] != seguradora:
            continue
        if tomadora and g["tomadora_codigo"] != tomadora:
            continue
        out.append(g["identificador"])
    return sorted(out)


def _tomadora_com_3_pdfs() -> list[str]:
    from collections import defaultdict

    por = defaultdict(list)
    for i in _ids_pdf():
        por[av.gabarito()[i]["tomadora_codigo"]].append(i)
    return next(v for v in por.values() if len(v) >= 3)[:3]


# --------------------------------------------------------------- dublê LLM
class GroqFalso:
    """Responde a partir do gabarito; erra de propósito para testar a validação."""

    disponivel = True

    def __init__(self, ident: str) -> None:
        self.settings = get_settings()
        self.g = av.gabarito()[ident]
        self.chamadas: list[str] = []

    def reiniciar_orcamento(self, *_a, **_k) -> None:
        pass

    def json(self, *, sistema: str, usuario: str, tarefa: str = "", **_k):
        self.chamadas.append(tarefa)
        if tarefa == "pf_cadastro":
            g = self.g
            return {"seguradora": g["seguradora"], "numero_apolice": g["numero_apolice"],
                    "tomadora": g["tomadora"], "tomadora_cnpj": g["tomadora_cnpj"],
                    "segmento": g["segmento"], "municipio": g["municipio"], "uf": g["uf"],
                    "vigencia_inicio": g["vigencia_inicio"], "vigencia_fim": g["vigencia_fim"],
                    "retroatividade": g["retroatividade"],
                    "retroatividade_ilimitada": g["retroatividade_ilimitada"],
                    "lmg": g["lmg"] * 10,          # erro proposital de leitura
                    "premio": g["premio"], "franquia": g["franquia"]}
        # cláusulas: localiza a seção pelo rótulo no prompt
        secoes = dict(re.findall(r"\[(S\d+)\] [^\n]*\n([^\n]+)", usuario))
        itens = []
        for i, c in enumerate(CLAUSULAS):
            nivel = self.g["avaliacoes"][c.codigo]
            sec, ev = "", ""
            if nivel != "ausente" and secoes:
                sec = list(secoes)[min(i, len(secoes) - 1)]
                ev = " ".join(secoes[sec].split()[:12])
            if c.codigo == "OPE-05" and nivel != "ausente":
                ev = "texto que não existe em lugar nenhum da apólice simulada"
            itens.append({"codigo": c.codigo, "nivel": nivel, "secao": sec, "evidencia": ev,
                          "justificativa": "teste"})
        return {"clausulas": itens}

    def texto(self, **_k) -> str:
        return "## Leitura\nA apólice tem LMG de 999.999.999 (número inventado)."

    def chat(self, mensagens, tools=None, **_k):
        # 1ª volta: chama uma ferramenta; 2ª: responde
        if not any(m.get("role") == "tool" for m in mensagens):
            return {"choices": [{"message": {"content": "", "tool_calls": [{
                "id": "t1", "type": "function", "function": {
                    "name": "apolices_por_clausula",
                    "arguments": json.dumps({"codigo": "DEF-01", "niveis": ["ampla"]})}}]}}]}
        return {"choices": [{"message": {"content": "Encontrei as apólices na tabela."}}]}


# --------------------------------------------------------------- acervo
def test_acervo_tem_5_seguradoras_com_20_apolices_cada():
    from collections import Counter

    docs = acervo()
    por_seg = Counter(d.espec.seguradora_codigo for d in docs)
    assert len(por_seg) >= 5 and min(por_seg.values()) >= 20
    assert all("(fictícia)" in d.espec.seguradora for d in docs)
    assert all(AVISO_SIMULACAO in d.texto() for d in docs)
    assert len(av.gabarito()) == len(docs)


def test_acervo_cobre_regioes_e_perfis():
    docs = acervo()
    assert {d.espec.regiao for d in docs} == {"Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"}
    assert len({d.espec.uf for d in docs}) >= 20
    assert {"familiar", "pequeno", "medio", "grande", "latifundio"} <= {d.espec.perfil for d in docs}


def test_cada_seguradora_tem_arquitetura_propria():
    """Documentos de seguradoras diferentes não podem seguir o mesmo template."""
    from agrosentinela.projeto_final.simulador import SEGURADORAS

    assert len({s.modelo for s in SEGURADORAS}) == len(SEGURADORAS)
    assert len({s.formato_valor for s in SEGURADORAS}) >= 3
    assert len({s.formato_data for s in SEGURADORAS}) >= 3


def test_gabarito_coerente_com_o_documento():
    """Toda cláusula marcada como presente aparece no documento, e vice-versa."""
    from agrosentinela.projeto_final.modelos_documento import codigos_presentes

    for d in acervo():
        pres = codigos_presentes(d)
        for c in CLAUSULAS:
            assert (d.espec.avaliacoes[c.codigo] != "ausente") == (c.codigo in pres), \
                (d.espec.identificador, c.codigo)


def test_coerencia_regional_e_de_perfil():
    """Familiar sem Side C; cobertura no exterior restrita para quem não exporta."""
    for d in acervo():
        e = d.espec
        if e.perfil == "familiar":
            assert e.lmg <= 3_000_000
            assert e.avaliacoes["ESC-04"] in ("ausente", "restrita")


def test_formatos_de_valor_e_data():
    assert ex.valor_reais("BRL 30,000,000.00") == 30_000_000.0
    assert ex.valor_reais("R$ 1,5 milhão") == 1_500_000.0
    assert ex.valor_reais("R$ 25 mil") == 25_000.0
    assert ex.valor_reais("R$ 5.000.000,00 (cinco milhões de reais)") == 5_000_000.0
    from datetime import date

    assert ex.data_br("1º de julho de 2026") == date(2026, 7, 1)
    assert ex.data_br("01.07.2026") == date(2026, 7, 1)
    assert ex.data_br("2026-07-01") == date(2026, 7, 1)


def test_arquivos_gerados_existem_em_tres_formatos():
    nomes = [p.name for p in DOCS.iterdir()]
    assert any(n.endswith("_digitalizada.pdf") for n in nomes)
    assert any(n.endswith(".jpg") for n in nomes)
    assert sum(1 for n in nomes if n.endswith(".pdf")) >= 40


def test_agrupa_fotos_da_mesma_apolice():
    g = agrupar_arquivos([("AP023-IPE-T08_foto_p2.jpg", b"x"), ("AP023-IPE-T08_foto_p1.jpg", b"y")])
    assert list(g) == ["AP023-IPE-T08"]
    assert [n for n, _ in g["AP023-IPE-T08"]] == ["AP023-IPE-T08_foto_p1.jpg",
                                                   "AP023-IPE-T08_foto_p2.jpg"]


# --------------------------------------------------------------- leitura
def test_leitura_e_segmentacao_pdf():
    ident = _ids_pdf("ATA")[0]
    nome, conteudo = _pdf(ident)
    doc = ler_documento(ident, [(nome, conteudo)])
    assert doc.metodo_resumo == "texto_pdf"
    secoes = segmentar(doc.texto)
    assert len(secoes) >= 20


def test_extracao_deterministica_le_quadros_de_todas_as_arquiteturas():
    """O quadro de dados muda de lugar e de formato entre seguradoras."""
    from agrosentinela.projeto_final.simulador import SEGURADORAS

    for s in SEGURADORAS:
        ident = _ids_pdf(s.codigo)[0]
        nome, conteudo = _pdf(ident)
        doc = ler_documento(ident, [(nome, conteudo)])
        r = av.avaliar(ident, ex.extrair_cadastro_regex(doc.texto), {})
        assert r["acuracia_campos"] >= 85.0, (s.codigo, r["erros_campos"])


def test_valor_reais():
    assert ex.valor_reais("R$ 5.000.000,00") == 5_000_000.0
    assert ex.valor_reais("20 milhões") == 20_000_000.0


# --------------------------------------------------------------- caminho LLM
def test_pipeline_com_llm_falso_valida_evidencia_e_numeros(tmp_path):
    nome, conteudo = _pdf(_ids_pdf("JAC")[0])
    ident = av.identificador_de(nome)
    falso = GroqFalso(ident)
    orq = OrquestradorApolices(repo=Repositorio(tmp_path / "t.sqlite", semear=False),
                               cliente=falso)
    ctx = orq.ingerir([(nome, conteudo)], usar_llm=True)
    it = ctx.itens[0]
    assert "pf_cadastro" in falso.chamadas and "pf_clausulas" in falso.chamadas
    assert it.extracao.metodo_clausulas == "llm"
    # o LMG 10x maior foi corrigido pelo quadro-resumo
    assert it.extracao.cadastro["lmg"] == av.gabarito()[ident]["lmg"]
    assert any(a.startswith("lmg") for a in it.validacao.alertas)
    # a evidência inventada foi detectada
    if av.gabarito()[ident]["avaliacoes"]["OPE-05"] != "ausente":
        assert it.extracao.clausulas["OPE-05"].evidencia_verificada is False
    assert it.avaliacao["acuracia_clausulas"] == 100.0
    assert Repositorio(tmp_path / "t.sqlite", semear=False).contagem()["apolices"] == 1


def test_comparacao_relatorio_e_verificador_de_numeros(tmp_path):
    repo = Repositorio(tmp_path / "c.sqlite", semear=False)
    orq = OrquestradorApolices(repo=repo, cliente=None)
    orq.ingerir([_pdf(i) for i in _tomadora_com_3_pdfs()], usar_llm=False)
    ids = repo.apolices()["id"].tolist()
    ctx = orq.comparar(ids, usar_llm=False)
    assert ctx.comparacao is not None and ctx.relatorio is not None
    assert ctx.relatorio.metodo == "deterministico"
    assert "Aviso" in ctx.relatorio.texto
    assert all(e.sucesso for e in ctx.rastro), ctx.avisos
    # relatório por "IA" com número inventado → sinalizado
    ident = av.identificador_de(ids[0])
    orq_ia = OrquestradorApolices(repo=repo, cliente=GroqFalso(ident))
    ctx2 = orq_ia.comparar(ids, usar_llm=True)
    assert ctx2.relatorio.metodo == "llm"
    assert "999.999.999" in ctx2.relatorio.numeros_nao_verificados


def test_numeros_orfaos():
    fatos = {"lmg": 20000000.0, "escore": 81.5}
    assert numeros_orfaos("LMG de R$ 20.000.000 e escore 81,5", fatos) == []
    assert numeros_orfaos("prêmio de 12.345", fatos) == ["12.345"]


# --------------------------------------------------------------- perfil e consulta
def test_perfil_de_risco_ajusta_pesos_para_cooperativa_de_credito():
    p = montar_perfil("Coop X", "MA", "Cooperativa de crédito rural", None)
    pesos = p.pesos()
    assert pesos["AGR-01"] > 4 and pesos["AGR-02"] > 4


def test_agente_de_consulta_com_ferramentas(tmp_path):
    repo = Repositorio(tmp_path / "q.sqlite", semear=False)
    ids = _ids_pdf()[:2]
    OrquestradorApolices(repo=repo).ingerir([_pdf(i) for i in ids], usar_llm=False)
    from agrosentinela.projeto_final.agentes import tabela_escores

    ag = AgenteConsulta(repo, GroqFalso(ids[0]), tabela_escores(repo))
    r = ag.perguntar("quais pagam defesa fora do LMG?")
    assert r.modo == "llm" and r.ferramentas[0].nome == "apolices_por_clausula"
    assert r.ferramentas[0].erro is None
    det = AgenteConsulta(repo, None, tabela_escores(repo)).perguntar("ranking de seguradora melhor")
    assert det.modo == "deterministico" and det.tabelas


def test_base_inicial_existe_e_tem_todo_o_acervo():
    base = APOLICES_DIR / "base_inicial.sqlite"
    if not base.exists():
        pytest.skip("base inicial não gerada")
    assert Repositorio(base, semear=False).contagem()["apolices"] == len(av.gabarito())


def test_importador_de_lotes_externos_valida_gabarito(tmp_path):
    import importlib.util
    import shutil

    spec = importlib.util.spec_from_file_location(
        "importador", RAIZ / "scripts" / "importar_apolices_externas.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    g = dict(av.gabarito()[_ids_pdf()[0]])
    g["identificador"], g["arquivos"] = "EXT001-TST-X01", ["EXT001-TST-X01.pdf"]
    shutil.copy(DOCS / av.gabarito()[_ids_pdf()[0]]["arquivos"][0], tmp_path / "EXT001-TST-X01.pdf")
    assert mod.validar(tmp_path, [g], set()) == []
    ruim = dict(g, identificador="EXT002-TST-X02", seguradora="Chubb Seguros S.A.",
                avaliacoes={**g["avaliacoes"], "ESC-01": "otima"})
    erros = mod.validar(tmp_path, [ruim], set())
    assert any("fictícia" in e for e in erros) and any("níveis" in e for e in erros)
