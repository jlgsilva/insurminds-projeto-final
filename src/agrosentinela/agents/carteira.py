"""
CarteiraAgent — prepara o universo monitorado.

Responsabilidade única: transformar a carteira de crédito rural (microdados
do Sicor) no conjunto de **operações efetivamente sujeitas a alerta**, já
enriquecido com tudo que as regras precisam:

* fase fenológica e sensibilidade da cultura na data de referência,
  derivadas das datas de plantio e colheita **da própria operação**
  (``DT_INIC_PLANTIO`` / ``DT_INIC_COLHEITA`` do Sicor);
* dias até a colheita e até o vencimento;
* exposição financeira agregada do município;
* histórico de acionamento do Proagro por município × evento;
* persona de comunicação.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from ..data.loader import carregar_base, indices_sinistralidade
from ..personas import inferir_persona_do_mutuario
from ..rules.catalogo import get_cultura
from ..utils.formato import inteiro, reais_compacto
from .base import Agente, Contexto

# Fase atribuída a operações sem ciclo de lavoura declarado (ex.: investimento)
FASE_SEM_CICLO = "sem_ciclo"


class CarteiraAgent(Agente):
    nome = "CarteiraAgent"
    papel = "Preparação do universo monitorado"
    descricao = (
        "Carrega a carteira de crédito rural do Sicor, filtra as operações "
        "vigentes, calcula a fase fenológica de cada lavoura na data de "
        "referência e anexa exposição financeira e histórico do Proagro."
    )

    def _executar(self, ctx: Contexto) -> str:
        if ctx.base is None:
            ctx.base = carregar_base()
            if ctx.base.e_demonstracao:
                ctx.avisar(ctx.base.aviso_procedencia)

        carteira = ctx.base.carteira.copy()
        if carteira.empty:
            ctx.carteira = carteira
            return "Carteira vazia — nada a monitorar."

        carteira = self._aplicar_filtros(carteira, ctx.filtros)
        carteira = self._calcular_ciclo(carteira, ctx.data_ref)
        carteira = self._garantir_persona(carteira)
        carteira = self._exposicao_municipio(carteira)
        carteira = self._anexar_historico(carteira, ctx.base.proagro_sinistros)
        carteira = self._anexar_contexto_externo(
            carteira, getattr(ctx.base, "contexto_externo", None))

        ctx.carteira = carteira.reset_index(drop=True)
        n_geo = int(ctx.carteira["lat"].notna().sum())
        return (
            f"{inteiro(len(ctx.carteira))} operações monitoradas em "
            f"{ctx.carteira['cd_ibge'].nunique()} municípios "
            f"({inteiro(n_geo)} com coordenada); "
            f"{reais_compacto(ctx.carteira['valor_credito'].sum())} em exposição."
        )

    def metricas(self, ctx: Contexto) -> dict[str, Any]:
        if ctx.carteira.empty:
            return {}
        c = ctx.carteira
        return {
            "operacoes": int(len(c)),
            "municipios": int(c["cd_ibge"].nunique()),
            "valor_total": float(c["valor_credito"].sum()),
            "em_ciclo": int((c["fase"] != FASE_SEM_CICLO).sum()),
            "sem_cobertura": int((~c["tem_cobertura"]).sum()),
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _aplicar_filtros(df: pd.DataFrame, filtros: dict[str, Any]) -> pd.DataFrame:
        out = df
        for coluna, valor in (filtros or {}).items():
            if coluna not in out.columns or valor in (None, "", [], "Todos"):
                continue
            if isinstance(valor, (list, tuple, set)):
                if len(valor) == 0:
                    continue
                out = out[out[coluna].isin(list(valor))]
            elif coluna == "valor_minimo":
                out = out[out["valor_credito"] >= float(valor)]
            else:
                out = out[out[coluna] == valor]
        return out

    # ------------------------------------------------------------------
    @staticmethod
    def _calcular_ciclo(df: pd.DataFrame, data_ref: date) -> pd.DataFrame:
        """
        Deriva a fase fenológica de cada operação.

        O progresso do ciclo é a fração decorrida entre o início do plantio
        e o início da colheita **declarados na operação**. Quando essas datas
        não existem (típico de operações de investimento), a operação entra
        como ``sem_ciclo``: continua na carteira para as regras financeiras,
        mas não recebe alerta agronômico de fase.
        """
        out = df.copy()
        hoje = pd.Timestamp(data_ref)

        for col in ("dt_inic_plantio", "dt_inic_colheita", "dt_fim_colheita", "dt_vencimento"):
            if col in out.columns:
                out[col] = pd.to_datetime(out[col], errors="coerce")

        ini = out["dt_inic_plantio"]
        fim = out["dt_inic_colheita"]
        duracao = (fim - ini).dt.days
        valida = ini.notna() & fim.notna() & (duracao > 0)

        progresso = pd.Series(np.nan, index=out.index, dtype="float64")
        progresso[valida] = ((hoje - ini[valida]).dt.days / duracao[valida]).astype(float)
        out["progresso_ciclo"] = progresso.clip(lower=-1.0, upper=2.0)

        # Fase e sensibilidade por cultura
        fases: list[str] = []
        nomes_fase: list[str] = []
        recomendacoes: list[str] = []
        sens: list[dict[str, float]] = []
        for cultura, p in zip(out["cultura"].astype(str), out["progresso_ciclo"]):
            info = get_cultura(cultura)
            if pd.isna(p) or p < 0 or p > 1.15:
                fases.append(FASE_SEM_CICLO)
                nomes_fase.append("Fora do ciclo de lavoura")
                recomendacoes.append("")
                sens.append({})
                continue
            fase = info.fase_em(min(float(p), 1.0))
            fases.append(fase.codigo)
            nomes_fase.append(fase.nome)
            recomendacoes.append(fase.recomendacao)
            sens.append(fase.sensibilidade)

        out["fase"] = fases
        out["fase_nome"] = nomes_fase
        out["recomendacao_fase"] = recomendacoes
        out["_sensibilidade"] = sens

        out["dias_para_colheita"] = (out["dt_inic_colheita"] - hoje).dt.days
        out["dias_para_vencimento"] = (out["dt_vencimento"] - hoje).dt.days
        out["dias_desde_plantio"] = (hoje - out["dt_inic_plantio"]).dt.days
        out["cultura_grupo"] = out["cultura"].map(lambda c: get_cultura(c).grupo)
        out["em_ciclo"] = out["fase"] != FASE_SEM_CICLO
        return out

    # ------------------------------------------------------------------
    @staticmethod
    def _garantir_persona(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        if "persona" not in out.columns:
            out["persona"] = pd.NA
        faltando = out["persona"].isna() | (out["persona"].astype(str).str.strip() == "")
        if bool(faltando.any()):
            out.loc[faltando, "persona"] = [
                inferir_persona_do_mutuario(
                    programa_descricao=r.get("programa"),
                    categoria_emitente=r.get("categoria_emitente"),
                    valor_credito=r.get("valor_credito"),
                    area_financiada=r.get("area_ha"),
                )
                for _, r in out.loc[faltando].iterrows()
            ]
        return out

    # ------------------------------------------------------------------
    @staticmethod
    def _exposicao_municipio(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        agg = out.groupby("cd_ibge")["valor_credito"].transform("sum")
        out["exposicao_municipio"] = agg.astype(float)
        out["operacoes_municipio"] = out.groupby("cd_ibge")["ref_bacen"].transform("count")
        out["area_municipio"] = out.groupby("cd_ibge")["area_ha"].transform("sum")
        # Fração da área financiada do município que tem alguma cobertura de
        # risco (Proagro ou seguro). Combinada com a penetração do seguro
        # privado (PSR/MAPA), é o que distingue um município **descoberto**
        # de um município **coberto por outro instrumento** — distinção que a
        # leitura isolada do Sicor não permite fazer.
        if "tem_cobertura" in out.columns:
            coberta = out["area_ha"].where(out["tem_cobertura"].astype(bool), 0.0)
            soma_coberta = coberta.groupby(out["cd_ibge"]).transform("sum")
            out["cobertura_municipio"] = (
                soma_coberta / out["area_municipio"].replace(0, np.nan)
            ).fillna(0.0).astype(float)
        else:
            out["cobertura_municipio"] = 0.0
        return out

    # ------------------------------------------------------------------
    @staticmethod
    def _anexar_contexto_externo(df: pd.DataFrame,
                                 contexto: pd.DataFrame) -> pd.DataFrame:
        """
        Traz para cada operação as colunas do conjunto ``contexto_externo``.

        Opcional por construção: sem o conjunto, as colunas ficam vazias e o
        enriquecimento simplesmente não acontece — nenhum alerta deixa de ser
        emitido por causa disso. É o que permite rodar a solução completa sem
        nunca ter tocado em uma fonte externa.
        """
        colunas = ("chuva_normal_mm_mes", "temp_normal_c", "penetracao_seguro_privado",
                   "rendimento_ref_kg_ha", "bioma", "perfil_uso", "classe_seca",
                   "severidade_seca", "focos_calor_24h")
        out = df.copy()
        if contexto is None or contexto.empty or "cd_ibge" not in contexto.columns:
            for c in colunas:
                if c not in out.columns:
                    out[c] = np.nan if c not in ("bioma", "perfil_uso", "classe_seca") else ""
            return out
        disponiveis = [c for c in colunas if c in contexto.columns]
        ref = contexto[["cd_ibge", *disponiveis]].drop_duplicates(subset=["cd_ibge"])
        out = out.merge(ref, on="cd_ibge", how="left", suffixes=("", "_ctx"))
        for c in colunas:
            if c not in out.columns:
                out[c] = np.nan if c not in ("bioma", "perfil_uso", "classe_seca") else ""
        return out

    # ------------------------------------------------------------------
    @staticmethod
    def _anexar_historico(df: pd.DataFrame, sinistros: pd.DataFrame) -> pd.DataFrame:
        """
        Anexa, por município, o dicionário ``evento -> frequência histórica``
        e a taxa geral de acionamento do Proagro.
        """
        out = df.copy()
        vazio = [{} for _ in range(len(out))]
        if sinistros is None or sinistros.empty:
            out["hist_eventos"] = vazio
            out["hist_perda_evento"] = [{} for _ in range(len(out))]
            out["hist_deferimento_evento"] = [{} for _ in range(len(out))]
            out["taxa_acionamento_municipio"] = 0.0
            out["prazo_pagamento_municipio"] = 0.0
            out["motivo_negativa_municipio"] = ""
            return out

        idx = indices_sinistralidade(sinistros)
        mapa: dict[int, dict[str, float]] = {}
        for cd, grupo in idx.groupby("cd_ibge"):
            mapa[int(cd)] = dict(zip(grupo["evento"], grupo["freq_evento"].astype(float)))

        taxa = (
            idx.groupby("cd_ibge")
            .apply(
                lambda g: float(g["n_cop"].sum()) / max(float(g["n_operacoes"].sum()), 1.0),
                include_groups=False,
            )
            .to_dict()
        )

        out["hist_eventos"] = out["cd_ibge"].map(lambda c: mapa.get(int(c), {}))
        out["taxa_acionamento_municipio"] = (
            out["cd_ibge"].map(lambda c: taxa.get(int(c), 0.0)).astype(float)
        )

        # A cadeia completa do Proagro (COP -> RCP -> súmula -> parcelas) traz
        # três números que mudam a conversa com o produtor: quanto costuma se
        # perder quando o evento ocorre, qual a chance de o pedido ser
        # deferido e quanto tempo o pagamento costuma levar. Nenhum deles é
        # previsão — todos são histórico observado naquele município.
        perdas: dict[int, dict[str, float]] = {}
        deferimentos: dict[int, dict[str, float]] = {}
        prazos: dict[int, float] = {}
        motivos: dict[int, str] = {}

        if "perda_media_pct" in sinistros.columns:
            for cd, grupo in sinistros.groupby("cd_ibge"):
                cd = int(cd)
                perdas[cd] = {
                    str(e): float(v)
                    for e, v in zip(grupo["evento"], grupo["perda_media_pct"])
                    if pd.notna(v) and float(v) > 0
                }
        if "taxa_deferimento" in sinistros.columns:
            for cd, grupo in sinistros.groupby("cd_ibge"):
                cd = int(cd)
                deferimentos[cd] = {
                    str(e): float(v)
                    for e, v in zip(grupo["evento"], grupo["taxa_deferimento"])
                    if pd.notna(v) and float(v) > 0
                }
        if "prazo_medio_pagamento_dias" in sinistros.columns:
            prazos = (sinistros.groupby("cd_ibge")["prazo_medio_pagamento_dias"]
                               .mean().dropna().astype(float).to_dict())
        if "motivo_negativa_frequente" in sinistros.columns:
            for cd, grupo in sinistros.groupby("cd_ibge"):
                serie = grupo["motivo_negativa_frequente"].dropna()
                if not serie.empty:
                    motivos[int(cd)] = str(serie.mode().iloc[0])

        out["hist_perda_evento"] = out["cd_ibge"].map(lambda c: perdas.get(int(c), {}))
        out["hist_deferimento_evento"] = out["cd_ibge"].map(
            lambda c: deferimentos.get(int(c), {}))
        out["prazo_pagamento_municipio"] = out["cd_ibge"].map(
            lambda c: float(prazos.get(int(c), 0.0))).astype(float)
        out["motivo_negativa_municipio"] = out["cd_ibge"].map(
            lambda c: motivos.get(int(c), ""))
        return out
