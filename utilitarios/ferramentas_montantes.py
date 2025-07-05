from collections import defaultdict

import pandas as pd

from utilitarios.geral import ordenar_id_barra
from utilitarios.verif_normativas import (
    calcula_tensao_axial_admissivel,
    calcular_esbeltez_corrigida,
)

from utilitarios.io_excel import filtrar_perfis_montante_reforco


def mapear_montantes_por_modulo(
    estrutura: any,
) -> tuple[dict[int, list[int]], dict[int, tuple[int, int, list[int], list[int]]]]:
    """
    Identifica e classifica montantes da estrutura entre:

    - montantes_puros: barras que pertencem totalmente a um único módulo;
    - montantes_cruzando: barras que conectam nós pertencentes a módulos diferentes.

    Args:
        estrutura (any): Objeto SystemElements do anaStruct com metadados de barras e nós preenchidos.

    Returns:
        tuple:
            - dict[int, list[int]]: Dicionário {módulo: lista de IDs de montantes puros}.
            - dict[int, tuple[int, int, list[int], list[int]]]: Dicionário {ID_barra: (nó1, nó2, módulos_nó1, módulos_nó2)}
              para montantes que cruzam módulos.
    """
    montantes_puros = {}
    montantes_cruzando = {}

    for id_barra, metadados_barra in estrutura.metadados_barras.items():
        tipo_barra = metadados_barra.get("tipo")
        if not isinstance(tipo_barra, str) or not tipo_barra.startswith("montante"):
            continue  # Só considera barras do tipo montante

        # Identifica os nós da barra
        no1 = metadados_barra.get("no1")
        no2 = metadados_barra.get("no2")

        modulos_no1 = estrutura.metadados_nos.get(no1, {}).get("modulo", [])
        modulos_no2 = estrutura.metadados_nos.get(no2, {}).get("modulo", [])

        set_mods_no1 = set(modulos_no1)
        set_mods_no2 = set(modulos_no2)

        intersecao = set_mods_no1.intersection(set_mods_no2)

        if intersecao:
            # Se existe interseção entre módulos dos dois nós → montante puro
            for modulo in intersecao:
                montantes_puros.setdefault(modulo, []).append(id_barra)
        else:
            # Sem interseção → montante cruzando módulos
            montantes_cruzando[id_barra] = (no1, no2, list(set_mods_no1), list(set_mods_no2))

    return montantes_puros, montantes_cruzando


def marcar_montantes_em_extremidades(metadados: dict[str, dict]) -> None:
    """
    Marca nos metadados de cada montante se ele é base de módulo, topo de módulo ou topo da estrutura.

    Essa marcação é utilizada para identificar corretamente os pontos de ligação nas extremidades dos módulos.

    Args:
        metadados (dict[str, dict]): Dicionário com os metadados de todas as barras da estrutura.
            Cada entrada deve conter os campos 'tipo', 'modulo', 'y_min' e 'y_max'.

    Modifies:
        Adiciona aos metadados de cada montante as chaves booleanas:
            - 'base_modulo': True se for a barra mais baixa do módulo.
            - 'topo_modulo': True se for a barra mais alta do módulo.
            - 'topo_estrutura': True se estiver no módulo mais alto e for o topo da estrutura.
            Caso contrário, os valores são definidos como False.
    """
    montantes_por_modulo: dict[int, list[tuple[str, dict]]] = {}

    # Agrupa montantes por módulo
    for id_barra, dados in metadados.items():
        if "montante" not in dados.get("tipo", ""):
            continue
        modulo = dados.get("modulo")
        y_min = dados.get("y_min")
        y_max = dados.get("y_max")
        if modulo is None or y_min is None or y_max is None:
            continue
        montantes_por_modulo.setdefault(modulo, []).append((id_barra, dados))

    # Marca base_modulo e topo_modulo
    for modulo, lista in montantes_por_modulo.items():
        if not lista:
            continue
        menor_y = min(b[1]["y_min"] for b in lista)
        maior_y = max(b[1]["y_max"] for b in lista)
        for id_barra, dados in lista:
            dados["base_modulo"] = abs(dados["y_min"] - menor_y) < 1e-3
            dados["topo_modulo"] = abs(dados["y_max"] - maior_y) < 1e-3
            dados["topo_estrutura"] = False  # será ajustado abaixo se aplicável

    # Marca topo_estrutura no módulo mais alto (menor número)
    if montantes_por_modulo:
        modulo_topo = min(montantes_por_modulo.keys())
        lista_topo = montantes_por_modulo[modulo_topo]
        y_topo_estrutura = max(d[1]["y_max"] for d in lista_topo)
        for id_barra, dados in lista_topo:
            dados["topo_estrutura"] = abs(dados["y_max"] - y_topo_estrutura) < 1e-3


def igualar_perfis_montantes_por_modulo(
    resultados: dict,
    df_montantes: pd.DataFrame,
    df_materiais: pd.DataFrame,
    coef_minoracao: float,
    diametros_furos: dict,
    descontos_area_liquida: dict = None,
) -> None:
    """
    Uniformiza os perfis dos montantes dentro de cada módulo da estrutura.

    Para cada módulo:
    - Identifica o maior perfil adotado entre os montantes (pela área bruta).
    - Recalcula todas as hipóteses de dimensionamento usando esse maior perfil.
    - Atualiza os metadados (raio de giração, esbeltez corrigida, área bruta, etc.)

    Args:
        resultados (dict): Resultados de dimensionamento por barra e por hipótese.
        df_montantes (pd.DataFrame): Tabela de perfis disponíveis para montantes.
        df_materiais (pd.DataFrame): Tabela de propriedades dos materiais (Fy, Fu).
        coef_minoracao (float): Coeficiente de minoração de resistência (γ).
        diametros_furos (dict): Diâmetro dos furos para cada tipo de barra.
        descontos_area_liquida (dict, opcional): Sobrescrita do número de furos a considerar para área líquida.

    Returns:
        None
    """
    # === 1. Agrupar montantes por módulo ===
    montantes_por_modulo = {}

    for id_barra, dados_barra in resultados.items():
        if not dados_barra.get("perfil_escolhido"):
            continue

        for nome_hipotese, dados_hipotese in dados_barra.items():
            if not isinstance(dados_hipotese, dict):
                continue
            if "montante" not in dados_hipotese.get("tipo", ""):
                continue

            modulo = dados_hipotese.get("modulo")
            if modulo is not None:
                montantes_por_modulo.setdefault(modulo, []).append(id_barra)
                break  # Achou um tipo válido, não precisa checar outras hipóteses

    # === 2. Para cada grupo de montantes, descobrir o maior perfil adotado ===
    for modulo, lista_barras in montantes_por_modulo.items():
        perfis_usados = {
            id_barra: resultados[id_barra]["perfil_escolhido"] for id_barra in lista_barras
        }

        perfis_areas = []
        for id_barra, nome_perfil in perfis_usados.items():
            linha_perfil = df_montantes[df_montantes["Perfil"].str.strip() == nome_perfil.strip()]
            if not linha_perfil.empty:
                area_bruta = linha_perfil.iloc[0]["A(cm2)"]
                perfis_areas.append((area_bruta, nome_perfil))

        if not perfis_areas:
            continue

        # Seleciona o perfil com maior área bruta
        _, perfil_final = max(perfis_areas, key=lambda x: x[0])

        linha_final = df_montantes[df_montantes["Perfil"].str.strip() == perfil_final.strip()].iloc[
            0
        ]

        # === 3. Recalcular hipóteses de cada montante com o novo perfil ===
        for id_barra in lista_barras:
            for nome_hipotese, dados_hipotese in resultados[id_barra].items():
                if not isinstance(dados_hipotese, dict):
                    continue

                forca_axial = dados_hipotese["forca_axial"]
                tipo_barra = dados_hipotese["tipo"]
                comprimento = dados_hipotese["comprimento_destravado"]

                novos_dados = calcula_tensao_axial_admissivel(
                    df_materiais,
                    linha_final,
                    forca_axial,
                    tipo_barra,
                    comprimento,
                    coef_minoracao,
                    diametro_furo=diametros_furos.get("montante", 1.59),
                    limitar_esbeltez_tracao=(forca_axial > 0),
                    forcar_verificacao_compressao=(forca_axial < 0),
                    descontos_area_liquida=descontos_area_liquida,
                )

                raio_giracao = linha_final["rx(cm)"]
                esbeltez_corrigida = calcular_esbeltez_corrigida(
                    "montante", comprimento, raio_giracao
                )

                resultados[id_barra][nome_hipotese].update(
                    {
                        **novos_dados,
                        "perfil_escolhido": perfil_final,
                        "raio": raio_giracao,
                        "area_bruta": linha_final["A(cm2)"],
                        "comprimento": dados_hipotese["comprimento"],
                        "esbeltez_corrigida": esbeltez_corrigida,
                    }
                )

            resultados[id_barra]["perfil_escolhido"] = perfil_final


def preparar_montantes_para_dimensionamento(estrutura: any) -> dict[str, dict]:
    """
    Combina as barras tipo montante reais (exceto montantes cruzadores) com as sub-barras artificiais tipo montante,
    retornando o conjunto de barras que efetivamente serão dimensionadas.

    Montantes cruzando módulos são substituídos pelas suas sub-barras correspondentes.

    Args:
        estrutura (any): Objeto SystemElements do anaStruct contendo:
            - metadados_barras: dicionário de metadados das barras reais,
            - sub_barras: dicionário de sub-barras criadas para montantes cruzadores.

    Returns:
        dict[str, dict]: Dicionário {ID_barra: metadados} ordenado naturalmente.
    """
    # Obtém o dicionário de sub-barras (pode estar ausente)
    sub_barras = getattr(estrutura, "sub_barras", {})

    # Conjunto de IDs de barras que cruzam módulos (origens das sub-barras)
    ids_cruzando = {dados["origem"] for dados in sub_barras.values()}

    # Filtra barras reais: remove montantes cruzadores
    barras_filtradas = {
        id_barra: metadados
        for id_barra, metadados in estrutura.metadados_barras.items()
        if not (metadados["tipo"].startswith("montante") and id_barra in ids_cruzando)
    }

    # Adiciona as sub-barras no conjunto
    barras_filtradas.update(sub_barras)

    # Ordena naturalmente (01, 02, 03, 06a, 06b, etc.)
    return dict(sorted(barras_filtradas.items(), key=lambda item: ordenar_id_barra(item[0])))


def identificar_montantes_com_ligacao(
    metadados: dict[str, dict], esforcos_por_hipotese: dict[str, dict[str, float]]
) -> set[str]:
    """
    Identifica os montantes que devem ter ligação verificada, com base nas marcações
    'base_modulo' e 'topo_estrutura' atribuídas previamente nos metadados.

    Para cada grupo (base de módulo ou topo da estrutura), seleciona-se:
    - A barra com maior tração (N > 0) entre as hipóteses;
    - A barra com maior compressão (N < 0) entre as hipóteses.

    Args:
        metadados (dict): Metadados das barras com marcações de posição e tipo.
        esforcos_por_hipotese (dict): Esforços axiais por hipótese e por ID de barra.

    Returns:
        set[str]: Conjunto de IDs das barras que devem ter ligação verificada.
    """
    ids_com_ligacao = set()
    esforcos_por_barra = {}

    # Reúne todos os esforços por barra combinando as hipóteses
    for barras in esforcos_por_hipotese.values():
        for id_barra, forca_axial in barras.items():
            esforcos_por_barra.setdefault(id_barra, []).append(forca_axial)

    # Agrupa os montantes em (modulo, posição), considerando apenas base ou topo da estrutura
    grupos: dict[tuple[int, str], list[str]] = {}
    for id_barra, dados in metadados.items():
        if not dados.get("tipo", "").startswith("montante"):
            continue
        modulo = dados.get("modulo")
        if modulo is None:
            continue
        if dados.get("base_modulo"):
            grupos.setdefault((modulo, "base"), []).append(id_barra)
        if dados.get("topo_estrutura"):
            grupos.setdefault((modulo, "topo"), []).append(id_barra)

    # Para cada grupo, escolhe o mais tracionado e o mais comprimido
    for (modulo, posicao), barras in grupos.items():
        melhor_tracao = None
        melhor_compressao = None
        tracao_maxima = -float("inf")
        compressao_maxima = float("inf")
        for id_barra in barras:
            lista = esforcos_por_barra.get(id_barra, [])
            if not lista:
                continue
            forca_axial_maxima = max(lista)
            forca_axial_minima = min(lista)
            if forca_axial_maxima > tracao_maxima:
                tracao_maxima = forca_axial_maxima
                melhor_tracao = id_barra
            if forca_axial_minima < compressao_maxima:
                compressao_maxima = forca_axial_minima
                melhor_compressao = id_barra
        if melhor_tracao:
            ids_com_ligacao.add(melhor_tracao)
        if melhor_compressao:
            ids_com_ligacao.add(melhor_compressao)

    return ids_com_ligacao


def expandir_ligacoes_montantes_simetricos(
    metadados: dict[str, dict], ids_originais: set[str], tolerancia: float = 1e-3
) -> set[str]:
    """
    Expande o conjunto de barras de ligação para incluir barras simétricas.

    Considera como "simétricas" as barras montantes que:
    - Pertencem ao mesmo módulo;
    - Compartilham o mesmo topo (y_max) ou a mesma base (y_min) dentro de uma tolerância;
    - São complementares entre 'montante_esq' e 'montante_dir' (se aplicável).

    Args:
        metadados (dict[str, dict]): Metadados das barras (tipo, módulo, y_min, y_max, etc.).
        ids_originais (set[str]): Conjunto inicial de IDs de barras com ligação verificada.
        tolerancia (float, opcional): Tolerância para considerar topo/base como coincidentes (padrão 1e-3).

    Returns:
        set[str]: Conjunto expandido de IDs de barras incluindo simétricos.
    """

    ids_adicionais = set()

    for id_referencia in ids_originais:
        dados_ref = metadados.get(id_referencia)
        if not dados_ref:
            continue
        if not dados_ref.get("tipo", "").startswith("montante"):
            continue

        modulo_ref = dados_ref.get("modulo")
        y_ref_min = dados_ref.get("y_min")
        y_ref_max = dados_ref.get("y_max")

        if modulo_ref is None or y_ref_min is None or y_ref_max is None:
            continue

        # Se a barra de referência for montante_esq, busca montante_dir, e vice-versa.
        # Se não tiver "esq" nem "dir", aceita qualquer outro montante no mesmo módulo que compartilhe topo/base.
        tipo_ref = dados_ref.get("tipo", "")
        if "esq" in tipo_ref:
            tipo_procurado = "montante_dir"
        elif "dir" in tipo_ref:
            tipo_procurado = "montante_esq"
        else:
            tipo_procurado = "montante"  # aceita qualquer montante no mesmo módulo

        # Procura barras candidatas
        for id_candidato, dados_candidato in metadados.items():
            if id_candidato == id_referencia:
                continue
            if not dados_candidato.get("tipo", "").startswith(tipo_procurado):
                continue
            if dados_candidato.get("modulo") != modulo_ref:
                continue

            y_min = dados_candidato.get("y_min")
            y_max = dados_candidato.get("y_max")
            if y_min is None or y_max is None:
                continue

            # Verifica se compartilham o topo ou a base dentro da tolerância
            mesmo_topo = abs(y_ref_max - y_max) < tolerancia
            mesma_base = abs(y_ref_min - y_min) < tolerancia

            if mesmo_topo or mesma_base:
                ids_adicionais.add(id_candidato)

    return ids_originais.union(ids_adicionais)


def segmentar_montantes_cruzando_modulos(
    estrutura: any,
    montantes_cruzando: dict[str, tuple[int, int, list[int], list[int]]],
    comprimentos_destravados: dict[int, float],
) -> None:
    """
    Divide virtualmente os montantes que cruzam módulos em duas sub-barras artificiais.

    Cada sub-barra criada herda o esforço, tipo e ângulo da barra original, mas
    passa a pertencer apenas ao módulo correspondente ao seu trecho.

    As sub-barras são armazenadas em `estrutura.sub_barras` com IDs no formato '06a', '06b', etc.

    Args:
        estrutura (any): Objeto SystemElements contendo nós, metadados e sub-barras.
        montantes_cruzando (dict): Dicionário {id_barra: (nó1, nó2, módulos_n1, módulos_n2)}.
        comprimentos_destravados (dict): Dicionário {módulo: comprimento destravado (cm)}.

    Returns:
        None
    """
    if not hasattr(estrutura, "sub_barras"):
        estrutura.sub_barras = {}

    for id_barra, (no1, no2, modulos_no1, modulos_no2) in montantes_cruzando.items():
        coord_no1 = estrutura.nos[no1]
        coord_no2 = estrutura.nos[no2]
        x1, y1 = coord_no1
        x2, y2 = coord_no2

        metadados_barra = estrutura.metadados_barras[id_barra]

        # Determina qual nó é superior e qual é inferior
        if y1 > y2:
            no_sup, coord_sup, mods_sup = no1, coord_no1, modulos_no1
            no_inf, coord_inf, mods_inf = no2, coord_no2, modulos_no2
        else:
            no_sup, coord_sup, mods_sup = no2, coord_no2, modulos_no2
            no_inf, coord_inf, mods_inf = no1, coord_no1, modulos_no1

        y_sup = coord_sup[1]
        y_inf = coord_inf[1]

        modulo_sup = min(mods_sup)
        modulo_inf = min(mods_inf)

        # Encontra altura da divisão (base do módulo mais alto)
        y_divisao = min(
            y
            for nid, (x, y) in estrutura.nos.items()
            if modulo_sup in estrutura.metadados_nos.get(nid, {}).get("modulo", [])
        )

        # 3. Calcula comprimentos dos segmentos
        comprimento_a = abs(y_sup - y_divisao)  # Parte superior (módulo mais alto)
        comprimento_b = abs(y_divisao - y_inf)  # Parte inferior (módulo mais baixo)

        # 4. Cria sub-barra superior (a)
        estrutura.sub_barras[f"{id_barra}a"] = {
            "origem": id_barra,
            "sub": "a",
            "comprimento": comprimento_a,
            "modulo": modulo_sup,
            "comprimento_destravado": comprimentos_destravados[modulo_sup],
            "tipo": metadados_barra["tipo"],
            "forca_axial": metadados_barra["forca_axial"],
            "alfa_graus": metadados_barra["alfa_graus"],
            "y_min": min(y_sup, y_divisao),
            "y_max": max(y_sup, y_divisao),
        }

        # 5. Cria sub-barra inferior (b)
        estrutura.sub_barras[f"{id_barra}b"] = {
            "origem": id_barra,
            "sub": "b",
            "comprimento": comprimento_b,
            "modulo": modulo_inf,
            "comprimento_destravado": comprimentos_destravados[modulo_inf],
            "tipo": metadados_barra["tipo"],
            "forca_axial": metadados_barra["forca_axial"],
            "alfa_graus": metadados_barra["alfa_graus"],
            "y_min": min(y_divisao, y_inf),
            "y_max": max(y_divisao, y_inf),
        }


def calcular_comprimentos_destravados_montantes(
    estrutura: any, montantes_puros: dict[int, list[str]]
) -> dict[int, float]:
    """
    Para cada módulo, identifica o maior comprimento de barra entre os montantes que estão totalmente contidos nele.

    Esse valor representa o comprimento destravado a ser usado para o dimensionamento dos montantes daquele módulo.

    Args:
        estrutura (any): Objeto SystemElements contendo os metadados das barras.
        montantes_puros (dict[int, list[str]]): Dicionário {módulo: lista de IDs dos montantes puros}.

    Returns:
        dict[int, float]: Dicionário {módulo: maior comprimento (cm)}.
    """
    comprimentos_por_modulo = {}

    for modulo, lista_ids in montantes_puros.items():
        comprimentos_validos = [
            estrutura.metadados_barras.get(id_barra, {}).get("comprimento", 0.0)
            for id_barra in lista_ids
        ]
        comprimento_maximo = max(comprimentos_validos, default=0.0)
        comprimentos_por_modulo[modulo] = comprimento_maximo

    return comprimentos_por_modulo


def calcular_areas_equivalentes_montantes(resultados: dict) -> dict[int, float]:
    """
    Calcula a área bruta média ponderada por comprimento para cada montante original.

    Sub-barras com sufixos 'a' ou 'b' são agrupadas pelo ID base (ex: '06a' e '06b' viram 6),
    e sua área equivalente é calculada como:

        A_eq = (Σ A_i · L_i) / (Σ L_i)

    Args:
        resultados (dict): Dicionário de resultados por barra, com hipótese "pior_caso" contendo
            os campos "area_bruta" e "comprimento".

    Returns:
        dict[int, float]: Dicionário {id_original: área média ponderada (cm²)}.
    """

    grupos_por_id = defaultdict(list)

    for id_barra, info in resultados.items():
        dados_pior_caso = info.get(info.get("pior_caso"))
        if not dados_pior_caso:
            continue

        area = dados_pior_caso.get("area_bruta")
        comprimento = dados_pior_caso.get("comprimento", 0.0)

        if area is None or comprimento is None:
            continue

        # Remove o sufixo 'a' ou 'b' se for sub-barra (ex: '06a' → 6)
        id_original = (
            int(id_barra[:-1])
            if isinstance(id_barra, str) and id_barra[-1] in "ab"
            else int(id_barra)
        )
        grupos_por_id[id_original].append((area, comprimento))

    areas_por_id = {}
    for id_original, segmentos in grupos_por_id.items():
        soma_area_vezes_comprimento = sum(area * comprimento for area, comprimento in segmentos)
        soma_comprimentos = sum(comprimento for _, comprimento in segmentos)

        if soma_comprimentos > 0:
            areas_por_id[id_original] = soma_area_vezes_comprimento / soma_comprimentos

    return areas_por_id


def obter_menores_tramos_montantes(alturas: list[float], num_diagonais: list[int]) -> list[float]:
    """
    Calcula o menor comprimento vertical (tramo) entre nós em cada módulo da torre.

    O número de tramos por módulo é igual ao número de diagonais da face (D),
    ou seja, `D + 1` nós verticais. Portanto, o menor tramo é `altura / D`.

    Args:
        alturas (list[float]): Alturas de cada módulo (cm).
        num_diagonais (list[int]): Número de diagonais por face em cada módulo.

    Returns:
        list[float]: Lista com os menores tramos verticais por módulo (cm).
    """
    return [altura / d for altura, d in zip(alturas, num_diagonais)]

def reforcar_montante_ate_viavel(
    id_barra: str,
    perfil_atual: str,
    forca_axial: float,
    df_perfis: pd.DataFrame,
    df_materiais: pd.DataFrame,
    diametros_furos: dict[str, float],
    limite_parafusos: dict[str, int],
    planos_cisalhamento: dict[str, int],
    fatores_esmagamento: list[float],
    coef_minoracao: float,
    descontos_area_liquida: dict[str, float],
    criterios_norma_fn,
    criterios_ligacao_fn,
    *,
    tipo_barra: str,
    comprimento: float,
    angulo_graus: float,
    interromper_se_inviavel: bool = True,
) -> tuple[str, dict] | None:
    """
    Percorre a tabela de perfis a partir do perfil atual e retorna o primeiro perfil
    que atenda simultaneamente aos critérios de ligação e aos critérios normativos.

    A função sobe progressivamente na tabela de perfis (ordem crescente de área) até
    encontrar um perfil que satisfaça os seguintes requisitos:

    - A ligação projetada para o perfil deve resultar em uma taxa de trabalho
      `tx_lig` ≤ 1,0.
    - A verificação normativa (tração, compressão, flexão, esbeltez, etc.) deve
      resultar em `tx_norma` ≤ 1,0, segundo a função `criterios_norma_fn`.

    Apenas os perfis compatíveis com o tipo de barra "montante" são considerados.
    Isso inclui:

    - Perfis cuja coluna "Notas" não contenha a indicação “Não utilizar em montante!”;
    - Perfis cujo valor de "D máx" seja maior ou igual ao diâmetro de furo exigido para montantes.

    Essa filtragem reflete uma prática comum em escritórios de engenharia, onde se evita
    utilizar perfis suscetíveis à flambagem local significativa — cuja verificação exigiria
    reduções em `Fy` que comprometem a eficiência do perfil — e também perfis incapazes de
    acomodar o parafuso requerido pela ligação.

    Se um perfil viável for encontrado, retorna uma tupla contendo o nome do perfil
    e os dados da ligação. Caso contrário, lança uma exceção (ou retorna None,
    conforme o parâmetro `interromper_se_inviavel`).

    Args:
        id_barra (str): ID da barra a ser reforçada.
        perfil_atual (str): Nome do perfil atualmente atribuído.
        forca_axial (float): Valor da força axial na barra (em kgf).
        df_perfis (pd.DataFrame): Tabela de perfis estruturais disponíveis.
        df_materiais (pd.DataFrame): Tabela com propriedades dos aços.
        diametros_furos (dict[str, float]): Diâmetro dos furos para cada tipo de barra.
        limite_parafusos (dict[str, int]): Limite máximo de parafusos por ligação.
        planos_cisalhamento (dict[str, int]): Quantidade de planos de cisalhamento por tipo.
        fatores_esmagamento (list[float]): Fatores de redução para o cálculo de Fc/Fe.
        coef_minoracao (float): Coeficiente de minoração das resistências.
        descontos_area_liquida (dict[str, float]): Fatores de desconto para área líquida.
        criterios_norma_fn (Callable): Função que calcula `tx_norma` para o perfil.
        criterios_ligacao_fn (Callable): Função que retorna (`dados_lig`, `tx_lig`) da ligação.
        tipo_barra (str): Tipo da barra ("montante", "diagonal", "horizontal").
        comprimento (float): Comprimento da barra (real ou destravado).
        angulo_graus (float): Ângulo de inclinação da barra, em graus.
        interromper_se_inviavel (bool, optional): Se True, levanta ValueError se
            nenhum perfil for viável. Se False, retorna None. Default = True.

    Returns:
        tuple[str, dict] | None: Tupla com (perfil_escolhido, dados_ligacao), ou
        None se nenhum perfil for viável e `interromper_se_inviavel` for False.

    Raises:
        ValueError: Se nenhum perfil atender aos critérios e `interromper_se_inviavel=True`.
    """
    # Tabela já em ordem crescente de peso/área
    # Aplica filtros antes de ordenar
    diametro_furo = diametros_furos.get("montante", 1.59)
    df_filtrado = filtrar_perfis_montante_reforco(df_perfis, diametro_furo)

    # Ordena por área bruta crescente
    tabela = df_filtrado.sort_values("A(cm2)").reset_index(drop=True)


    idx_atual = tabela.index[tabela["Perfil"].str.strip() == perfil_atual.strip()]
    idx_atual = int(idx_atual[0]) if len(idx_atual) else 0

    for idx in range(idx_atual, len(tabela)):
        linha = tabela.iloc[idx]
        perfil_nome = linha["Perfil"]

        # 1) ligação  –– basta acrescentar tipo_barra
        melhor_lig, tx_lig = criterios_ligacao_fn(
            perfil=linha,
            forca=forca_axial,
            diametros_furos=diametros_furos,
            limite_parafusos=limite_parafusos,
            planos=planos_cisalhamento,
            fatores_esmagamento=fatores_esmagamento,
            coef_minoracao=coef_minoracao,
            df_materiais=df_materiais,
            df_perfis=df_perfis,
            tipo_barra=tipo_barra,
        )
        # 2) norma  –– agora passando tudo o que o helper precisa
        tx_norma = criterios_norma_fn(
            perfil=linha,
            forca=forca_axial,
            descontos_area_liquida=descontos_area_liquida,
            coef_minoracao=coef_minoracao,
            tipo_barra=tipo_barra,
            comprimento=comprimento,
            angulo_graus=angulo_graus,
            df_materiais=df_materiais,
            diametros_furos=diametros_furos,
        )

        if tx_lig <= 1.0 and tx_norma <= 1.0:
            return perfil_nome, melhor_lig

    # se chegou aqui, nenhum perfil foi suficiente
    if interromper_se_inviavel:
        raise ValueError(
            f"Barra {id_barra}: nenhum perfil atende ligação e critérios normativos."
        )
    return None