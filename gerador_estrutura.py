import math

from utilitarios.classes import EstruturaComMetadados
from utilitarios.constantes import MODULO_ELASTICIDADE_ACO, PESO_PROPRIO_INICIAL_PADRAO
from utilitarios.forcas import aplicar_cargas


def calcular_estrutura_nos(
    alturas_modulos: list[float], largura: float, diagonais_por_modulo: list[int]
) -> tuple[dict[int, tuple[float, float]], dict[int, dict[str, any]]]:
    """
    Gera os nós da estrutura modular e atribui metadados estruturais a cada nó.

    Os nós são construídos módulo por módulo, com coordenadas (x, y), e marcados com:
    - apoio (base da estrutura),
    - topo_estrutura (nó mais alto),
    - topo_modulo (topo local de cada módulo),
    - tipo 'diagonal',
    - e a quais módulos pertence.

    A ordenação final garante que:
    - os nós do lado esquerdo (x=0) vêm antes, de cima para baixo,
    - seguidos pelos do lado direito (x=largura), também de cima para baixo.

    Args:
        alturas_modulos (list[float]): Altura de cada módulo da estrutura (em cm).
        largura (float): Largura horizontal da base da estrutura (em cm).
        diagonais_por_modulo (list[int]): Lista com número de diagonais ou divisões verticais para cada módulo.

    Returns:
        tuple[
            dict[int, tuple[float, float]],        # Coordenadas dos nós por ID
            dict[int, dict[str, any]]              # Metadados dos nós por ID
        ]
    """
    dicionario_nos: dict[int, tuple[float, float]] = {}
    metadados_nos: dict[int, dict[str, any]] = {}
    proximo_id = 1
    y_topo_total = sum(alturas_modulos)

    def adicionar_no(x: float, y: float, marcar_diagonal: bool = True) -> int:
        nonlocal proximo_id
        x, y = round(x, 5), round(y, 5)
        for nid, (xi, yi) in dicionario_nos.items():
            if abs(xi - x) < 1e-6 and abs(yi - y) < 1e-6:
                return nid
        dicionario_nos[proximo_id] = (x, y)
        if marcar_diagonal:
            metadados_nos[proximo_id] = {"tipo": "diagonal"}
        proximo_id += 1
        return proximo_id - 1

    y_topo = y_topo_total
    id_ultimo_no = None

    for i, altura in enumerate(alturas_modulos):
        y_base = y_topo - altura
        ids_modulo = []
        divisoes_verticais_modulo_i = diagonais_por_modulo[i]

        for j in range(divisoes_verticais_modulo_i + 1):
            # Herda o nó de base do módulo anterior (que passa a ser o nó de topo do módulo atual)
            if i > 0 and j == 0:
                topo_id = id_ultimo_no
                ids_modulo.append(topo_id)
                # Marca que esse nó pertence ao módulo atual (i + 1)
                metadados_nos.setdefault(topo_id, {}).setdefault("modulo", [])
                if (i + 1) not in metadados_nos[topo_id]["modulo"]:
                    metadados_nos[topo_id]["modulo"].append(i + 1)

                # Como é o topo do novo módulo, também recebe essa marcação
                metadados_nos[topo_id]["topo_modulo"] = True
                continue

            y = y_topo - j * (altura / divisoes_verticais_modulo_i)

            if not ids_modulo:
                x = largura
            else:
                x = 0 if dicionario_nos[ids_modulo[-1]][0] == largura else largura

            nid = adicionar_no(x, y)

            # Marca o módulo atual (i + 1)
            metadados_nos.setdefault(nid, {}).setdefault("modulo", [])
            if (i + 1) not in metadados_nos[nid]["modulo"]:
                metadados_nos[nid]["modulo"].append(i + 1)

            ids_modulo.append(nid)

        id_ultimo_no = ids_modulo[-1]

        # Marca o topo do módulo (caso não tenha sido herdado)
        if "topo_modulo" not in metadados_nos[ids_modulo[0]]:
            metadados_nos[ids_modulo[0]]["topo_modulo"] = True

        y_topo = y_base

    # Garante marcação dos nós extremos (base e topo)
    extremos = [(0, y_topo_total), (largura, y_topo_total), (0, 0), (largura, 0)]
    for x, y in extremos:
        nid = adicionar_no(x, y, marcar_diagonal=False)
        if abs(y - y_topo_total) < 1e-6:
            metadados_nos.setdefault(nid, {})["topo_estrutura"] = True
        if abs(y) < 1e-6:
            metadados_nos.setdefault(nid, {})["apoio"] = True

    # Corrige marcações de módulo nos nós especiais
    modulo_inferior = len(alturas_modulos)
    for nid, marcas in metadados_nos.items():
        if marcas.get("topo_estrutura"):
            marcas["modulo"] = [1]
        if marcas.get("apoio"):
            marcas["modulo"] = [modulo_inferior]

    # Ordena: esquerda de cima para baixo, depois direita
    esquerda = [(nid, y) for nid, (x, y) in dicionario_nos.items() if abs(x) < 1e-6]
    direita = [(nid, y) for nid, (x, y) in dicionario_nos.items() if abs(x - largura) < 1e-6]
    esquerda.sort(key=lambda t: -t[1])
    direita.sort(key=lambda t: -t[1])
    nova_ordem = [nid for nid, _ in esquerda + direita]

    # Reconstrói os dicionários com IDs sequenciais
    dicionario_nos_final: dict[int, tuple[float, float]] = {}
    metadados_nos_final: dict[int, dict[str, any]] = {}
    for novo_id, antigo_id in enumerate(nova_ordem, start=1):
        dicionario_nos_final[novo_id] = dicionario_nos[antigo_id]
        metadados_nos_final[novo_id] = metadados_nos.get(antigo_id, {})

    return dicionario_nos_final, metadados_nos_final


def adicionar_barra(
    estrutura: EstruturaComMetadados,
    localizacao: list[tuple[float, float]],
    rigidez_axial: float,
    tipo_barra: str,
) -> None:
    """
    Adiciona uma barra à estrutura anaStruct, calculando comprimento, ângulo e armazenando metadados.

    A função atribui a rigidez axial (E × A) diretamente no momento da criação da barra,
    garantindo que a matriz de rigidez global da estrutura seja corretamente construída.

    Args:
        estrutura (SystemElements): Objeto anaStruct com atributos personalizados.
        localizacao (list[tuple[float, float]]): Lista com dois pontos (x, y) definindo os nós da barra.
        rigidez_axial (float): Produto E × A da barra, em kgf.
        tipo_barra (str): Tipo da barra (ex: 'montante_esq', 'diagonal', etc.).
    """
    estrutura.contador_barras += 1
    id_barra = estrutura.contador_barras

    estrutura.add_truss_element(location=localizacao, EA=rigidez_axial)

    x1, y1 = localizacao[0]
    x2, y2 = localizacao[1]
    comprimento = math.hypot(x2 - x1, y2 - y1)
    angulo = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 360

    estrutura.metadados_barras[id_barra] = {
        "tipo": tipo_barra,
        "comprimento": comprimento,
        "alfa_graus": round(angulo, 2),
        "no1": estrutura.find_node_id(localizacao[0]),
        "no2": estrutura.find_node_id(localizacao[1]),
        "y_min": min(y1, y2),
        "y_max": max(y1, y2),
    }


def criar_estrutura(
    nos: dict[int, tuple[float, float]],
    metadados_nos: dict[int, dict[str, any]],
    forcas: list[float],
    areas: dict[str, float],
    areas_por_id: dict[int, float] | None = None,
    peso_proprio_inicial_por_modulo: int | float | list[float] | None = None,
    cargas_verticais_por_no: dict[int, float] | None = None,
    modulo_e: float = MODULO_ELASTICIDADE_ACO,
) -> EstruturaComMetadados:
    """
    Coordena a criação completa da estrutura: lançamento das barras, aplicação de cargas, apoios e solução.

    Args:
        nos: Dicionário de coordenadas dos nós.
        metadados_nos: Dicionário com informações dos nós (ex: tipo, módulo, apoio...).
        forcas: Lista de cargas horizontais nos topos dos módulos (Fh).
        areas: Dicionário com áreas brutas padrão para cada tipo de barra.
        areas_por_id: (Opcional) Áreas específicas por ID de barra.
        peso_proprio_inicial_por_modulo: (Opcional) Lista com peso próprio de cada módulo (kgf).
        cargas_verticais_por_no: (Opcional) Dicionário com cargas verticais aplicadas diretamente por nó.
        modulo_e: Módulo de elasticidade do aço.

    Returns:
        EstruturaComMetadados: Objeto anaStruct com toda a estrutura resolvida e esforços armazenados.
    """
    from utilitarios.analise_estrutural import aplicar_apoios, rodar_analise_estrutural

    estrutura = EstruturaComMetadados()

    if isinstance(peso_proprio_inicial_por_modulo, (int, float)):
        peso_proprio_inicial_por_modulo = [float(peso_proprio_inicial_por_modulo)]
    elif peso_proprio_inicial_por_modulo is None:
        peso_proprio_inicial_por_modulo = None
    else:
        peso_proprio_inicial_por_modulo = list(peso_proprio_inicial_por_modulo)

    lancar_barras(estrutura, nos, metadados_nos, areas, areas_por_id, modulo_e)

    aplicar_cargas(
        estrutura,
        nos,
        metadados_nos,
        forcas,
        peso_proprio_inicial_por_modulo,
        cargas_verticais_por_no,
    )

    aplicar_apoios(estrutura, nos, metadados_nos)

    rodar_analise_estrutural(estrutura)

    estrutura.nos = nos
    estrutura.metadados_nos = metadados_nos
    return estrutura


def lancar_barras(
    estrutura: EstruturaComMetadados,
    nos: dict[int, tuple[float, float]],
    metadados_nos: dict[int, dict[str, any]],
    areas: dict[str, float],
    areas_por_id: dict[int, float] | None,
    modulo_e: float,
) -> None:
    """
    Lança todos os elementos estruturais na estrutura: montantes, diagonais e horizontal superior.

    Args:
        estrutura: Objeto anaStruct onde as barras serão lançadas.
        nos: Dicionário com coordenadas dos nós.
        metadados_nos: Metadados indicando o tipo de cada nó (diagonal, topo, apoio, etc).
        areas: Áreas padrão por tipo de barra (montante_esq, diagonal, etc).
        areas_por_id: Dicionário com áreas específicas para cada ID de barra (pode ser None).
        modulo_e: Módulo de elasticidade do aço (kgf/cm²).
    """
    # Montantes esquerdo e direito
    esquerda = [(nid, coord) for nid, coord in nos.items() if abs(coord[0]) < 1e-6]
    direita = [
        (nid, coord)
        for nid, coord in nos.items()
        if abs(coord[0] - max(x for x, _ in nos.values())) < 1e-6
    ]
    esquerda.sort(key=lambda x: -x[1][1])
    direita.sort(key=lambda x: -x[1][1])

    for i in range(len(esquerda) - 1):
        id_temp = estrutura.contador_barras + 1
        area = areas_por_id.get(id_temp) if areas_por_id else areas['montante_esq']
        if area is None:
            continue  # Pula a barra se não há área definida
        adicionar_barra(
            estrutura, [esquerda[i][1], esquerda[i + 1][1]], modulo_e * area, 'montante_esq'
        )
        estrutura.metadados_barras[id_temp]["area_bruta"] = area
        estrutura.element_map[id_temp].EA = modulo_e * area

    for i in range(len(direita) - 1):
        id_temp = estrutura.contador_barras + 1
        area = areas_por_id.get(id_temp) if areas_por_id else areas['montante_dir']
        if area is None:
            continue  # Pula a barra se não há área definida
        adicionar_barra(
            estrutura, [direita[i][1], direita[i + 1][1]], modulo_e * area, 'montante_dir'
        )
        estrutura.metadados_barras[id_temp]["area_bruta"] = area
        estrutura.element_map[id_temp].EA = modulo_e * area

    # Diagonais
    diagonais = sorted(
        [(nid, nos[nid]) for nid, m in metadados_nos.items() if m.get("tipo") == "diagonal"],
        key=lambda x: -x[1][1],
    )

    for i in range(len(diagonais) - 1):
        id_temp = estrutura.contador_barras + 1
        area = areas_por_id.get(id_temp) if areas_por_id else areas['diagonal']
        if area is None:
            continue  # Pula a barra se não há área definida
        adicionar_barra(
            estrutura, [diagonais[i][1], diagonais[i + 1][1]], modulo_e * area, 'diagonal'
        )
        estrutura.metadados_barras[id_temp]["area_bruta"] = area
        estrutura.element_map[id_temp].EA = modulo_e * area

    # Horizontal superior
    topo_nos = [nid for nid, m in metadados_nos.items() if m.get("topo_estrutura")]
    if len(topo_nos) == 2:
        p1, p2 = nos[topo_nos[0]], nos[topo_nos[1]]
        if abs(p1[1] - p2[1]) < 1e-6:
            id_temp = estrutura.contador_barras + 1
            area = areas_por_id.get(id_temp) if areas_por_id else areas['horizontal_sup']
            if area is not None:
                adicionar_barra(estrutura, [p1, p2], modulo_e * area, 'horizontal_sup')
                estrutura.metadados_barras[id_temp]["area_bruta"] = area
                estrutura.element_map[id_temp].EA = modulo_e * area


def montar_estrutura_modular(
    *,
    alturas_modulos: list[float],
    largura: float,
    forcas: list[float],
    limite_diagonais_por_modulo: int,
    areas_iniciais: dict[str, float] | None = None,
    diagonais_por_modulo: list[int] | None = None,
    areas_por_id: dict[int, float] | None = None,
    peso_proprio_inicial_por_modulo: int | float | list[float] | None = None,
    cargas_verticais_por_no: dict[int, float] | None = None,
) -> EstruturaComMetadados:
    """
    Gera uma estrutura modular com base nas informações geométricas e de carregamento fornecidas.

    Esta função é utilizada para integração com os módulos de dimensionamento e otimização.
    Ela calcula os nós e metadados da estrutura e monta a estrutura final com os esforços.

    Args:
        alturas_modulos: Lista com altura de cada módulo (em cm).
        largura: Largura da base da estrutura (em cm).
        forcas: Lista de forças horizontais (kgf), uma por módulo.
        limite_diagonais_por_modulo: Número máximo de divisões verticais permitido.
        areas_iniciais: Áreas padrão por tipo de barra.
        diagonais_por_modulo: Número de divisões verticais por módulo (opcional).
        areas_por_id: Áreas específicas por ID de barra (opcional).
        peso_proprio_inicial_por_modulo: Lista com peso próprio estimado de cada módulo (kgf).
        cargas_verticais_por_no: Dicionário com cargas verticais exatas por nó (se houver).

    Returns:
        EstruturaComMetadados: Estrutura resolvida, com metadados e esforços armazenados.
    """
    if areas_por_id is not None:
        areas_utilizadas = areas_por_id
    elif areas_iniciais is not None:
        areas_utilizadas = areas_iniciais
    else:
        raise ValueError("Você deve fornecer 'areas_por_id' ou 'areas_iniciais'")

    if diagonais_por_modulo is None:
        diagonais_por_modulo = [limite_diagonais_por_modulo for _ in alturas_modulos]

    nos, metadados = calcular_estrutura_nos(alturas_modulos, largura, diagonais_por_modulo)

    estrutura = criar_estrutura(
        nos,
        metadados,
        forcas,
        areas=areas_utilizadas,
        areas_por_id=areas_por_id,
        peso_proprio_inicial_por_modulo=peso_proprio_inicial_por_modulo,
        cargas_verticais_por_no=cargas_verticais_por_no,
    )

    return estrutura