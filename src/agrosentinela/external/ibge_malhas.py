"""
IBGE — malhas territoriais, localidades e centroides municipais.

Base geométrica de todos os mapas. O centroide do município é o ponto usado
na consulta climática **quando não há gleba**; havendo gleba (WKT do Sicor),
o centroide do polígono da lavoura tem prioridade — diferença de precisão
que, em municípios como Ribas do Rio Pardo ou Altamira, chega a 80 km.

API pública de serviços de dados do IBGE, sem chave.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .base import ConectorExterno

URL_MUNICIPIOS = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
URL_MALHA = "https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{cd}"


class IbgeMalhas(ConectorExterno):
    chave = "ibge_malhas"
    nome = "IBGE — localidades e malhas municipais"
    ttl_min = 60 * 24 * 180

    def _buscar(self, *, uf: str | None = None, **_: Any) -> pd.DataFrame:
        url = URL_MUNICIPIOS
        if uf:
            url = (f"https://servicodados.ibge.gov.br/api/v1/localidades/"
                   f"estados/{uf}/municipios")
        dados = self._get_json(url)
        if not dados:
            return pd.DataFrame()
        linhas = []
        for m in dados:
            micro = m.get("microrregiao") or {}
            meso = micro.get("mesorregiao") or {}
            estado = meso.get("UF") or {}
            regiao = (estado.get("regiao") or {})
            linhas.append({
                "cd_ibge": int(m["id"]),
                "municipio": m.get("nome", ""),
                "uf": estado.get("sigla", ""),
                "regiao": regiao.get("nome", ""),
                "microrregiao": micro.get("nome", ""),
                "mesorregiao": meso.get("nome", ""),
            })
        return pd.DataFrame(linhas)

    def _offline(self, **_: Any) -> pd.DataFrame:
        # A referência local completa é o seed de municípios do projeto, que
        # já traz código IBGE, nome, UF, região e centroide.
        try:
            from ..data.municipios_seed import municipios_dataframe
            return municipios_dataframe()
        except Exception:  # noqa: BLE001
            return pd.DataFrame(columns=["cd_ibge", "municipio", "uf", "regiao"])

    def _params_sonda(self) -> dict[str, Any]:
        return {"uf": "MT"}


def centroide_de_wkt(wkt: str) -> tuple[float, float] | None:
    """
    Centroide aproximado de um POLYGON/MULTIPOLYGON em WKT, sem depender de
    shapely — média dos vértices do anel externo.

    O Sicor publica as glebas em WKT; calcular o centroide sem biblioteca
    geoespacial mantém o ``requirements.txt`` leve o suficiente para o plano
    gratuito do Streamlit Cloud, que é uma restrição declarada do projeto.
    """
    if not wkt or not isinstance(wkt, str):
        return None
    inicio = wkt.find("((")
    if inicio < 0:
        return None
    corpo = wkt[inicio + 2:]
    fim = corpo.find("))")
    if fim < 0:
        fim = corpo.find(")")
    corpo = corpo[:fim] if fim > 0 else corpo
    corpo = corpo.split("),")[0].replace("(", " ").replace(")", " ")

    xs: list[float] = []
    ys: list[float] = []
    for par in corpo.split(","):
        partes = par.strip().split()
        if len(partes) < 2:
            continue
        try:
            xs.append(float(partes[0]))
            ys.append(float(partes[1]))
        except ValueError:
            continue
    if not xs or not ys:
        return None
    lon = sum(xs) / len(xs)
    lat = sum(ys) / len(ys)
    # Sanidade: território brasileiro.
    if not (-74.5 <= lon <= -34.0 and -34.0 <= lat <= 5.5):
        return None
    return round(lat, 6), round(lon, 6)


def area_aproximada_ha(wkt: str) -> float:
    """
    Área aproximada do polígono em hectares (fórmula do laço, com correção
    de latitude). Serve para conferir a área declarada no Sicor — divergência
    grande entre a gleba desenhada e a área financiada é sinal de dado a
    revisar antes de usar em alerta.
    """
    import math

    inicio = wkt.find("((") if isinstance(wkt, str) else -1
    if inicio < 0:
        return 0.0
    corpo = wkt[inicio + 2:].split("))")[0].split("),")[0]
    corpo = corpo.replace("(", " ").replace(")", " ")
    pontos: list[tuple[float, float]] = []
    for par in corpo.split(","):
        partes = par.strip().split()
        if len(partes) < 2:
            continue
        try:
            pontos.append((float(partes[0]), float(partes[1])))
        except ValueError:
            continue
    if len(pontos) < 3:
        return 0.0
    lat_media = sum(p[1] for p in pontos) / len(pontos)
    km_por_grau_lat = 110.574
    km_por_grau_lon = 111.320 * math.cos(math.radians(lat_media))
    soma = 0.0
    for i in range(len(pontos)):
        x1, y1 = pontos[i]
        x2, y2 = pontos[(i + 1) % len(pontos)]
        soma += (x1 * km_por_grau_lon) * (y2 * km_por_grau_lat) \
              - (x2 * km_por_grau_lon) * (y1 * km_por_grau_lat)
    area_km2 = abs(soma) / 2.0
    return round(area_km2 * 100.0, 2)
