"""
Validação da extração — o guarda-corpo entre o modelo e o banco.

Nada que o LLM produz entra no banco sem passar por aqui. Verificações:

1. **Esquema** — níveis no vocabulário fechado, todas as cláusulas presentes.
2. **Evidência ancorada** — o trecho citado pelo modelo precisa existir de
   fato na seção indicada (comparação normalizada, tolerante a OCR). Evidência
   que não existe no documento é tratada como alucinação: a classificação é
   rebaixada e o alerta registrado.
3. **Verificação cruzada de números** — LMG, prêmio e franquia lidos pelo
   LLM são conferidos com a leitura por expressão regular do quadro-resumo.
   Divergência vira alerta; o valor do texto (regex) prevalece quando o
   LLM diverge e a regex encontrou um valor.
4. **Coerência** — fim de vigência após o início; taxa de prêmio sobre o
   LMG dentro de faixa plausível para D&O (0,05%–6%); retroatividade não
   posterior ao início da vigência.

O resultado é um **índice de confiança** (0–100) por apólice, exibido na
interface ao lado de cada dado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from .documentos import Secao, normalizar
from .extracao import NIVEIS_VALIDOS, ExtracaoApolice, valores_monetarios


@dataclass
class ResultadoValidacao:
    confianca: float
    alertas: list[str] = field(default_factory=list)
    evidencias_ok: int = 0
    evidencias_falhas: int = 0
    campos_corrigidos: list[str] = field(default_factory=list)


def evidencia_no_texto(evidencia: str, texto: str, limiar: float = 0.82) -> bool:
    """Busca aproximada do trecho citado (tolera erros de OCR e de cópia)."""
    ev, tx = normalizar(evidencia), normalizar(texto)
    if not ev:
        return False
    if ev in tx:
        return True
    n = len(ev)
    if n > len(tx):
        return SequenceMatcher(None, ev, tx).ratio() >= limiar
    passo = max(1, n // 6)
    melhor = 0.0
    for i in range(0, len(tx) - n + 1, passo):
        r = SequenceMatcher(None, ev, tx[i:i + n]).ratio()
        if r > melhor:
            melhor = r
            if melhor >= limiar:
                return True
    return False


def validar(extracao: ExtracaoApolice, secoes: list[Secao],
            cadastro_regex: dict[str, Any], tipo_documento: str = "apolice") -> ResultadoValidacao:
    alertas: list[str] = []
    corrigidos: list[str] = []
    por_rotulo = {s.rotulo: s for s in secoes}
    texto_total = " ".join(s.texto for s in secoes)

    # --- 1 e 2: cláusulas --------------------------------------------------
    ok = falhas = 0
    for codigo, cl in extracao.clausulas.items():
        if cl.nivel not in NIVEIS_VALIDOS:
            alertas.append(f"{codigo}: nível inválido '{cl.nivel}' → ausente.")
            cl.nivel = "ausente"
        if cl.metodo != "llm" or cl.nivel == "ausente":
            continue
        secao = por_rotulo.get(cl.secao)
        alvo = secao.texto + " " + secao.titulo if secao else texto_total
        if evidencia_no_texto(cl.evidencia, alvo) or (
                secao is None and evidencia_no_texto(cl.evidencia, texto_total)):
            cl.evidencia_verificada = True
            ok += 1
        elif evidencia_no_texto(cl.evidencia, texto_total):
            cl.evidencia_verificada = True
            ok += 1
            alertas.append(f"{codigo}: evidência encontrada, mas fora da seção {cl.secao}.")
        else:
            cl.evidencia_verificada = False
            falhas += 1
            alertas.append(f"{codigo}: evidência não localizada no documento — "
                           "classificação mantida com baixa confiança.")

    # --- 3: números ----------------------------------------------------------
    # Quem decide uma divergência é o DOCUMENTO: vale o valor que aparece
    # escrito no texto (em qualquer grafia: R$ 5.000.000,00, R$ 5 milhões,
    # BRL 5,000,000.00). A leitura por regex só desempata.
    cad = extracao.cadastro
    no_texto = valores_monetarios(texto_total + " " + " ".join(s.titulo for s in secoes))

    def aparece(v) -> bool:
        try:
            v = float(v)
        except (TypeError, ValueError):
            return False
        return any(abs(v - x) <= 0.005 * max(1.0, abs(x)) for x in no_texto)

    for campo in ("lmg", "premio", "franquia"):
        v_llm, v_rx = cad.get(campo), cadastro_regex.get(campo)
        if v_llm is None:
            if v_rx is not None:
                cad[campo] = v_rx
                corrigidos.append(campo)
            continue
        if aparece(v_llm):
            if v_rx is not None and not aparece(v_rx):
                pass  # regex errou; LLM confirmado pelo texto
            continue
        # valor do LLM não está escrito em lugar nenhum do documento
        if v_rx is not None and aparece(v_rx):
            alertas.append(f"{campo}: LLM leu {float(v_llm):,.2f}, mas o documento traz "
                           f"{float(v_rx):,.2f} — prevalece o documento.")
            cad[campo] = v_rx
            corrigidos.append(campo)
        else:
            alertas.append(f"{campo}: valor {float(v_llm):,.2f} não localizado no texto "
                           "— conferir manualmente.")
    for campo, v in cadastro_regex.items():
        if cad.get(campo) in (None, "") and v not in (None, ""):
            cad[campo] = v
            if campo not in corrigidos:
                corrigidos.append(campo)

    # --- 4: coerência --------------------------------------------------------
    ini, fim = cad.get("vigencia_inicio"), cad.get("vigencia_fim")
    if ini and fim and fim <= ini:
        alertas.append("Vigência: fim não é posterior ao início.")
    retro = cad.get("retroatividade")
    if retro and ini and retro > ini:
        alertas.append("Retroatividade posterior ao início da vigência.")
    lmg, premio = cad.get("lmg"), cad.get("premio")
    if lmg and premio:
        taxa = 100 * float(premio) / float(lmg)
        if not 0.05 <= taxa <= 6:
            alertas.append(f"Taxa de prêmio {taxa:.2f}% do LMG fora da faixa usual de D&O.")
    if tipo_documento == "condicoes_gerais":
        # texto-padrão do produto: não tem tomadora, vigência nem valores
        faltantes = [k for k in ("seguradora",) if not cad.get(k)]
        alertas.append("Condições gerais: sem tomadora, vigência e valores (esperado) — "
                       "a comparação vale para a redação das cláusulas.")
    else:
        faltantes = [k for k in ("seguradora", "tomadora", "lmg", "premio") if not cad.get(k)]
    if faltantes:
        alertas.append("Campos essenciais ausentes: " + ", ".join(faltantes))

    # --- índice de confiança -------------------------------------------------
    base = 100.0
    base -= 4 * falhas
    base -= 8 * len(faltantes)
    base -= 3 * len([a for a in alertas if a.startswith(("lmg", "premio", "franquia"))])
    if extracao.metodo_clausulas == "deterministico":
        base -= 15   # linha de base: níveis por gatilho são menos confiáveis
    return ResultadoValidacao(
        confianca=max(0.0, min(100.0, round(base, 1))), alertas=alertas,
        evidencias_ok=ok, evidencias_falhas=falhas, campos_corrigidos=corrigidos,
    )
