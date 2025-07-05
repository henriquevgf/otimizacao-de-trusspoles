import pandas as pd


def calcular_peso_total(resultados: dict, df_perfis: pd.DataFrame) -> float | None:
    """
    Calcula o peso total da estrutura com base nos perfis escolhidos e nos comprimentos
    do pior caso de cada barra.

    Args:
        resultados (dict): Dicionário com os resultados do dimensionamento por barra.
        df_perfis (pd.DataFrame): DataFrame com os perfis e seus respectivos pesos (coluna "Peso(kg/m)").

    Returns:
        float | None: Peso total da estrutura em kg, ou None se houver barra com dados inválidos.
    """

    # === Inicializa acumulador de peso ===
    peso_total = 0.0

    # === Percorre cada barra nos resultados ===
    for dados_barra in resultados.values():
        nome_hipotese = dados_barra.get("pior_caso")
        dados_piores = dados_barra.get(nome_hipotese, {})
        perfil = dados_piores.get("perfil_escolhido", "").strip()

        if not perfil or perfil == "NENHUM":
            return None

        linha_perfil = df_perfis[df_perfis["Perfil"].str.strip() == perfil]
        if linha_perfil.empty:
            return None

        comprimento_cm = dados_piores.get("comprimento")
        if comprimento_cm is None:
            return None

        peso_por_metro = linha_perfil["Peso(kg/m)"].values[0]
        comprimento_m = comprimento_cm / 100

        # === Acumula peso total ===
        peso_total += peso_por_metro * comprimento_m

    return peso_total


def calcular_peso_por_modulo(
    resultados: dict,
    df_perfis,
    estruturas_por_hipotese: dict,
) -> tuple[dict[int, float], dict[int, float], dict[int, float]]:
    """
    Calcula o peso das barras por módulo da torre, distinguindo montantes e barras inclinadas.

    A função percorre todas as barras do dicionário de resultados, identifica o perfil e o tipo de cada barra,
    e acumula seu peso conforme o módulo estrutural ao qual pertence. Também trata sub-barras virtuais,
    quando presentes, usando os metadados da estrutura final.

    Args:
        resultados (dict): Resultados do dimensionamento, organizados por ID de barra.
        df_perfis: DataFrame contendo os dados dos perfis, incluindo a coluna "Peso(kg/m)".
        estruturas_por_hipotese (dict): Dicionário com as estruturas geradas para cada hipótese de carregamento.

    Returns:
        tuple: Três dicionários contendo:
            - peso_total_por_modulo: peso total de todas as barras por módulo.
            - peso_montantes_por_modulo: peso apenas dos montantes por módulo.
            - peso_diagonais_e_horizontais_por_modulo: peso de diagonais e horizontais por módulo.
    """
    # === Recupera estrutura final e sub-barras ===
    estrutura_final = next(iter(estruturas_por_hipotese.values()))
    sub_barras = getattr(estrutura_final, "sub_barras", {})

    # === Inicializa dicionários de saída ===
    peso_total_por_modulo = {}
    peso_montantes_por_modulo = {}
    peso_diagonais_e_horizontais_por_modulo = {}

    # === Percorre os resultados por barra ===
    for id_barra, dados_barra in resultados.items():
        dados_piores = dados_barra.get(dados_barra.get("pior_caso"))
        if not dados_piores:
            continue

        perfil = dados_piores.get("perfil_escolhido", "").strip()
        if perfil == "NENHUM":
            continue

        linha_perfil = df_perfis[df_perfis["Perfil"].str.strip() == perfil]
        if linha_perfil.empty:
            continue

        peso_linear = linha_perfil["Peso(kg/m)"].values[0]

        # === Determina metadados da barra ===
        if isinstance(id_barra, str) and id_barra in sub_barras:
            metadados = sub_barras[id_barra]
            comprimento_m = metadados["comprimento"] / 100
            tipo = metadados["tipo"]
            modulo = metadados["modulo"]
        else:
            metadados = estrutura_final.metadados_barras.get(id_barra, {})
            comprimento_m = metadados.get("comprimento", 0) / 100
            tipo = metadados.get("tipo", "")
            no1 = metadados.get("no1")
            no2 = metadados.get("no2")

            mods_no1 = estrutura_final.metadados_nos.get(no1, {}).get("modulo", [])
            mods_no2 = estrutura_final.metadados_nos.get(no2, {}).get("modulo", [])
            modulos_comuns = set(mods_no1).intersection(mods_no2)

            if not modulos_comuns:
                continue
            modulo = list(modulos_comuns)[0]

        # === Acumula pesos por módulo ===
        peso = peso_linear * comprimento_m
        peso_total_por_modulo[modulo] = peso_total_por_modulo.get(modulo, 0) + peso

        if tipo.startswith("montante"):
            peso_montantes_por_modulo[modulo] = peso_montantes_por_modulo.get(modulo, 0) + peso
        else:
            peso_diagonais_e_horizontais_por_modulo[modulo] = (
                peso_diagonais_e_horizontais_por_modulo.get(modulo, 0) + peso
            )

    return peso_total_por_modulo, peso_montantes_por_modulo, peso_diagonais_e_horizontais_por_modulo
