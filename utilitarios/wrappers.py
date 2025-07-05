from utilitarios.ligacoes import dimensionar_ligacao
from utilitarios.io_excel import obter_fu

def wrapper_ligacao_montante(
    *,
    perfil,                # pd.Series da linha do perfil
    forca: float,          # esforço axial (±)
    diametros_furos: dict,
    limite_parafusos: dict,
    planos: dict,
    fatores_esmagamento: list[float],
    coef_minoracao: float,
    df_materiais,
    df_perfis,
    tipo_barra: str = "montante",
):
    """
    Wrapper que adapta os parâmetros para chamada à função `dimensionar_ligacao`.

    Essa função serve como intermediária entre algoritmos genéricos (como o
    `reforcar_montante_ate_viavel`) e a lógica específica de cálculo de ligações
    para montantes. Ela converte uma linha de perfil em uma chamada completa à
    função `dimensionar_ligacao`, retornando tanto o dicionário com os dados da
    ligação quanto a taxa de trabalho final (`tx_lig`), usada como critério de
    aceitação do perfil.

    Args:
        perfil (pd.Series): Linha da tabela de perfis, contendo as colunas esperadas
            como "Perfil", "t(cm)", etc.
        forca (float): Esforço axial na barra (positivo ou negativo), em kgf.
        diametros_furos (dict): Diâmetro dos furos por tipo de barra.
        limite_parafusos (dict): Quantidade máxima de parafusos permitidos por tipo.
        planos (dict): Quantidade de planos de cisalhamento por tipo de ligação.
        fatores_esmagamento (list[float]): Fatores redutores para cálculo de Fc e Fe.
        coef_minoracao (float): Coeficiente de minoração das resistências (ex: 1.1).
        df_materiais (pd.DataFrame): Tabela de propriedades dos aços disponíveis.
        df_perfis (pd.DataFrame): Tabela de perfis metálicos disponíveis.
        tipo_barra (str, optional): Tipo da barra ("montante", "diagonal", etc.). Default: "montante".

    Returns:
        tuple[dict, float]: Tupla com:
            - dicionário completo da ligação (dados geométricos, fc, fe, np, d, tx_lig, etc.);
            - valor numérico da taxa de trabalho da ligação (`tx_lig`), usado como critério de aprovação.

    Raises:
        KeyError: Se o tipo de barra não estiver definido nas tabelas auxiliares
            (como `diametros_furos`, `limite_parafusos` ou `planos`).
        ValueError: Se algum parâmetro essencial estiver ausente ou incorreto.

    Notes:
        Esta função assume que a ligação será feita com parafusos do tipo A394
        e que o perfil fornecido contém a espessura da aba como `t(cm)`.
    """
    lig = dimensionar_ligacao(
        forca_axial=forca,
        tipo_barra=tipo_barra,
        perfil_nome=perfil["Perfil"],
        espessura_aba=perfil["t(cm)"],
        diametros_furos=diametros_furos,
        fv_parafuso=df_materiais.loc["A394", "fc (kgf/cm²)"],
        fu_peca=obter_fu(perfil, df_materiais),
        limite_parafusos=limite_parafusos,
        planos_cisalhamento=planos,
        fatores_esmagamento=fatores_esmagamento,
        df_perfis=df_perfis,
        coef_minoracao=coef_minoracao,
    )
    return lig, lig["tx_lig"]