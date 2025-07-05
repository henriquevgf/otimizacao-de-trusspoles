
from utilitarios.classes import EstruturaComMetadados
from utilitarios.constantes import COEF_MAJORACAO_PESO_PROPRIO, COEF_MAJORACAO_FORCAS_HORIZONTAIS

def aplicar_cargas(
    estrutura: EstruturaComMetadados,
    nos: dict[int, tuple[float, float]],
    metadados_nos: dict[int, dict[str, any]],
    forcas: list[float],
    peso_por_modulo: list[float] | None,
    cargas_verticais_por_no: dict[int, float] | None,
) -> None:
    """
    Aplica as cargas horizontais e verticais nos nós da estrutura.

    As cargas verticais podem ser:
    - Derivadas do peso próprio por módulo (repartido nos dois nós mais altos);
    - Ou fornecidas diretamente por nó (e então substituem a lógica de peso próprio).

    Args:
        estrutura: Objeto anaStruct onde as cargas serão aplicadas.
        nos: Dicionário com coordenadas dos nós.
        metadados_nos: Metadados dos nós indicando se são topo, apoio, etc.
        forcas: Lista de cargas horizontais nos topos dos módulos (kgf).
        peso_por_modulo: Lista com o peso próprio (kgf) de cada módulo.
        cargas_verticais_por_no: Dicionário com cargas verticais específicas por nó (já com sinal adequado).
    """
    cargas_por_no: dict[int, dict[str, float]] = {}

    # === Cargas horizontais + peso próprio nos topos dos módulos ===
    # Lista os nós de topo de módulo (para aplicar as cargas Fx nos módulos intermediários)
    topo_nos = [nid for nid, m in metadados_nos.items() if m.get("topo_modulo")]
    topo_nos.sort(key=lambda nid: -nos[nid][1])  # de cima para baixo

    # Identifica o nó de topo da estrutura no lado esquerdo (para aplicação de Fx no topo)
    nids_topo_estrutura = [nid for nid, m in metadados_nos.items() if m.get("topo_estrutura")]
    nid_topo_esquerdo = min(nids_topo_estrutura, key=lambda nid: nos[nid][0]) if nids_topo_estrutura else None

    for i, nid in enumerate(topo_nos):
        fx = (forcas[i] if i < len(forcas) else 0) * COEF_MAJORACAO_FORCAS_HORIZONTAIS
        fy = 0

        # Substitui o nó de topo pelo esquerdo apenas no topo da estrutura
        if i == 0 and nid_topo_esquerdo is not None:
            nid = nid_topo_esquerdo

        if cargas_verticais_por_no is None and peso_por_modulo is not None:
            if i < len(peso_por_modulo):
                fy = -peso_por_modulo[i]
        cargas_por_no.setdefault(nid, {"Fx": 0, "Fy": 0})
        cargas_por_no[nid]["Fx"] += fx
        cargas_por_no[nid]["Fy"] += fy

    # === Peso próprio distribuído nos dois nós mais altos de cada módulo ===
    if cargas_verticais_por_no is None and peso_por_modulo is not None:
        num_modulos = max(m.get("modulo", [0])[0] for m in metadados_nos.values() if "modulo" in m)
        peso_lista = list(peso_por_modulo)
        while len(peso_lista) < num_modulos:
            peso_lista.append(peso_lista[-1])  # Repete o último peso, se necessário

        for modulo in range(1, num_modulos + 1):
            nos_mod = [
                (nid, nos[nid][1])
                for nid in nos
                if modulo in metadados_nos.get(nid, {}).get("modulo", [])
            ]
            dois_mais_altos = sorted(nos_mod, key=lambda item: -item[1])[:2]
            for nid, _ in dois_mais_altos:
                cargas_por_no.setdefault(nid, {"Fx": 0, "Fy": 0})
                cargas_por_no[nid]["Fy"] += -peso_lista[modulo - 1]

    # === Cargas verticais específicas por nó (substitui lógica acima se presente) ===
    if cargas_verticais_por_no:
        for nid, carga in cargas_verticais_por_no.items():
            cargas_por_no.setdefault(nid, {"Fx": 0, "Fy": 0})
            cargas_por_no[nid]["Fy"] += carga  # Já com sinal correto

    # === Aplica todas as cargas acumuladas ===
    for nid, comp in cargas_por_no.items():
        estrutura.point_load(node_id=nid, Fx=comp["Fx"], Fy=comp["Fy"])


def gerar_cargas_peso_proprio(
    estrutura: EstruturaComMetadados,
    peso_montantes_por_modulo: dict[int, float],
    peso_diagonais_por_modulo: dict[int, float],
) -> dict[int, float]:
    """
    Gera cargas verticais de peso próprio nos nós da estrutura com base nos pesos por módulo.

    Para cada módulo:
    - Encontra os dois nós mais altos (maior coordenada y).
    - Aplica em cada um desses dois nós uma carga vertical calculada como:
        carga_por_no = (peso_montantes / 2) + peso_diagonais

    A carga aplicada é negativa (para baixo) e acumulada no dicionário de saída.

    Args:
        estrutura: Objeto anaStruct contendo os nós e metadados da estrutura.
        peso_montantes_por_modulo: Dicionário com peso total dos montantes de cada módulo (em kgf).
        peso_diagonais_por_modulo: Dicionário com peso total das diagonais/horizontais de cada módulo (em kgf).

    Returns:
        dict[int, float]: Dicionário {id_nó: carga_vertical_em_kgf} com as cargas negativas aplicáveis.
    """
    cargas_por_no: dict[int, float] = {}

    modulos = sorted(set(peso_montantes_por_modulo.keys()).union(peso_diagonais_por_modulo.keys()))
    for modulo in modulos:
        # Filtra nós que pertencem ao módulo
        nos_do_modulo = [
            (nid, coord)
            for nid, coord in estrutura.nos.items()
            if modulo in estrutura.metadados_nos.get(nid, {}).get("modulo", [])
        ]

        if not nos_do_modulo:
            continue  # segurança: não há nós neste módulo

        # Seleciona os dois nós mais altos (maior y)
        dois_mais_altos = sorted(nos_do_modulo, key=lambda item: -item[1][1])[:2]
        if len(dois_mais_altos) < 2:
            continue  # segurança: não aplicar se houver apenas um nó

        carga_total = peso_montantes_por_modulo.get(
            modulo, 0.0
        ) / 2.0 + peso_diagonais_por_modulo.get(modulo, 0.0)

        carga_por_no = carga_total * COEF_MAJORACAO_PESO_PROPRIO

        for nid, _ in dois_mais_altos:
            cargas_por_no[nid] = cargas_por_no.get(nid, 0.0) - carga_por_no

    return cargas_por_no
