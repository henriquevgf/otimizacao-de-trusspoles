
from gerador_estrutura import montar_estrutura_modular
from utilitarios.classes import EstruturaComMetadados
from utilitarios.ferramentas_montantes import (
    calcular_comprimentos_destravados_montantes,
    mapear_montantes_por_modulo,
    preparar_montantes_para_dimensionamento,
    segmentar_montantes_cruzando_modulos,
)


def aplicar_apoios(
    estrutura: EstruturaComMetadados,
    nos: dict[int, tuple[float, float]],
    metadados_nos: dict[int, dict[str, any]],
) -> None:
    """
    Aplica apoios fixos nos nós identificados como base da estrutura (apoios).

    A posição (x, y) de cada nó é convertida para o node_id reconhecido pelo anaStruct,
    e um apoio fixo é atribuído.

    Args:
        estrutura: Objeto anaStruct onde os apoios serão aplicados.
        nos: Dicionário com coordenadas dos nós.
        metadados_nos: Metadados contendo marcações de quais nós são apoio.
    """
    for nid, dados in metadados_nos.items():
        if dados.get("apoio"):
            coordenada = nos[nid]
            estrutura.add_support_fixed(node_id=estrutura.find_node_id(coordenada))


def rodar_analise_estrutural(estrutura: EstruturaComMetadados) -> None:
    """
    Executa a análise estrutural para estrutura em questão e armazena os esforços normais (N) nas barras.

    Após a chamada de estrutura.solve(), cada barra terá seu esforço axial máximo (Nmax)
    armazenado no metadado correspondente.

    Args:
        estrutura: Objeto anaStruct já montado e pronto para análise.
    """
    estrutura.solve()
    for resultado in estrutura.get_element_results():
        estrutura.metadados_barras[resultado["id"]]["forca_axial"] = float(resultado["Nmax"])


def executar_hipoteses_carregamento(
    hipoteses: list[dict[str, any]],
    alturas: list[float],
    largura: float,
    diagonais_por_modulo: int | list[int],
    areas_iniciais: dict[str, float] | None = None,
    areas_por_id: dict[int, float] | None = None,
    peso_proprio_inicial_por_modulo: int | float | list[float] | None = None,
    cargas_verticais_por_no: dict[int, float] | None = None,
) -> tuple[dict[str, dict[str, float]], dict[str, EstruturaComMetadados]]:
    """
    Executa a análise estrutural completa para múltiplas hipóteses de carregamento.

    Para cada hipótese fornecida, a estrutura é gerada com os dados específicos
    (como forças horizontais, cargas verticais e áreas), resolvida e os esforços
    axiais (N) são armazenados para cada barra.

    Args:
        hipoteses: Lista de dicionários com dados de entrada por hipótese. Cada dict deve conter:
                   - "nome": Nome identificador da hipótese.
                   - "forcas": Lista de forças horizontais (kgf) por módulo.
        alturas: Lista com a altura de cada módulo (em cm).
        largura: Largura da base da estrutura (em cm).
        diagonais_por_modulo: Número de divisões verticais por módulo (int ou lista).
        areas_iniciais: Áreas padrão por tipo de barra (opcional).
        areas_por_id: Áreas específicas por ID de barra (opcional).
        peso_proprio_inicial_por_modulo: Lista (ou valor único) com pesos dos módulos (kgf).
        cargas_verticais_por_no: Cargas verticais exatas por nó (opcional).

    Returns:
        tuple:
            - Dicionário com esforços N por barra em cada hipótese.
            - Dicionário com as estruturas resolvidas por hipótese.
    """
    # Converte diagonais_por_modulo para lista se necessário
    if isinstance(diagonais_por_modulo, int):
        lista_diagonais_por_modulo = [diagonais_por_modulo] * len(alturas)
    else:
        lista_diagonais_por_modulo = list(diagonais_por_modulo)

    limite_diagonais_por_modulo = max(lista_diagonais_por_modulo)

    esforcos_por_hipotese: dict[str, dict[str, float]] = {}
    estruturas_por_hipotese: dict[str, EstruturaComMetadados] = {}

    for hip in hipoteses:
        nome = hip["nome"]
        forcas = hip["forcas"]

        # Gera a estrutura completa com base nos dados dessa hipótese
        estrutura = montar_estrutura_modular(
            alturas_modulos=alturas,
            largura=largura,
            forcas=forcas,
            limite_diagonais_por_modulo=limite_diagonais_por_modulo,
            diagonais_por_modulo=lista_diagonais_por_modulo,
            areas_por_id=areas_por_id if areas_por_id is not None else None,
            areas_iniciais=areas_iniciais if areas_por_id is None else None,
            peso_proprio_inicial_por_modulo=peso_proprio_inicial_por_modulo,
            cargas_verticais_por_no=cargas_verticais_por_no,
        )

        # Identifica os montantes que ficam 100% dentro de um módulo
        # e os que cruzam entre módulos (precisam ser divididos)
        montantes_puros, montantes_cruzando = mapear_montantes_por_modulo(estrutura)

        # Calcula o comprimento destravado por módulo (maior comprimento dos montantes puros)
        comprimentos_destravados = calcular_comprimentos_destravados_montantes(
            estrutura, montantes_puros
        )

        # Atualiza metadados com comprimento destravado e módulo de origem
        for modulo, barras in montantes_puros.items():
            for bid in barras:
                estrutura.metadados_barras[bid]["comprimento_destravado"] = (
                    comprimentos_destravados[modulo]
                )
                estrutura.metadados_barras[bid]["modulo"] = modulo

        # Segmenta os montantes que cruzam módulos, criando sub-barras com comprimento adequado
        segmentar_montantes_cruzando_modulos(
            estrutura, montantes_cruzando, comprimentos_destravados
        )

        # Seleciona apenas as barras que serão de fato dimensionadas (evita barras internas desnecessárias)
        estrutura.barras_para_dimensionar = preparar_montantes_para_dimensionamento(estrutura)

        # Armazena os esforços N das barras que serão dimensionadas nesta hipótese
        esforcos_por_hipotese[nome] = {}
        for bid, meta in estrutura.barras_para_dimensionar.items():
            esforcos_por_hipotese[nome][bid] = meta["forca_axial"]

        # Guarda a estrutura completa também (para acesso posterior)
        estruturas_por_hipotese[nome] = estrutura

    return esforcos_por_hipotese, estruturas_por_hipotese
