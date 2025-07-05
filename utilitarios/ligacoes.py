import math

from typing import cast

import pandas as pd

from utilitarios.constantes import COEF_MINORACAO_PADRAO
from utilitarios.ferramentas_montantes import (
    expandir_ligacoes_montantes_simetricos,
    igualar_perfis_montantes_por_modulo,
)
from utilitarios.io_excel import obter_fu


def dimensionar_ligacao(
    forca_axial: float,
    tipo_barra: str,
    perfil_nome: str,
    espessura_aba: float,
    diametros_furos: dict[str, float],
    fv_parafuso: float,
    fu_peca: float,
    limite_parafusos: dict[str, int],
    planos_cisalhamento: dict[str, int],
    fatores_esmagamento: list[float],
    df_perfis: pd.DataFrame,
    coef_minoracao: float = COEF_MINORACAO_PADRAO,
) -> dict:
    """
    Dimensiona a ligação metálica de uma barra quanto ao cisalhamento e ao esmagamento,
    aplicando o coeficiente de minoração (phi). Avalia combinações possíveis de número
    de parafusos e fatores de esmagamento, retornando o primeiro caso que atende.

    Args:
        forca_axial (float): Esforço axial na barra (positivo ou negativo).
        tipo_barra (str): Tipo da barra ('montante', 'diagonal', 'horizontal').
        perfil_nome (str): Nome do perfil adotado (ex: 'L 75x75x5').
        espessura_aba (float): Espessura da aba do perfil, em cm.
        diametros_furos (dict[str, float]): Diâmetros dos furos por tipo de barra.
        fv_parafuso (float): Tensão admissível ao cisalhamento do parafuso (kgf/cm²).
        fu_peca (float): Tensão última do material da peça ligada (kgf/cm²).
        limite_parafusos (dict[str, int]): Máximo de parafusos permitidos por tipo.
        planos_cisalhamento (dict[str, int]): Número de planos de cisalhamento por tipo.
        fatores_esmagamento (list[float]): Fatores normativos para o cálculo da força admissível ao esmagamento (fator_fp).
        df_perfis (pd.DataFrame): Tabela de perfis para consulta de dados.
        coef_minoracao (float, optional): Coeficiente de minoração phi. Padrão 0.9.

    Returns:
        dict: Dicionário com os resultados da ligação (viabilidade, np, capacidades, taxas, etc).
    """

    tipo_base = (
        "montante"
        if "montante" in tipo_barra
        else "diagonal" if "diagonal" in tipo_barra else "horizontal"
    )

    d_furo = diametros_furos.get(tipo_base, 1.59)
    area_parafuso = math.pi * (d_furo / 2) ** 2  # área do parafuso em cm²
    np_max = limite_parafusos[tipo_base]
    num_planos_cisalhamento = planos_cisalhamento[tipo_base]

    # Determina número mínimo de parafusos para montantes
    if tipo_base == "montante":
        np_min = 4  # valor padrão definido fora do try
        try:
            match = df_perfis[df_perfis["Perfil"].str.strip() == perfil_nome.strip()]
            if match.empty:
                raise ValueError(f"Perfil '{perfil_nome}' não encontrado na tabela de perfis.")
            dados_perfil = match.iloc[0]
            np_min = int(round(dados_perfil["Np mín"]))
        except (IndexError, KeyError, ValueError):
            pass  # já está com valor padrão
    else:
        np_min = 1  # diagonais e horizontais

    for np in range(np_min, np_max + 1):
        if tipo_base == "montante" and np % 2 != 0:
            continue  # montantes só aceitam número par de parafusos

        # Verificação ao cisalhamento
        forca_adm_cisalhamento = (
            coef_minoracao * np * area_parafuso * fv_parafuso * num_planos_cisalhamento
        )
        if abs(forca_axial) > forca_adm_cisalhamento:
            continue  # não atende ao cisalhamento

        # Verificação ao esmagamento
        for fator_fp in fatores_esmagamento:
            tensao_adm_esmagamento = float(
                coef_minoracao * fator_fp * fu_peca
            )  # tensão admissível ao esmagamento
            area_contato = np * d_furo * espessura_aba
            tensao_solicitante_esmagamento = (
                abs(forca_axial) / area_contato
            )  # tensão solicitante ao esmagamento
            forca_adm_esmagamento = (
                tensao_adm_esmagamento * area_contato
            )  # força admissível ao esmagamento

            # Comparação feita por tensão; força admissível só é calculada após confirmação
            if float(tensao_solicitante_esmagamento) <= float(tensao_adm_esmagamento):
                tx_cisalhamento = abs(forca_axial) / forca_adm_cisalhamento
                tx_esmagamento = tensao_solicitante_esmagamento / tensao_adm_esmagamento
                tx_ligacao = max(tx_cisalhamento, tx_esmagamento)

                if tx_ligacao <= 1.0:
                    return {
                        "ligacao_viavel": True,
                        "np": np,
                        "forca_adm_cisalhamento": forca_adm_cisalhamento,
                        "forca_adm_esmagamento": forca_adm_esmagamento,
                        "tx_lig": tx_ligacao,
                        "d_furo": d_furo,
                        "area_parafuso": area_parafuso,
                        "fator_fp": fator_fp,
                        "planos": num_planos_cisalhamento,
                        "coef_minoracao": coef_minoracao,
                    }

    # Se nenhum caso for viável
    return {
        "ligacao_viavel": False,
        "np": None,
        "forca_adm_cisalhamento": 0.0,
        "forca_adm_esmagamento": 0.0,
        "tx_lig": 999.0,
        "d_furo": d_furo,
        "area_parafuso": area_parafuso,
        "fator_fp": None,
        "planos": num_planos_cisalhamento,
        "coef_minoracao": coef_minoracao,
    }


def ajustar_perfis_montantes_por_ligacao(
    metadados: dict,
    esforcos_por_hipotese: dict[str, dict[str, float]],
    df_perfis: pd.DataFrame,
    df_materiais: pd.DataFrame,
    diametros_furos: dict[str, float],
    limite_parafusos: dict[str, int],
    planos_cisalhamento: dict[str, int],
    fatores_esmagamento: list[float],
    coef_minoracao: float = COEF_MINORACAO_PADRAO,
    max_iter: int = 5,
    descontos_area_liquida: dict[str, int] | None = None,
) -> dict[str, dict]:
    """
    Ajusta os perfis dos montantes cuja ligação metálica não atende aos critérios normativos,
    substituindo por um novo perfil com área e espessura maiores, caso necessário.
    Após cada ajuste, aplica novamente a simetrização dos montantes por módulo.

    Args:
        metadados (dict): Dicionário de metadados por barra, incluindo perfil adotado.
        esforcos_por_hipotese (dict): Esforços axiais por barra e por hipótese.
        df_perfis (pd.DataFrame): Tabela combinada de perfis.
        df_materiais (pd.DataFrame): Tabela de propriedades dos materiais.
        diametros_furos (dict): Diâmetros de furação por tipo de barra.
        limite_parafusos (dict): Máximo de parafusos por tipo de barra.
        planos_cisalhamento (dict): Número de planos de cisalhamento por tipo.
        fatores_esmagamento (list): Fatores de correção da tensão de esmagamento.
        coef_minoracao (float, optional): Coeficiente de minoração phi. Default = 0.9.
        max_iter (int, optional): Número máximo de iterações. Default = 5.
        descontos_area_liquida (dict, optional): Qtd. de furos por tipo de barra para tração.

    Returns:
        dict: Dicionário com os dados das ligações finais (incluindo simétricos).
    """
    for i in range(max_iter):
        ligacoes_forcadas = otimizar_ligacoes_montantes_extremidades(
            metadados,
            esforcos_por_hipotese,
            df_materiais,
            diametros_furos,
            limite_parafusos,
            planos_cisalhamento,
            fatores_esmagamento,
            df_perfis,
            coef_minoracao=coef_minoracao,
        )

        trocou_algum_perfil = False

        for id_barra, ligacao in ligacoes_forcadas.items():
            if ligacao["ligacao_viavel"]:
                continue

            perfil_atual = metadados[id_barra]["perfil_escolhido"]
            if perfil_atual == "NENHUM":
                continue

            linha_atual = df_perfis[df_perfis["Perfil"] == perfil_atual].iloc[0]
            espessura_atual = linha_atual["t(cm)"]
            area_atual = linha_atual["A(cm2)"]
            area_parafuso = ligacao.get("area_parafuso", 0.2)  # valor default para segurança
            fu = obter_fu(linha_atual, df_materiais)

            df_candidatos = df_perfis[
                (df_perfis["A(cm2)"] >= area_atual)
                & (df_perfis["t(cm)"] >= espessura_atual + 0.001)
            ]

            if df_candidatos.empty:
                continue

            linha_nova = df_candidatos.sort_values(by="Peso(kg/m)").iloc[0]
            novo_perfil = linha_nova["Perfil"]

            if novo_perfil != perfil_atual:
                metadados[id_barra]["perfil_escolhido"] = novo_perfil
                trocou_algum_perfil = True

        if not trocou_algum_perfil:
            break

        igualar_perfis_montantes_por_modulo(
            metadados,
            df_montantes=df_perfis,
            df_materiais=df_materiais,
            coef_minoracao=coef_minoracao,
            diametros_furos=diametros_furos,
            descontos_area_liquida=descontos_area_liquida,  # ← NOVO
        )

    # Aplica simetria final às ligações
    ligacoes_completas = {}
    for id_barra_base, lig in ligacoes_forcadas.items():
        simetricos = expandir_ligacoes_montantes_simetricos(
            metadados, {id_barra_base}, tolerancia=1e-3
        )
        for id_barra in simetricos:
            ligacoes_completas[id_barra] = lig

    return ligacoes_completas


def otimizar_ligacoes_montantes_extremidades(
    metadados: dict[str, dict],
    esforcos_por_hipotese: dict[str, dict[str, float]],
    df_materiais: pd.DataFrame,
    diametros_furos: dict[str, float],
    limite_parafusos: dict[str, int],
    planos_cisalhamento: dict[str, int],
    fatores_esmagamento: list[float],
    df_perfis: pd.DataFrame,
    coef_minoracao: float = COEF_MINORACAO_PADRAO,
) -> dict[str, dict]:
    """
    Calcula a ligação metálica otimizada para cada extremidade de módulo (base ou topo),
    considerando os montantes mais solicitados (em tração e compressão) daquele grupo.

    Os grupos de extremidade são definidos a partir das marcações:
    - 'base_modulo': montantes localizados na base do módulo;
    - 'topo_modulo': montantes localizados no topo do módulo;
    - 'topo_estrutura': montantes no topo final da torre.

    Essas marcações devem estar previamente atribuídas no metadado por meio da função
    `marcar_montantes_em_extremidades(...)`.

    A ligação mais resistente entre os candidatos (maior Fc e Fe) é adotada como referência
    e aplicada a todos os montantes do grupo correspondente (mesmo módulo e nível).

    Se nenhum dos montantes do grupo apresentar ligação viável (ou seja, se todas as tentativas
    resultarem em 'np = None'), todas as barras do grupo são marcadas com
    {'ligacao_viavel': False}. Isso permite que o dimensionamento reconheça a configuração como
    inviável sem interromper a execução — funcionalidade necessária para integração com o otimizador.

    Args:
        metadados (dict[str, dict]): Metadados das barras, incluindo tipo, módulo, y_min, y_max e marcações de posição.
        esforcos_por_hipotese (dict[str, dict[str, float]]): Esforços axiais por hipótese e por barra.
        df_materiais (pd.DataFrame): Tabela de propriedades dos materiais (fu, fc, etc.).
        diametros_furos (dict[str, float]): Diâmetro dos furos por tipo de barra.
        limite_parafusos (dict[str, int]): Número máximo de parafusos por tipo de barra.
        planos_cisalhamento (dict[str, int]): Número de planos de cisalhamento por tipo de barra.
        fatores_esmagamento (list[float]): Lista de fatores multiplicativos normativos para esmagamento.
        df_perfis (pd.DataFrame): Tabela de perfis com propriedades geométricas.
        coef_minoracao (float): Coeficiente de minoração da resistência (phi). Padrão 0.9.

    Returns:
        dict[str, dict]: Dicionário onde cada chave é o ID de uma barra com ligação forçada,
        e o valor é um dicionário com os dados da ligação dimensionada (np, d_furo, Fc, Fe, etc.).
    """

    ligacoes_forcadas = {}
    esforcos_por_barra = {}

    for nome_hipotese, barras in esforcos_por_hipotese.items():
        for id_barra, esforco in barras.items():
            esforcos_por_barra.setdefault(id_barra, []).append(esforco)

    # Agrupar montantes por módulo e posição vertical (base/topo)
    grupos_por_modulo = {}
    for id_barra, dados in metadados.items():
        if not isinstance(dados, dict):
            continue
        if "tipo" not in dados or not dados["tipo"].startswith("montante"):
            continue

        modulo = dados.get("modulo")
        y_min = dados.get("y_min")
        y_max = dados.get("y_max")
        if modulo is None or y_min is None or y_max is None:
            continue

        # Apenas adiciona à base se marcado como base de módulo
        if dados.get("base_modulo"):
            grupos_por_modulo.setdefault((modulo, "base", y_min), []).append(id_barra)

        # Apenas adiciona ao topo se marcado como topo de módulo ou topo da estrutura
        if dados.get("topo_modulo") or dados.get("topo_estrutura"):
            grupos_por_modulo.setdefault((modulo, "topo", y_max), []).append(id_barra)

    for (modulo, posicao, nivel_y), ids_barra in grupos_por_modulo.items():
        # Identifica os montantes mais tracionado e mais comprimido
        melhor_tracao = None
        melhor_compressao = None
        tracao_maxima = -float("inf")
        compressao_maxima = float("inf")

        for id_barra in ids_barra:
            lista_esforco_axial = esforcos_por_barra.get(id_barra, [])
            esforco_axial_maximo = max(lista_esforco_axial) if lista_esforco_axial else 0
            esforco_axial_minimo = min(lista_esforco_axial) if lista_esforco_axial else 0

            if esforco_axial_maximo > tracao_maxima:
                tracao_maxima = esforco_axial_maximo
                melhor_tracao = id_barra
            if esforco_axial_minimo < compressao_maxima:
                compressao_maxima = esforco_axial_minimo
                melhor_compressao = id_barra

        # Seleciona os candidatos à ligação
        candidatos = set()
        if melhor_tracao:
            candidatos.add(melhor_tracao)
        if melhor_compressao:
            candidatos.add(melhor_compressao)

        ligacoes_candidatas = {}

        # Dimensiona ligação para cada candidato
        for id_barra in candidatos:
            tipo = metadados[id_barra]["tipo"]
            perfil_nome = metadados[id_barra].get("perfil_escolhido")
            if perfil_nome is None or perfil_nome == "NENHUM":
                continue

            linha = df_perfis[df_perfis["Perfil"].str.strip() == perfil_nome.strip()]
            if linha.empty:
                continue

            linha = linha.iloc[0]
            espessura_aba = float(linha["t(cm)"])
            forca_axial_critica: float = cast(
                float,
                max(esforcos_por_barra[id_barra], key=abs)
            )

            verif = dimensionar_ligacao(
                forca_axial=forca_axial_critica,
                tipo_barra=tipo,
                perfil_nome=perfil_nome,
                espessura_aba=espessura_aba,
                diametros_furos=diametros_furos,
                fv_parafuso=df_materiais.loc["A394", "fc (kgf/cm²)"],
                fu_peca=obter_fu(linha, df_materiais),
                limite_parafusos=limite_parafusos,
                planos_cisalhamento=planos_cisalhamento,
                fatores_esmagamento=fatores_esmagamento,
                df_perfis=df_perfis,
                coef_minoracao=coef_minoracao,
            )
            ligacoes_candidatas[id_barra] = verif

        if not ligacoes_candidatas:
            continue

        # Escolhe a mais resistente (maior Fc e Fe)
        def criterio_resistencia(lig):
            return (lig["forca_adm_cisalhamento"], lig["forca_adm_esmagamento"])

        melhor_ligacao = max(ligacoes_candidatas.values(), key=criterio_resistencia)

        # Se todos os candidatos à ligação resultaram em np=None, a ligação é considerada inviável.
        # Esse caso é tratado explicitamente para evitar falhas no otimizador e garantir que
        # toda a extremidade do módulo seja marcada como indisponível para essa configuração.
        if not melhor_ligacao or melhor_ligacao.get("np") is None:
            for id_barra in ids_barra:
                ligacoes_forcadas[id_barra] = {"ligacao_viavel": False, "np": None}
            continue  # vai para o próximo grupo de montantes

        # Verifica se a melhor ligação atende a todos os candidatos
        for id_barra in candidatos:
            forca_axial_critica = max(esforcos_por_barra[id_barra], key=abs)
            tipo = metadados[id_barra]["tipo"]
            espessura_aba = float(metadados[id_barra].get("t", 0.0))

            while True:
                forca_adm_cisalhamento = melhor_ligacao["forca_adm_cisalhamento"]
                forca_adm_esmagamento = melhor_ligacao["forca_adm_esmagamento"]

                if (
                    abs(forca_axial_critica) <= forca_adm_cisalhamento
                    and abs(forca_axial_critica) <= forca_adm_esmagamento
                ):
                    break  # ligação atende

                # Se não atende, reforça
                # Se por alguma razão 'np' ainda vier None, encerra o reforço
                if melhor_ligacao.get("np") is None:
                    break
                novo_np = melhor_ligacao["np"] + (2 if tipo.startswith("montante") else 1)
                if "montante" in tipo:
                    tipo_base = "montante"
                elif "horizontal" in tipo:
                    tipo_base = "horizontal"
                else:
                    tipo_base = "diagonal"

                if novo_np > limite_parafusos[tipo_base]:
                    break  # atingiu o limite

                melhor_ligacao = dimensionar_ligacao(
                    forca_axial=forca_axial_critica,
                    tipo_barra=tipo,
                    perfil_nome=perfil_nome,
                    espessura_aba=espessura_aba,
                    diametros_furos=diametros_furos,
                    fv_parafuso=df_materiais.loc["A394", "fc (kgf/cm²)"],
                    fu_peca=obter_fu(linha, df_materiais),
                    limite_parafusos=limite_parafusos,
                    planos_cisalhamento=planos_cisalhamento,
                    fatores_esmagamento=fatores_esmagamento,
                    df_perfis=df_perfis,
                    coef_minoracao=coef_minoracao,
                )

        # Aplica a ligação final a todos os montantes daquele nível
        for id_barra in ids_barra:
            ligacoes_forcadas[id_barra] = melhor_ligacao

    return ligacoes_forcadas
