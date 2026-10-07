"""
Cálculo dos **indicadores meteorológicos** que alimentam o motor de regras.

Cada indicador é uma métrica objetiva, calculada a partir da série diária de
uma célula de grade, e explicitamente dividida entre:

* **janela observada** (passado recente) — mede o que já aconteceu no solo;
* **janela prevista** (próximos dias)   — mede o que está por vir.

Essa separação é o que permite distinguir, por exemplo, "já estamos há 18
dias sem chuva" (observado) de "vem chuva forte na quinta" (previsto).

Todos os indicadores são documentados em ``docs/regras_negocio.md`` e
aparecem na interface, junto de cada alerta, para fins de auditoria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

LIMIAR_DIA_SECO_MM = 1.0
LIMIAR_DIA_CHUVOSO_MM = 1.0


@dataclass
class JanelaIndicadores:
    """Indicadores de uma célula em uma data de referência."""

    cell_id: str
    data_ref: date
    valores: dict[str, Any] = field(default_factory=dict)
    dia_pico: dict[str, str] = field(default_factory=dict)

    def como_dict(self) -> dict[str, Any]:
        return dict(self.valores)


def _num(serie: Sequence[Any], default: float = 0.0) -> list[float]:
    saida = []
    for v in serie:
        try:
            saida.append(default if v is None else float(v))
        except (TypeError, ValueError):
            saida.append(default)
    return saida


def _run_final(valores: Iterable[float], limiar: float) -> int:
    """Comprimento da sequência final de valores abaixo do limiar."""
    n = 0
    for v in reversed(list(valores)):
        if v < limiar:
            n += 1
        else:
            break
    return n


def _run_inicial(valores: Iterable[float], limiar: float) -> int:
    """Comprimento da sequência inicial de valores abaixo do limiar."""
    n = 0
    for v in valores:
        if v < limiar:
            n += 1
        else:
            break
    return n


def probabilidade_granizo(cape_max: float, rajada: float, prec_max: float) -> float:
    """
    Proxy de probabilidade de granizo (0–100).

    Não existe previsão pública direta de granizo de acesso livre; usamos um
    **índice convectivo composto**, documentado e auditável:

        f_cape  = (CAPE − 800) / 2200     — energia convectiva disponível
        f_vento = (rajada − 40) / 50      — cisalhamento/organização da célula
        f_chuva = (prec24h − 15) / 45     — presença de núcleo precipitante

        índice = 100 × (0,55·f_cape + 0,27·f_vento + 0,18·f_chuva)

    Com **porta de entrada**: se CAPE < 800 J/kg o índice é zero, pois sem
    energia convectiva não há formação de granizo relevante.

    O índice é uma *estimativa de ambiente favorável*, não uma previsão
    determinística — e é assim que aparece nas mensagens ao usuário.
    """
    if cape_max is None or cape_max < 800:
        return 0.0
    f_cape = min(max((cape_max - 800.0) / 2200.0, 0.0), 1.0)
    f_vento = min(max((rajada - 40.0) / 50.0, 0.0), 1.0)
    f_chuva = min(max((prec_max - 15.0) / 45.0, 0.0), 1.0)
    return round(100.0 * (0.55 * f_cape + 0.27 * f_vento + 0.18 * f_chuva), 1)


def calcular_indicadores(
    df_celula: pd.DataFrame,
    *,
    data_ref: date | None = None,
    horizonte_dias: int = 7,
    janela_passada: int = 14,
) -> JanelaIndicadores:
    """
    Calcula o pacote de indicadores de uma célula.

    Parameters
    ----------
    df_celula:
        Série diária da célula, com as colunas produzidas pelo provedor de
        clima (``data``, ``tmax``, ``tmin``, ``precipitacao``, ``et0``...).
    data_ref:
        Data de referência ("hoje"). Padrão: data corrente.
    horizonte_dias:
        Tamanho da janela de previsão considerada.
    janela_passada:
        Tamanho da janela observada considerada.
    """
    data_ref = data_ref or date.today()
    df = df_celula.copy()
    df["data"] = pd.to_datetime(df["data"]).dt.date
    df = df.sort_values("data").reset_index(drop=True)

    passado = df[df["data"] < data_ref].tail(janela_passada)
    futuro = df[df["data"] >= data_ref].head(horizonte_dias)
    futuro14 = df[df["data"] >= data_ref].head(14)

    prec_fut = _num(futuro.get("precipitacao", []))
    prec_pas = _num(passado.get("precipitacao", []))
    et0_fut = _num(futuro.get("et0", []))
    et0_pas = _num(passado.get("et0", []))
    tmin_fut = _num(futuro.get("tmin", []), default=99.0)
    tmax_fut = _num(futuro.get("tmax", []), default=-99.0)
    rajada_fut = _num(futuro.get("rajada", []))
    vento_fut = _num(futuro.get("vento_medio", []))
    cape_fut = _num(futuro.get("cape_max", []))
    umid_fut = _num(futuro.get("umidade_media", []), default=60.0)
    umidmin_fut = _num(futuro.get("umidade_min", []), default=45.0)
    prob_fut = _num(futuro.get("prob_precipitacao", []))

    # --- seca -------------------------------------------------------------
    secos_passados = _run_final(prec_pas, LIMIAR_DIA_SECO_MM)
    secos_previstos = _run_inicial(prec_fut, LIMIAR_DIA_SECO_MM)
    # Só encadeia passado + futuro se a sequência não foi interrompida hoje.
    dias_secos = secos_passados + secos_previstos if secos_passados > 0 else secos_previstos

    # --- balanço hídrico ---------------------------------------------------
    bh_passado = sum(prec_pas) - sum(et0_pas)
    bh_futuro = sum(prec_fut) - sum(et0_fut)

    prec_max_24h = max(prec_fut) if prec_fut else 0.0
    cape_max = max(cape_fut) if cape_fut else 0.0
    rajada_max = max(rajada_fut) if rajada_fut else 0.0

    valores: dict[str, Any] = {
        # precipitação
        "prec_1d": round(prec_fut[0], 1) if prec_fut else 0.0,
        "prec_3d": round(sum(prec_fut[:3]), 1),
        "prec_7d": round(sum(prec_fut[:7]), 1),
        "prec_14d": round(sum(_num(futuro14.get("precipitacao", []))), 1),
        "prec_max_24h": round(prec_max_24h, 1),
        "prec_passada_14d": round(sum(prec_pas), 1),
        "dias_com_chuva_7d": int(sum(1 for p in prec_fut[:7] if p >= LIMIAR_DIA_CHUVOSO_MM)),
        "prob_prec_max": round(max(prob_fut), 0) if prob_fut else 0.0,
        # seca
        "dias_secos_passados": int(secos_passados),
        "dias_secos_previstos": int(secos_previstos),
        "dias_secos_consecutivos": int(dias_secos),
        "balanco_hidrico_7d": round(bh_futuro, 1),
        "balanco_hidrico_14d": round(bh_passado, 1),
        "et0_7d": round(sum(et0_fut), 1),
        # temperatura
        "tmin_min": round(min(tmin_fut), 1) if tmin_fut else None,
        "tmax_max": round(max(tmax_fut), 1) if tmax_fut else None,
        "dias_tmin_le_3": int(sum(1 for t in tmin_fut if t <= 3.0)),
        "dias_tmin_le_0": int(sum(1 for t in tmin_fut if t <= 0.0)),
        "dias_tmax_ge_32": int(sum(1 for t in tmax_fut if t >= 32.0)),
        "dias_tmax_ge_35": int(sum(1 for t in tmax_fut if t >= 35.0)),
        "amplitude_max": round(max((a - b) for a, b in zip(tmax_fut, tmin_fut)), 1)
        if tmax_fut and tmin_fut
        else None,
        # vento e convecção
        "rajada_max": round(rajada_max, 1),
        "vento_medio_max": round(max(vento_fut), 1) if vento_fut else 0.0,
        "cape_max": round(cape_max, 0),
        "prob_granizo": probabilidade_granizo(cape_max, rajada_max, prec_max_24h),
        # umidade
        "umidade_media": round(sum(umid_fut) / len(umid_fut), 1) if umid_fut else None,
        "umidade_min": round(min(umidmin_fut), 1) if umidmin_fut else None,
    }

    # --- dia de pico de cada fenômeno (usado no texto da mensagem) --------
    dia_pico: dict[str, str] = {}
    if not futuro.empty:
        f = futuro.reset_index(drop=True)
        try:
            dia_pico["chuva"] = str(f.loc[pd.Series(prec_fut).idxmax(), "data"]) if prec_fut else ""
            dia_pico["frio"] = str(f.loc[pd.Series(tmin_fut).idxmin(), "data"]) if tmin_fut else ""
            dia_pico["calor"] = str(f.loc[pd.Series(tmax_fut).idxmax(), "data"]) if tmax_fut else ""
            dia_pico["vento"] = str(f.loc[pd.Series(rajada_fut).idxmax(), "data"]) if rajada_fut else ""
            dia_pico["convectivo"] = str(f.loc[pd.Series(cape_fut).idxmax(), "data"]) if cape_fut else ""
        except (ValueError, KeyError):  # pragma: no cover
            pass

    return JanelaIndicadores(
        cell_id=str(df_celula["cell_id"].iloc[0]) if "cell_id" in df_celula.columns and len(df_celula) else "",
        data_ref=data_ref,
        valores=valores,
        dia_pico=dia_pico,
    )


def calcular_por_celula(
    df_clima: pd.DataFrame,
    *,
    data_ref: date | None = None,
    horizonte_dias: int = 7,
    janela_passada: int = 14,
) -> pd.DataFrame:
    """Aplica :func:`calcular_indicadores` a todas as células de uma vez."""
    if df_clima is None or df_clima.empty:
        return pd.DataFrame()
    linhas = []
    for cell_id, grupo in df_clima.groupby("cell_id", sort=False):
        jan = calcular_indicadores(
            grupo,
            data_ref=data_ref,
            horizonte_dias=horizonte_dias,
            janela_passada=janela_passada,
        )
        linha = {"cell_id": cell_id, **jan.valores}
        for k, v in jan.dia_pico.items():
            linha[f"dia_pico_{k}"] = v
        linhas.append(linha)
    return pd.DataFrame(linhas)


def descricao_indicadores() -> list[dict[str, str]]:
    """Dicionário legível dos indicadores — exibido na UI e na documentação."""
    return [
        {"indicador": "prec_1d / prec_3d / prec_7d / prec_14d", "unidade": "mm",
         "janela": "prevista", "descricao": "Precipitação acumulada prevista no horizonte."},
        {"indicador": "prec_max_24h", "unidade": "mm",
         "janela": "prevista", "descricao": "Maior acumulado diário previsto na janela."},
        {"indicador": "prec_passada_14d", "unidade": "mm",
         "janela": "observada", "descricao": "Chuva acumulada nos 14 dias anteriores."},
        {"indicador": "dias_com_chuva_7d", "unidade": "dias",
         "janela": "prevista", "descricao": "Dias com chuva ≥ 1 mm nos próximos 7 dias."},
        {"indicador": "dias_secos_passados", "unidade": "dias",
         "janela": "observada", "descricao": "Sequência de dias sem chuva encerrada hoje."},
        {"indicador": "dias_secos_consecutivos", "unidade": "dias",
         "janela": "combinada", "descricao": "Sequência seca observada somada à prevista."},
        {"indicador": "balanco_hidrico_14d", "unidade": "mm",
         "janela": "observada", "descricao": "Chuva menos evapotranspiração (ET0) nos últimos 14 dias."},
        {"indicador": "balanco_hidrico_7d", "unidade": "mm",
         "janela": "prevista", "descricao": "Chuva menos ET0 nos próximos 7 dias."},
        {"indicador": "tmin_min", "unidade": "°C",
         "janela": "prevista", "descricao": "Menor temperatura mínima prevista (abrigo)."},
        {"indicador": "dias_tmin_le_3 / dias_tmin_le_0", "unidade": "dias",
         "janela": "prevista", "descricao": "Dias com mínima ≤ 3 °C e ≤ 0 °C (risco de geada)."},
        {"indicador": "tmax_max / dias_tmax_ge_35", "unidade": "°C / dias",
         "janela": "prevista", "descricao": "Pico térmico e dias de estresse por calor."},
        {"indicador": "rajada_max / vento_medio_max", "unidade": "km/h",
         "janela": "prevista", "descricao": "Rajada máxima e vento sustentado máximo."},
        {"indicador": "cape_max", "unidade": "J/kg",
         "janela": "prevista", "descricao": "Energia potencial convectiva disponível (pico)."},
        {"indicador": "prob_granizo", "unidade": "índice 0–100",
         "janela": "prevista", "descricao": "Índice convectivo composto (proxy de granizo)."},
        {"indicador": "umidade_media / umidade_min", "unidade": "%",
         "janela": "prevista", "descricao": "Umidade relativa média e mínima previstas."},
    ]


def agora_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def contexto_climatico_resumido(valores: Mapping[str, Any]) -> str:
    """Resumo textual curto dos indicadores — vai no prompt do LLM."""
    partes = []
    v = valores
    if v.get("prec_7d") is not None:
        partes.append(f"chuva prevista 7 dias: {v['prec_7d']:.0f} mm")
    if v.get("prec_max_24h"):
        partes.append(f"maior acumulado em 24h: {v['prec_max_24h']:.0f} mm")
    if v.get("dias_secos_consecutivos"):
        partes.append(f"dias secos consecutivos: {v['dias_secos_consecutivos']}")
    if v.get("balanco_hidrico_14d") is not None:
        partes.append(f"balanço hídrico 14 dias: {v['balanco_hidrico_14d']:.0f} mm")
    if v.get("tmin_min") is not None:
        partes.append(f"mínima prevista: {v['tmin_min']:.1f} °C")
    if v.get("tmax_max") is not None:
        partes.append(f"máxima prevista: {v['tmax_max']:.1f} °C")
    if v.get("rajada_max"):
        partes.append(f"rajada máxima: {v['rajada_max']:.0f} km/h")
    if v.get("prob_granizo"):
        partes.append(f"índice de granizo: {v['prob_granizo']:.0f}/100")
    return "; ".join(partes)
