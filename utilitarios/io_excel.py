
import pandas as pd

"""
Módulo de utilitários para leitura de dados de planilhas de Excel usados no algoritmo de otimização estrutural.

Funções:
- carregar_tabela_perfis: carrega e filtra a tabela de perfis estruturais.
- carregar_tabela_materiais: carrega as propriedades dos materiais e indexa por nome.
"""


def carregar_tabela_perfis(caminho_excel: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Lê o arquivo Excel com dados dos perfis e retorna dois DataFrames filtrados.

    Args:
        caminho_excel (str): Caminho para o arquivo .xlsx contendo a aba de perfis.

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame]:
            - df_montantes: Apenas perfis com nota "OK!".
            - df_diagonais_horizontais: Perfis com nota "OK!" ou "Não utilizar em montante! (Flambagem Local)".

    Raises:
        FileNotFoundError: Se o arquivo não for encontrado.
    """
    df = pd.read_excel(caminho_excel)
    df.columns = df.columns.str.strip()
    df_montantes = df[df["Notas"] == "OK!"].copy()
    df_diagonais_horizontais = df[
        df["Notas"].isin(["OK!", "Não utilizar em montante! (Flambagem Local)"])
    ].copy()
    return df_montantes, df_diagonais_horizontais


def carregar_tabela_materiais(caminho_excel: str) -> pd.DataFrame:
    """
    Lê o arquivo Excel com propriedades dos materiais e define a coluna "Material" como índice.

    Args:
        caminho_excel (str): Caminho para o arquivo .xlsx contendo as propriedades dos materiais.

    Returns:
        pd.DataFrame: DataFrame indexado por "Material".

    Raises:
        FileNotFoundError: Se o arquivo não for encontrado.
        KeyError: Se a coluna "Material" não estiver presente.
    """
    df = pd.read_excel(caminho_excel)
    df.columns = df.columns.str.strip()
    return df.set_index("Material")


def obter_fy(linha_perfil: dict | pd.Series, df_materiais: pd.DataFrame) -> float:
    """
    Retorna a tensão de escoamento (fy) do aço utilizado no perfil.

    Args:
        linha_perfil (pd.Series): Linha da tabela de perfis, contendo a chave "Aço".
        df_materiais (pd.DataFrame): Tabela de materiais com coluna "fy (kgf/cm²)".

    Returns:
        float: Tensão de escoamento (fy) em kgf/cm².

    Raises:
        KeyError: Se o valor de "Aço" não existir em df_materiais.index.
    """
    aco = linha_perfil.get("Aço", "A572-50")
    return df_materiais.loc[aco, "fy (kgf/cm²)"]


def obter_fu(linha_perfil: pd.Series, df_materiais: pd.DataFrame) -> float:
    """
    Retorna a tensão de ruptura (fu) do aço utilizado no perfil.

    Args:
        linha_perfil (pd.Series): Linha da tabela de perfis, contendo a chave "Aço".
        df_materiais (pd.DataFrame): Tabela de materiais com coluna "fu (kgf/cm²)".

    Returns:
        float: Tensão de ruptura (fu) em kgf/cm².

    Raises:
        KeyError: Se o valor de "Aço" não existir em df_materiais.index.
    """
    aco = linha_perfil.get("Aço", "A572-50")
    return df_materiais.loc[aco, "fu (kgf/cm²)"]

def filtrar_por_diametro_parafuso(tabela: pd.DataFrame, diametro_cm: float) -> pd.DataFrame:
    """
    Filtra os perfis com base no diâmetro máximo de parafuso permitido,
    tratando perfis com valor ausente como se não tivessem restrição e emitindo aviso.

    Perfis com valor ausente na coluna "D máx" não são descartados automaticamente,
    mas o usuário será alertado sobre essa situação.

    Args:
        tabela: DataFrame com os perfis estruturais, contendo a coluna "D máx".
        diametro_cm: Diâmetro do parafuso (em cm) a ser utilizado na ligação.

    Returns:
        Um novo DataFrame com apenas os perfis compatíveis com o diâmetro informado,
        incluindo os que não possuem valor de "D máx" (com aviso).
    """
    # Perfis com valor ausente em "D máx" serão mantidos, mas alertados
    perfis_sem_dmax = tabela[tabela["D máx"].isna()]
    if not perfis_sem_dmax.empty:
        print(f"[AVISO] {len(perfis_sem_dmax)} perfis sem valor em 'D máx' foram considerados sem restrição.")

    return tabela[(tabela["D máx"].isna()) | (tabela["D máx"] >= diametro_cm)].copy()

def filtrar_perfis_montante_reforco(tabela: pd.DataFrame, diametro_cm: float) -> pd.DataFrame:
    """
    Filtra a tabela de perfis para uso como montantes no reforço, removendo:

    - Perfis com nota "Não utilizar em montante! (Flambagem Local)";
    - Perfis com "D máx" menor que o diâmetro fornecido (se presente).

    Perfis com 'D máx' ausente são mantidos com aviso.

    Args:
        tabela: DataFrame com os perfis estruturais (inclusive a coluna 'Notas').
        diametro_cm: Diâmetro de parafuso (em cm) a ser usado na ligação.

    Returns:
        DataFrame filtrado para uso seguro em montantes reforçados.
    """
    # 1. Remove perfis com nota proibitiva
    filtrado = tabela[~tabela["Notas"].str.contains("Não utilizar em montante", na=False)].copy()

    # 2. Aplica o filtro de diâmetro máximo (com aviso)
    from utilitarios.io_excel import filtrar_por_diametro_parafuso
    return filtrar_por_diametro_parafuso(filtrado, diametro_cm)
