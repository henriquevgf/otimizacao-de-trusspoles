import math

import pandas as pd

from utilitarios.constantes import (
    COEF_MINORACAO_PADRAO,
    LIMITE_ESBELTEZ_DIAG_HORIZ,
    LIMITE_ESBELTEZ_MONTANTE,
    LIMITE_ESBELTEZ_TRACAO,
    MODULO_ELASTICIDADE_ACO,
)
from utilitarios.io_excel import obter_fy


def calcular_esbeltez_corrigida(tipo_barra: str, comprimento: float, raio_giracao: float) -> float:
    """
    Calcula a esbeltez corrigida (L/r) conforme ASCE 10-15, aplicando ajustes
    de curva de flambagem para diagonais e horizontais.

    Para montantes, retorna diretamente L/r.
    Para diagonais/horizontais, aplica:
        - Se L/r ≤ 120 → esbeltez_corrigida = 60 + 0.5 * (L/r)
        - Se L/r > 120 → esbeltez_corrigida = L/r

    Args:
        tipo_barra (str): Tipo da barra ("montante", "diagonal" ou "horizontal").
        comprimento (float): Comprimento efetivo da barra (cm).
        raio_giracao (float): Raio de giração da barra (cm).

    Returns:
        float: Esbeltez corrigida (adimensional).
    """
    esbeltez = comprimento / raio_giracao

    if tipo_barra.startswith("montante"):
        esbeltez_corrigida = esbeltez

    else:
        if esbeltez <= 120:
            esbeltez_corrigida = 60 + 0.5 * esbeltez
        else:
            esbeltez_corrigida = esbeltez

    return esbeltez_corrigida


def corrigir_fy_por_flambagem_local(
    dados_perfil: dict[str, float], modulo_elasticidade: float, tensao_fy_nominal: float
) -> float:
    """
    Aplica correção de flambagem local na tensão de escoamento (Fy) de perfis
    comprimidos, conforme a ASCE 10-15. A redução depende da razão w/t,
    onde w = b - t - R.

    Args:
        dados_perfil (dict): Dicionário com propriedades geométricas do perfil.
            Requer as chaves:
            - 'b(cm)' : largura total da aba (cm)
            - 't(cm)' : espessura da aba (cm)
            - 'raio lam.(cm)' : raio de laminação da aba (cm)
        modulo_elasticidade (float): Módulo de elasticidade do material (kgf/cm²).
        tensao_fy_nominal (float): Tensão de escoamento não corrigida (kgf/cm²).

    Returns:
        float: Tensão de escoamento corrigida (kgf/cm²). Pode ser menor que
        a nominal se o perfil for esbelto localmente.
    """
    # === Conversão de unidades: kgf/cm² → MPa ===
    fy_mpa = tensao_fy_nominal / 10.1972
    e_mpa = modulo_elasticidade / 10.1972

    # === Geometria ===
    largura_aba = dados_perfil["b(cm)"]  # largura das abas em cm
    espessura_aba = dados_perfil["t(cm)"]  # espessura das abas em cm
    raio_laminacao = dados_perfil["raio lam.(cm)"]  # raio de laminação em cm

    largura_util = largura_aba - espessura_aba - raio_laminacao
    rel_w_t = largura_util / espessura_aba

    # Limites normativos (ASCE 10-15)
    limite_inferior = 209.6 / math.sqrt(fy_mpa)
    limite_superior = 377.28 / math.sqrt(fy_mpa)

    # === Avaliação ===
    if rel_w_t <= limite_inferior:
        fy_corrigido_mpa = fy_mpa  # Perfil compacto → Fy não altera

    elif rel_w_t <= limite_superior:
        fator_reducao = 1.677 - 0.677 * (rel_w_t / limite_inferior)
        fy_corrigido_mpa = fator_reducao * fy_mpa

    else:
        fy_corrigido_mpa = (0.0332 * math.pi ** 2 * e_mpa) / (rel_w_t ** 2)

    # === Conversão de volta: MPa → kgf/cm² ===
    fy_corrigido = fy_corrigido_mpa * 10.1972

    return fy_corrigido


def fa_asce(
    esbeltez_corrigida: float, modulo_elasticidade: float, tensao_fy_corrigida: float
) -> float:
    """
    Calcula a tensão admissível a compressão (Fa) segundo ASCE 10‑15.

    A fórmula depende da comparação da esbeltez corrigida (λ) com o valor crítico Cc:
    - Se λ ≤ Cc (regime inelástico): Fa = (1 - 0.5 * (λ/Cc)²) * Fy
    - Se λ > Cc (regime elástico):    Fa = (π² * E) / λ²

    Args:
        esbeltez_corrigida (float): Esbeltez corrigida da barra (L/r).
        modulo_elasticidade (float): Módulo de elasticidade do aço (kgf/cm²).
        tensao_fy_corrigida (float): Tensão de escoamento corrigida (kgf/cm²).

    Returns:
        float: Tensão admissível à compressão (Fa), em kgf/cm².
    """
    cc = math.pi * math.sqrt(2 * modulo_elasticidade / tensao_fy_corrigida)
    if esbeltez_corrigida <= cc:
        return (1 - 0.5 * (esbeltez_corrigida / cc) ** 2) * tensao_fy_corrigida
    else:
        return (math.pi**2 * modulo_elasticidade) / (esbeltez_corrigida**2)


def verifica_flexao_simples(
    tipo_barra: str,
    angulo_graus: float,
    comprimento: float,
    modulo_resistencia_flexao_x: float,
    tensao_fy: float,
    coef_minoracao: float = COEF_MINORACAO_PADRAO,
) -> bool:
    """
    Verifica a resistência à flexão simples para barras inclinadas até 45° em
    relação à horizontal, aplicando uma carga de 100 kgf no meio do vão.

    Args:
        tipo_barra (str): Tipo da barra ("diagonal", "horizontal" ou "montante").
        angulo_graus (float): Ângulo de inclinação da barra em graus.
        comprimento (float): Comprimento da barra (cm).
        modulo_resistencia_flexao_x (float): Módulo de resistência à flexão (Wx) da barra (cm³).
        tensao_fy (float): Tensão de escoamento do material (kgf/cm²).
        coef_minoracao (float): Coeficiente de minoração (Φ). Padrão = 0,9.

    Returns:
        bool: True se a barra atende ao critério de flexão ou se o critério não se aplica.
              False se a barra reprovar por flexão.
    """
    if tipo_barra.startswith("montante"):
        return True

    # aplica apenas se o ângulo estiver nas seguintes faixas:
    if not (
        (0 <= angulo_graus <= 45) or (135 <= angulo_graus <= 225) or (315 <= angulo_graus <= 360)
    ):
        return True  # Fora da faixa de verificação para flexão

    momento_solicitante = (100 * comprimento) / 4  # kgf·cm
    momento_resistente = modulo_resistencia_flexao_x * tensao_fy * coef_minoracao  # kgf·cm

    return momento_solicitante <= momento_resistente


def dicionario_inviavel(solicitacao):
    """
    Cria um dicionário padrão para representar uma barra inviável no dimensionamento,
    preenchendo todos os campos normativos relevantes com valores nulos.

    Args:
        solicitacao (str): Tipo de solicitação que levou à inviabilidade ("compressao" ou "tracao").

    Returns:
        dict: Dicionário com todos os campos preenchidos como None ou False, exceto pela solicitação.
    """

    return {
        "solicitacao": solicitacao,
        "viavel": False,
        "tensao_solicitante": None,
        "area_bruta": None,
        "area_efetiva": None,
        "forca_axial_admissivel": None,
        "taxa_trabalho": None,
        "esbeltez_corrigida": None,
        "tensao_fy_corrigida": None,
        "Fa": None,
        "Fa_reduzido": None,
        "ft_admissivel": None,
        "esbeltez_tracao": None,
    }


def calcular_area_liquida_efetiva(
    dados_perfil: dict,
    diametro_furo: float,
    ct: float,
    tipo_barra: str,
    descontos_area_liquida: dict = None,
) -> float:
    """
    Calcula a área líquida efetiva (Ae) para uma cantoneira tracionada, considerando o desconto
    de furos de parafusos e aplicando o coeficiente de correção Ct.

    Fórmula utilizada:
        Ae = (Ag - n * (d + 0.3175) * t) * Ct

    onde:
        - Ag é a área bruta da seção (coluna "A(cm2)"),
        - n é o número de diâmetros descontados,
        - d é o diâmetro do furo informado, acrescido da folga de 0.3175 cm,
        - t é a espessura da aba (coluna "t(cm)"),
        - Ct é o coeficiente de correção para tração.

    Args:
        dados_perfil (dict): Dados do perfil (deve conter "A(cm2)", "t(cm)", "Qtd furos An").
        diametro_furo (float): Diâmetro do furo de ligação (cm).
        ct (float): Coeficiente de correção (Ct = 1.0 para montantes, 0.9 para diagonais e horizontais).
        tipo_barra (str): Tipo da barra ("montante", "diagonal" ou "horizontal").
        descontos_area_liquida (dict, opcional): Sobrescrita do número de furos descontados por tipo de barra.

    Returns:
        float: Área efetiva corrigida da barra (cm²).
    """
    area_bruta = dados_perfil["A(cm2)"]
    espessura_aba = dados_perfil["t(cm)"]

    # Determina o número de diâmetros a descontar (n)
    if descontos_area_liquida is not None:
        tipo_base = (
            "montante"
            if "montante" in tipo_barra
            else (
                "diagonal"
                if "diagonal" in tipo_barra
                else "horizontal" if "horizontal" in tipo_barra else None
            )
        )

        if tipo_base in descontos_area_liquida:
            n_furos = descontos_area_liquida[tipo_base]
        else:
            n_furos = dados_perfil["Qtd furos An"]
    else:
        n_furos = dados_perfil["Qtd furos An"]

    # Aplica a folga normativa ao diâmetro
    diametro_ajustado = diametro_furo + 0.3175

    # Calcula área líquida e efetiva
    area_liquida = area_bruta - n_furos * diametro_ajustado * espessura_aba
    area_efetiva = area_liquida * ct
    return area_efetiva


def calcula_tensao_axial_admissivel(
    df_materiais: pd.DataFrame,
    dados_perfil: dict,
    forca_axial: float,
    tipo_barra: str,
    comprimento_efetivo: float,
    coef_minoracao: float,
    diametro_furo: float = 1.59,
    modulo_elasticidade: float = MODULO_ELASTICIDADE_ACO,
    limitar_esbeltez_tracao: bool = False,
    forcar_verificacao_compressao: bool = False,
    descontos_area_liquida: dict = None,
) -> dict:
    """
    Calcula a capacidade axial admissível (tensão e força) de um perfil estrutural,
    considerando flambagem local, flambagem global e descontos de área líquida para tração.

    O processo inclui:
    - Correção do Fy para flambagem local;
    - Cálculo da esbeltez corrigida (L/r);
    - Determinação da tensão admissível:
      - Compressão: pela fórmula da ASCE 10-15 (com minorador),
      - Tração: área líquida efetiva e tensão limitada conforme esbeltez;
    - Avaliação de viabilidade normativa;
    - Cálculo da taxa de trabalho da barra.

    Args:
        df_materiais (pd.DataFrame): Tabela de propriedades dos materiais (deve conter "Fy" e "Fu").
        dados_perfil (dict): Dados geométricos do perfil (deve conter "A(cm2)", "t(cm)", etc).
        forca_axial (float): Força axial solicitante (kgf). Positivo para tração, negativo para compressão.
        tipo_barra (str): Tipo da barra ("montante", "diagonal" ou "horizontal").
        comprimento_efetivo (float): Comprimento destravado ou livre da barra (cm).
        coef_minoracao (float): Coeficiente de minoração de resistência (γ).
        diametro_furo (float, opcional): Diâmetro dos furos para ligação (cm). Default é 1.59 cm.
        modulo_elasticidade (float, opcional): Módulo de elasticidade do material (kgf/cm²).
        limitar_esbeltez_tracao (bool, opcional): Se True, limita a esbeltez de barras tracionadas.
        forcar_verificacao_compressao (bool, opcional): Se True, força a verificação de compressão mesmo se N > 0.
        descontos_area_liquida (dict, opcional): Sobrescrita do número de furos descontados por tipo de barra.

    Returns:
        dict: Dicionário contendo:
            - solicitacao: "compressao" ou "tracao"
            - viavel: True/False
            - tensao_solicitante: tensão real solicitada (kgf/cm²)
            - area_bruta: área bruta (cm²)
            - area_efetiva: área líquida efetiva corrigida (cm²) (se aplicável)
            - forca_axial_admissivel: força admissível (kgf)
            - taxa_trabalho: relação |N|/N_admissível
            - esbeltez_corrigida: esbeltez final (L/r)
            - tensao_fy_corrigida: Fy corrigido para flambagem local (kgf/cm²)
            - Fa: tensão admissível antes da minoração (kgf/cm²)
            - Fa_reduzido: tensão admissível minorada (kgf/cm²)
            - ft_admissivel: tensão admissível à tração (kgf/cm²)
            - esbeltez_tracao: esbeltez real para barras tracionadas (se aplicável)
    """
    # Bloco 1: Definições iniciais
    solicitacao = "tracao" if forca_axial > 0 else "compressao"
    ct = 1.0 if tipo_barra.startswith("montante") else 0.9

    # Extração de propriedades geométricas
    area_bruta = dados_perfil["A(cm2)"]
    if tipo_barra.startswith("montante"):
        raio_giracao = dados_perfil["rx(cm)"]
    else:
        raio_giracao = dados_perfil["rz(cm)"]

    # Obter propriedades do material
    tensao_fy_nominal = obter_fy(dados_perfil, df_materiais)

    # Cálculo da esbeltez real
    esbeltez_real = comprimento_efetivo / raio_giracao if raio_giracao else 9999

    # Bloco 2: Verificação de limites de esbeltez

    if solicitacao == "compressao" or forcar_verificacao_compressao:
        # Compressão (ou tração forçada a verificar compressão)
        if tipo_barra.startswith("montante"):
            # Montantes: limitar esbeltez real
            if esbeltez_real > LIMITE_ESBELTEZ_MONTANTE:
                return dicionario_inviavel(solicitacao)

        else:
            # Diagonais e horizontais: limitar esbeltez corrigida
            esbeltez_corrigida = calcular_esbeltez_corrigida(
                tipo_barra, comprimento_efetivo, raio_giracao
            )
            if esbeltez_corrigida > LIMITE_ESBELTEZ_DIAG_HORIZ:
                return dicionario_inviavel(solicitacao)

    elif solicitacao == "tracao":
        # Tração: opcionalmente limitar esbeltez real
        if limitar_esbeltez_tracao and esbeltez_real > LIMITE_ESBELTEZ_TRACAO:
            return dicionario_inviavel(solicitacao)

    # Bloco 3: Cálculo da área efetiva (para tração) e tensão solicitante

    # Cálculo da área líquida efetiva (apenas para tração)
    area_efetiva = calcular_area_liquida_efetiva(
        dados_perfil=dados_perfil,
        diametro_furo=diametro_furo,
        ct=ct,
        tipo_barra=tipo_barra,
        descontos_area_liquida=descontos_area_liquida,
    )

    # Definição da seção utilizada para calcular tensão
    if solicitacao == "compressao":
        secao_utilizada = area_bruta
    else:
        secao_utilizada = area_efetiva

    # Cálculo da tensão solicitante
    tensao_solicitante = abs(forca_axial) / secao_utilizada if secao_utilizada else 1e12

    # Bloco 4: Verificação final de compressão ou tração
    if solicitacao == "compressao":
        # Para barras comprimidas
        esbeltez_corrigida = calcular_esbeltez_corrigida(
            tipo_barra, comprimento_efetivo, raio_giracao
        )
        tensao_fy_corrigida = corrigir_fy_por_flambagem_local(
            dados_perfil, modulo_elasticidade, tensao_fy_nominal
        )
        tensao_adm_compressao = fa_asce(
            esbeltez_corrigida, modulo_elasticidade, tensao_fy_corrigida
        )
        tensao_adm_reduzida = coef_minoracao * tensao_adm_compressao

        viavel = tensao_solicitante <= tensao_adm_reduzida
        forca_axial_admissivel = tensao_adm_reduzida * area_bruta

        # Preenche resultados intermediários para debug
        ft_admissivel = None
        esbeltez_tracao = None

    else:
        # Para barras tracionadas
        ft_admissivel = coef_minoracao * tensao_fy_nominal
        esbeltez_tracao = comprimento_efetivo / raio_giracao if raio_giracao else 9999

        viavel = tensao_solicitante <= ft_admissivel
        forca_axial_admissivel = ft_admissivel * area_efetiva

        # Preenche resultados intermediários para debug
        esbeltez_corrigida = None
        tensao_fy_corrigida = tensao_fy_nominal
        tensao_adm_compressao = None
        tensao_adm_reduzida = None

    # Bloco 5: Cálculo da taxa de trabalho e montagem do dicionário de retorno

    # Cálculo da taxa de trabalho
    taxa_trabalho = (
        abs(forca_axial) / forca_axial_admissivel
        if (forca_axial_admissivel and forca_axial_admissivel > 1e-9)
        else 9999
    )

    # Monta o dicionário final de resultados
    return {
        "solicitacao": solicitacao,
        "viavel": viavel,
        "tensao_solicitante": tensao_solicitante,
        "area_bruta": area_bruta,
        "area_efetiva": area_efetiva,
        "forca_axial_admissivel": forca_axial_admissivel,
        "taxa_trabalho": taxa_trabalho,
        "esbeltez_corrigida": esbeltez_corrigida,
        "tensao_fy_corrigida": tensao_fy_corrigida,
        "Fa": tensao_adm_compressao,
        "Fa_reduzido": tensao_adm_reduzida,
        "ft_admissivel": ft_admissivel,
        "esbeltez_tracao": esbeltez_tracao,
    }

def verificar_axial_flexao(
    perfil: pd.Series,
    forca: float,
    descontos_area_liquida: dict[str, float],
    coef_minoracao: float,
    *,
    tipo_barra: str | None = "montante",      # valor default só para exemplo
    comprimento: float | None = None,
    angulo_graus: float = 0.0,
    df_materiais: pd.DataFrame,
    diametros_furos: dict[str, float] | None = None,
) -> float:
    """
    Verifica se o perfil atende simultaneamente aos critérios normativos de
    resistência axial (compressão/tração) e resistência à flexão simples.

    Essa função é usada principalmente para barras do tipo "montante", e retorna
    a **maior** entre as duas taxas de trabalho envolvidas:
    - `tx_axial`: taxa de trabalho obtida a partir da verificação axial conforme
      critérios normativos (compressão ou tração).
    - `tx_flex`: taxa fictícia (999.0) caso a barra reprove à flexão simples,
      ou zero caso a flexão seja aprovada.

    A maior entre essas duas é usada como critério final de aprovação do perfil
    quando se deseja que a barra atenda **ambas as verificações**.

    Args:
        perfil (pd.Series): Linha da tabela de perfis, contendo os campos como
            "A(cm2)", "Wx(cm3)", "t(cm)", etc.
        forca (float): Esforço axial na barra (positivo = tração, negativo = compressão).
        descontos_area_liquida (dict[str, float]): Fatores de desconto aplicados à área
            líquida da seção conforme o tipo da barra.
        coef_minoracao (float): Coeficiente de minoração das resistências normativas.
        tipo_barra (str, optional): Tipo da barra ("montante", "diagonal", etc.).
            Default é "montante".
        comprimento (float, optional): Comprimento efetivo da barra, necessário para
            o cálculo de esbeltez e flexão. Obrigatório.
        angulo_graus (float, optional): Inclinação da barra em graus. Default = 0.0.
        df_materiais (pd.DataFrame): Tabela de propriedades dos aços disponíveis.
        diametros_furos (dict[str, float], optional): Dicionário com os diâmetros
            dos furos por tipo de barra. Se omitido, assume 1.59 cm para montantes.

    Returns:
        float: A maior taxa de trabalho entre axial e flexão.
            - Valor ≤ 1.0 indica que o perfil atende aos critérios normativos.
            - Valor > 1.0 indica reprovação em pelo menos um dos critérios.

    Raises:
        ValueError: Se `comprimento` não for fornecido.

    Notes:
        - A verificação axial considera sempre o modo mais crítico (força de compressão).
        - A verificação de flexão é feita com carga concentrada de 100 kgf no meio do vão,
          como exigido para barras com inclinação ≤ 45°.
    """
    if comprimento is None:
        raise ValueError("Comprimento obrigatório para verificação normativa")

    diam_furo = 1.59 if diametros_furos is None else diametros_furos.get("montante", 1.59)

    ver_axial = calcula_tensao_axial_admissivel(
        df_materiais=df_materiais,
        dados_perfil=perfil,
        forca_axial=forca,
        tipo_barra=tipo_barra,
        comprimento_efetivo=comprimento,
        coef_minoracao=coef_minoracao,
        diametro_furo=diam_furo,
        limitar_esbeltez_tracao=False,
        forcar_verificacao_compressao=True,
        descontos_area_liquida=descontos_area_liquida,
    )
    tx_axial = ver_axial["taxa_trabalho"]

    flex_ok = verifica_flexao_simples(
        tipo_barra=tipo_barra,
        angulo_graus=angulo_graus,
        comprimento=comprimento,
        modulo_resistencia_flexao_x=perfil.get("Wx(cm3)", 0.0),
        tensao_fy=obter_fy(perfil, df_materiais),
        coef_minoracao=coef_minoracao,
    )
    tx_flex = 0.0 if flex_ok else 999.0

    return max(tx_axial, tx_flex)
