"""
Base de referência de municípios — **semente de demonstração**.

Para que o aplicativo funcione imediatamente (inclusive no Streamlit Cloud,
antes de qualquer execução do ETL), o projeto embarca uma amostra de
municípios com forte presença de crédito rural, contendo código IBGE, nome,
UF, mesorregião agrícola e **coordenadas aproximadas do centro urbano**
(precisão de duas casas decimais, suficiente para a grade meteorológica de
~11 km da Open-Meteo).

⚠️  Esta é uma **amostra de demonstração**. A base oficial e completa dos
5.570 municípios é construída pelo ETL a partir de:

* ``MunicipiosSicor.csv`` — tabela de domínio do Banco Central (código IBGE,
  nome e UF de todos os municípios usados no Sicor);
* ``AliquotaBaseProagro.csv`` — alíquotas do Proagro por município;
* centroides oficiais do IBGE (malha municipal).

Consulte ``etl/04_build_municipios.py``.
"""

from __future__ import annotations

import pandas as pd

# (cd_ibge, municipio, uf, regiao, lat, lon, polo_agricola)
_MUNICIPIOS: tuple[tuple[int, str, str, str, float, float, str], ...] = (
    # ---------------------------------------------------------- Centro-Oeste
    (5107925, "Sorriso", "MT", "Centro-Oeste", -12.55, -55.72, "Soja e milho"),
    (5107909, "Sinop", "MT", "Centro-Oeste", -11.86, -55.51, "Soja e milho"),
    (5105259, "Lucas do Rio Verde", "MT", "Centro-Oeste", -13.05, -55.91, "Soja e milho"),
    (5106232, "Nova Mutum", "MT", "Centro-Oeste", -13.83, -56.08, "Soja e algodão"),
    (5106752, "Primavera do Leste", "MT", "Centro-Oeste", -15.56, -54.30, "Soja e algodão"),
    (5103007, "Campo Verde", "MT", "Centro-Oeste", -15.55, -55.17, "Algodão e soja"),
    (5107602, "Rondonópolis", "MT", "Centro-Oeste", -16.47, -54.64, "Soja e pecuária"),
    (5107875, "Sapezal", "MT", "Centro-Oeste", -13.54, -58.81, "Algodão"),
    (5102686, "Campo Novo do Parecis", "MT", "Centro-Oeste", -13.67, -57.89, "Algodão e soja"),
    (5107156, "Querência", "MT", "Centro-Oeste", -12.61, -52.21, "Soja"),
    (5103403, "Cuiabá", "MT", "Centro-Oeste", -15.60, -56.10, "Pecuária"),
    (5103502, "Diamantino", "MT", "Centro-Oeste", -14.41, -56.45, "Soja"),
    (5108006, "Tangará da Serra", "MT", "Centro-Oeste", -14.62, -57.49, "Cana e soja"),
    (5218805, "Rio Verde", "GO", "Centro-Oeste", -17.79, -50.93, "Soja, milho e suínos"),
    (5219753, "Jataí", "GO", "Centro-Oeste", -17.88, -51.72, "Soja e milho"),
    (5205109, "Cristalina", "GO", "Centro-Oeste", -16.77, -47.61, "Grãos irrigados"),
    (5213103, "Mineiros", "GO", "Centro-Oeste", -17.57, -52.55, "Soja e milho"),
    (5208707, "Goiânia", "GO", "Centro-Oeste", -16.69, -49.26, "Diversificado"),
    (5204508, "Catalão", "GO", "Centro-Oeste", -18.17, -47.94, "Soja e milho"),
    (5221403, "Silvânia", "GO", "Centro-Oeste", -16.66, -48.61, "Grãos"),
    (5003702, "Dourados", "MS", "Centro-Oeste", -22.22, -54.81, "Soja e milho"),
    (5002704, "Campo Grande", "MS", "Centro-Oeste", -20.44, -54.65, "Pecuária"),
    (5008305, "São Gabriel do Oeste", "MS", "Centro-Oeste", -19.40, -54.57, "Soja e suínos"),
    (5006606, "Maracaju", "MS", "Centro-Oeste", -21.61, -55.17, "Soja e milho"),
    (5007109, "Naviraí", "MS", "Centro-Oeste", -23.06, -54.19, "Cana e soja"),
    (5300108, "Brasília", "DF", "Centro-Oeste", -15.78, -47.93, "Grãos irrigados"),

    # ----------------------------------------------------------------- Sul
    (4314100, "Passo Fundo", "RS", "Sul", -28.26, -52.41, "Soja e trigo"),
    (4306106, "Cruz Alta", "RS", "Sul", -28.64, -53.61, "Soja e trigo"),
    (4310108, "Ijuí", "RS", "Sul", -28.39, -53.91, "Soja e trigo"),
    (4316907, "Santa Maria", "RS", "Sul", -29.68, -53.81, "Arroz e soja"),
    (4322509, "Vacaria", "RS", "Sul", -28.51, -50.94, "Maçã e grãos"),
    (4305108, "Caxias do Sul", "RS", "Sul", -29.17, -51.18, "Uva e fruticultura"),
    (4302105, "Bento Gonçalves", "RS", "Sul", -29.17, -51.52, "Uva e vinho"),
    (4314902, "Pelotas", "RS", "Sul", -31.77, -52.34, "Arroz e fruticultura"),
    (4318705, "Santo Ângelo", "RS", "Sul", -28.30, -54.26, "Soja"),
    (4307609, "Erechim", "RS", "Sul", -27.63, -52.27, "Grãos e aves"),
    (4104808, "Cascavel", "PR", "Sul", -24.96, -53.46, "Soja e milho"),
    (4113700, "Londrina", "PR", "Sul", -23.31, -51.16, "Soja e café"),
    (4115200, "Maringá", "PR", "Sul", -23.43, -51.94, "Soja e milho"),
    (4119905, "Ponta Grossa", "PR", "Sul", -25.09, -50.16, "Soja e trigo"),
    (4127700, "Toledo", "PR", "Sul", -24.72, -53.74, "Grãos e aves"),
    (4108304, "Guarapuava", "PR", "Sul", -25.39, -51.46, "Grãos e batata"),
    (4106902, "Curitiba", "PR", "Sul", -25.43, -49.27, "Olerícolas"),
    (4118204, "Pato Branco", "PR", "Sul", -26.23, -52.67, "Grãos e aves"),
    (4204202, "Chapecó", "SC", "Sul", -27.10, -52.62, "Suínos e aves"),
    (4209300, "Lages", "SC", "Sul", -27.82, -50.33, "Pecuária e grãos"),
    (4211900, "Rio do Sul", "SC", "Sul", -27.21, -49.64, "Arroz e leite"),
    (4202404, "Araranguá", "SC", "Sul", -28.94, -49.49, "Arroz"),
    (4218707, "Tubarão", "SC", "Sul", -28.47, -49.01, "Arroz"),
    (4216602, "São Joaquim", "SC", "Sul", -28.29, -49.93, "Maçã"),

    # -------------------------------------------------------------- Sudeste
    (3170206, "Uberaba", "MG", "Sudeste", -19.75, -47.93, "Cana e grãos"),
    (3170107, "Uberlândia", "MG", "Sudeste", -18.92, -48.28, "Grãos e café"),
    (3148004, "Patos de Minas", "MG", "Sudeste", -18.58, -46.52, "Café e grãos"),
    (3148103, "Patrocínio", "MG", "Sudeste", -18.94, -46.99, "Café"),
    (3143906, "Monte Carmelo", "MG", "Sudeste", -18.73, -47.50, "Café"),
    (3136702, "Juiz de Fora", "MG", "Sudeste", -21.76, -43.35, "Leite"),
    (3170701, "Unaí", "MG", "Sudeste", -16.36, -46.91, "Grãos irrigados"),
    (3125903, "Guaxupé", "MG", "Sudeste", -21.31, -46.71, "Café"),
    (3169901, "Três Pontas", "MG", "Sudeste", -21.37, -45.51, "Café"),
    (3106200, "Belo Horizonte", "MG", "Sudeste", -19.92, -43.94, "Diversificado"),
    (3516200, "Franca", "SP", "Sudeste", -20.54, -47.40, "Café e cana"),
    (3543402, "Ribeirão Preto", "SP", "Sudeste", -21.18, -47.81, "Cana"),
    (3538709, "Piracicaba", "SP", "Sudeste", -22.73, -47.65, "Cana"),
    (3505708, "Barretos", "SP", "Sudeste", -20.56, -48.57, "Cana e pecuária"),
    (3549805, "São José do Rio Preto", "SP", "Sudeste", -20.82, -49.38, "Citros e cana"),
    (3501608, "Americana", "SP", "Sudeste", -22.74, -47.33, "Diversificado"),
    (3524402, "Itapetininga", "SP", "Sudeste", -23.59, -48.05, "Grãos e cana"),
    (3529401, "Marília", "SP", "Sudeste", -22.21, -49.95, "Grãos e citros"),
    (3552205, "Sorocaba", "SP", "Sudeste", -23.50, -47.46, "Olerícolas"),
    (3205309, "Vitória", "ES", "Sudeste", -20.32, -40.34, "Café conilon"),
    (3201308, "Colatina", "ES", "Sudeste", -19.54, -40.63, "Café conilon"),
    (3302205, "Campos dos Goytacazes", "RJ", "Sudeste", -21.75, -41.33, "Cana"),

    # ------------------------------------------------------------- Nordeste
    (2903201, "Barreiras", "BA", "Nordeste", -12.15, -44.99, "Soja e algodão"),
    (2919553, "Luís Eduardo Magalhães", "BA", "Nordeste", -12.09, -45.80, "Soja e algodão"),
    (2909307, "Formosa do Rio Preto", "BA", "Nordeste", -11.05, -45.19, "Soja e algodão"),
    (2933307, "Vitória da Conquista", "BA", "Nordeste", -14.87, -40.84, "Café e pecuária"),
    (2910800, "Irecê", "BA", "Nordeste", -11.30, -41.86, "Feijão e mandioca"),
    (2927408, "Salvador", "BA", "Nordeste", -12.97, -38.50, "Diversificado"),
    (2905701, "Bom Jesus da Lapa", "BA", "Nordeste", -13.26, -43.42, "Fruticultura irrigada"),
    (2101400, "Balsas", "MA", "Nordeste", -7.53, -46.04, "Soja"),
    (2111300, "São Luís", "MA", "Nordeste", -2.53, -44.30, "Diversificado"),
    (2211001, "Uruçuí", "PI", "Nordeste", -7.23, -44.56, "Soja"),
    (2205706, "Bom Jesus", "PI", "Nordeste", -9.07, -44.36, "Soja"),
    (2611606, "Petrolina", "PE", "Nordeste", -9.39, -40.50, "Fruticultura irrigada"),
    (2903904, "Juazeiro", "BA", "Nordeste", -9.42, -40.50, "Fruticultura irrigada"),
    (2304400, "Fortaleza", "CE", "Nordeste", -3.73, -38.53, "Diversificado"),
    (2408102, "Mossoró", "RN", "Nordeste", -5.19, -37.34, "Fruticultura irrigada"),
    (2800308, "Aracaju", "SE", "Nordeste", -10.91, -37.07, "Diversificado"),
    (2507507, "João Pessoa", "PB", "Nordeste", -7.12, -34.86, "Cana"),
    (2704302, "Maceió", "AL", "Nordeste", -9.67, -35.74, "Cana"),

    # ---------------------------------------------------------------- Norte
    (1721000, "Palmas", "TO", "Norte", -10.18, -48.33, "Soja e pecuária"),
    (1709500, "Gurupi", "TO", "Norte", -11.73, -49.07, "Soja e arroz"),
    (1702109, "Araguaína", "TO", "Norte", -7.19, -48.21, "Pecuária"),
    (1100205, "Porto Velho", "RO", "Norte", -8.76, -63.90, "Pecuária e soja"),
    (1100304, "Vilhena", "RO", "Norte", -12.74, -60.15, "Soja e milho"),
    (1100122, "Cacoal", "RO", "Norte", -11.44, -61.45, "Café e leite"),
    (1500602, "Santarém", "PA", "Norte", -2.44, -54.71, "Soja"),
    (1506807, "Paragominas", "PA", "Norte", -2.99, -47.35, "Grãos e pecuária"),
    (1502400, "Castanhal", "PA", "Norte", -1.30, -47.92, "Dendê e fruticultura"),
    (1302603, "Manaus", "AM", "Norte", -3.12, -60.02, "Diversificado"),
    (1400100, "Boa Vista", "RR", "Norte", 2.82, -60.67, "Arroz e soja"),
    (1600303, "Macapá", "AP", "Norte", 0.03, -51.07, "Diversificado"),
    (1200401, "Rio Branco", "AC", "Norte", -9.97, -67.81, "Pecuária"),
)

COLUNAS = ("cd_ibge", "municipio", "uf", "regiao", "lat", "lon", "polo_agricola")

# Regiões por UF — usado quando o ETL traz municípios sem a coluna região.
UF_REGIAO: dict[str, str] = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte", "RO": "Norte",
    "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste",
    "PB": "Nordeste", "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste",
    "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste",
    "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
}

# Bounding box aproximado de cada UF — usado para validar coordenadas
# (lat_min, lat_max, lon_min, lon_max).
UF_BBOX: dict[str, tuple[float, float, float, float]] = {
    "AC": (-11.2, -7.1, -74.0, -66.6), "AL": (-10.5, -8.8, -38.3, -35.1),
    "AM": (-9.9, 2.3, -73.9, -56.0), "AP": (-1.3, 4.5, -54.9, -49.8),
    "BA": (-18.4, -8.5, -46.7, -37.3), "CE": (-7.9, -2.7, -41.5, -37.2),
    "DF": (-16.1, -15.5, -48.3, -47.3), "ES": (-21.4, -17.8, -41.9, -39.6),
    "GO": (-19.6, -12.3, -53.3, -45.9), "MA": (-10.3, -1.0, -48.8, -41.7),
    "MG": (-22.9, -14.2, -51.1, -39.8), "MS": (-24.1, -17.1, -58.2, -50.9),
    "MT": (-18.1, -7.3, -61.7, -50.2), "PA": (-9.9, 2.6, -58.9, -46.0),
    "PB": (-8.4, -6.0, -38.8, -34.7), "PE": (-9.5, -7.2, -41.4, -34.8),
    "PI": (-10.9, -2.7, -45.9, -40.3), "PR": (-26.8, -22.4, -54.7, -48.0),
    "RJ": (-23.4, -20.7, -44.9, -40.9), "RN": (-6.9, -4.8, -38.6, -34.9),
    "RO": (-13.7, -7.9, -66.9, -59.7), "RR": (-1.6, 5.3, -64.9, -58.8),
    "RS": (-33.8, -27.0, -57.7, -49.6), "SC": (-29.4, -25.9, -53.9, -48.3),
    "SE": (-11.6, -9.4, -38.3, -36.3), "SP": (-25.4, -19.7, -53.2, -44.1),
    "TO": (-13.5, -5.1, -50.8, -45.6),
}


def municipios_seed() -> pd.DataFrame:
    """DataFrame com a amostra de municípios de demonstração."""
    df = pd.DataFrame(_MUNICIPIOS, columns=list(COLUNAS))
    df["cd_ibge"] = df["cd_ibge"].astype("int64")
    df["cd_uf"] = (df["cd_ibge"] // 100000).astype("int64")
    df["fonte"] = "seed_demonstracao"
    return df


def validar_coordenadas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Verifica se cada coordenada cai dentro do *bounding box* da sua UF.

    Devolve apenas as linhas com problema — usado nos testes e no ETL para
    detectar erro de digitação ou de junção.
    """
    problemas = []
    for _, linha in df.iterrows():
        bbox = UF_BBOX.get(str(linha.get("uf")))
        if not bbox:
            continue
        lat_min, lat_max, lon_min, lon_max = bbox
        lat, lon = float(linha["lat"]), float(linha["lon"])
        if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
            problemas.append(
                {
                    "cd_ibge": linha.get("cd_ibge"),
                    "municipio": linha.get("municipio"),
                    "uf": linha.get("uf"),
                    "lat": lat,
                    "lon": lon,
                    "motivo": "Coordenada fora do limite aproximado da UF",
                }
            )
    return pd.DataFrame(problemas)
