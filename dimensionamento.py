from copy import deepcopy
from typing import Optional

import pandas as pd
from anastruct import SystemElements

from utilitarios.analise_estrutural import executar_hipoteses_carregamento
from utilitarios.constantes import COEF_MINORACAO_PADRAO, LIMITE_TAXA_TRABALHO_DIAG_HORIZ, FATOR_ESMAGAMENTO_PADRAO
from utilitarios.ferramentas_montantes import (
    expandir_ligacoes_montantes_simetricos,
    identificar_montantes_com_ligacao,
    igualar_perfis_montantes_por_modulo,
    marcar_montantes_em_extremidades,
    reforcar_montante_ate_viavel
)
from utilitarios.geral import divisao_segura, ordenar_id_barra
from utilitarios.io_excel import (
    carregar_tabela_materiais,
    carregar_tabela_perfis,
    obter_fu,
    obter_fy,
    filtrar_por_diametro_parafuso
)
from utilitarios.ligacoes import (
    ajustar_perfis_montantes_por_ligacao,
    dimensionar_ligacao,
    otimizar_ligacoes_montantes_extremidades,
)
from utilitarios.peso import calcular_peso_por_modulo, calcular_peso_total
from utilitarios.verif_normativas import (
    calcula_tensao_axial_admissivel,
    calcular_esbeltez_corrigida,
    verifica_flexao_simples,
    verificar_axial_flexao,
)

from utilitarios.wrappers import wrapper_ligacao_montante

def dimensionar_barras(
    esforcos_por_hipotese: dict[str, dict[str, float]],
    estruturas_por_hipotese: dict[str, SystemElements],
    df_montantes: pd.DataFrame,
    df_diagonais_horizontais: pd.DataFrame,
    df_materiais: pd.DataFrame,
    df_perfis: pd.DataFrame,
    coef_minoracao: float = COEF_MINORACAO_PADRAO,
    diametros_furos: dict[str, float] | None = None,
    descontos_area_liquida: dict[str, int] | None = None,
    limite_parafusos: dict[str, int] | None = None,
    planos_cisalhamento: dict[str, int] | None = None,
    fatores_esmagamento: list[float] | None = None,
    interromper_se_inviavel: bool = True,
) -> tuple[
    Optional[dict[str, dict[str, any]]], Optional[dict[str, dict[str, any]]], Optional[set[str]],]:
    """
    Dimensiona **todas** as barras de uma treliça submetida a diversas hipóteses de
    carregamento, contemplando:

    * resistência axial (tração e compressão) com limites de esbeltez distintos;
    * verificação de flexão simples para barras com |α| ≤ 45 °;
    * verificação do limite absoluto de flambagem local (w/t ≤ 25 conforme ASCE 10-15);
    * compatibilidade com ligações metálicas parafusadas (cisalhamento e esmagamento);
    * simetria e unificação de perfis nos montantes de cada módulo;
    * reforço iterativo do perfil quando a ligação reprova, até convergência.

    O algoritmo é dividido em nove etapas principais:

    1. **Preparação dos dados**
       Coleta os metadados de cada barra a partir das estruturas resolvidas (`SystemElements`),
       classificando o tipo de solicitação (tração ou compressão) e registrando os comprimentos
       (real e destravado).
       Em seguida, os montantes são classificados como **base de módulo**, **topo de módulo** ou
       **topo da estrutura**, com base em sua posição vertical relativa dentro de cada módulo.
       Essa marcação é usada como critério unificado para determinar **quais montantes exigem
       verificação de ligação metálica nas extremidades da torre**.
       As barras marcadas são replicadas para seus montantes simétricos.

    2. **Pré-processamento por barra: tração exclusiva e hipóteses críticas**
       Identifica quais barras estão exclusivamente tracionadas em todas as hipóteses,
       permitindo um critério de esbeltez mais permissivo para essas barras.
       Em seguida, para cada barra, elege-se a hipótese que gera a **maior tração** e a que
       gera a **maior compressão**. Se alguma delas estiver ausente, o algoritmo
       introduz uma hipótese simulada (`hip_0_t` ou `hip_0_c`) com esforço fictício de
       ±0,01 kgf para viabilizar os cálculos e garantir a consistência da saída.

    3. **Varredura de perfis (pré-cheque)**
        Para cada hipótese crítica, o algoritmo executa:

    - Avaliação de todos os perfis disponíveis, filtrados de acordo com o tipo de barra:
          - Para montantes, são excluídos perfis com nota “Não utilizar em montante! (Flambagem Local)”;
          - Todos os perfis devem possuir valor de “D máx” maior ou igual ao diâmetro de parafuso exigido para a barra
        (ou serão descartados).
        - Aplicação sequencial dos seguintes critérios:
          - Resistência axial combinada com limites de esbeltez.
          - Verificação de flexão simples (aplicável quando |α| ≤ 45°).
          - **Ligações mínimas individuais** (*aplicável apenas para diagonais e horizontais*): para cada perfil,
            percorre-se todos os pares possíveis de `(np, fp)` dentro dos limites definidos por `limite_parafusos`
            e `fatores_esmagamento`, buscando o primeiro arranjo que satisfaça **ambos** os critérios:
            `F ≤ Fc` (cisalhamento) **e** `F ≤ Fe` (esmagamento).
            - Se o **cisalhamento** continuar limitante **mesmo com** `np = np_max`, o perfil é **rejeitado** (aumentar a espessura não resolve).
            - Se o **esmagamento** for limitante, testa-se `fp` até 1,25 antes de descartar.
          - Limitação da taxa de trabalho a no máximo 90% para diagonais e horizontais.
        - Seleção do perfil leve mais viável para cada barra; caso nenhum atenda, registra-se como "NENHUM".

    4. **Escolha do perfil da barra**
       Quando as duas hipóteses resultam no mesmo perfil viável, ele é adotado.
       Se resultam em perfis distintos, opta-se por aquele que:

       * apresentar a **maior taxa de trabalho** (critério de eficiência); ou
       * possuir a **maior área bruta** em caso de empate na taxa.

    5. **Rechecagem completa com o perfil final**
       Reexecuta os cálculos axiais, de flexão e da ligação mínima para ambas as
       hipóteses, agora utilizando o perfil final.
       Registra‐se, para cada barra, a hipótese que produz a maior
       `tx_lig` → `pior_ligacao`.

    6. **Dimensionamento das ligações definitivas (montantes)**
       Para cada extremidade de módulo são avaliadas combinações de parâmetros
       (nº de parafusos, diâmetro, planos de cisalhamento, fator de esmagamento)
       até encontrar **um único arranjo viável** que atenda simultaneamente ao par de
       montantes na extremidade.
       Se nenhuma ligação viável for encontrada, o processo é interrompido (ou retorna
       `None`, conforme o parâmetro `interromper_se_inviavel`).
       O detalhamento ótimo obtido é propagado aos montantes simétricos.

       * Atenção: esse processo de abortar o dimensionamento em caso de ligação
         inviável é exclusivo dos montantes, que exigem simetria e verificação
         conjunta nas extremidades dos módulos. Diagonais e horizontais são
         dimensionadas individualmente; se nenhuma ligação viável for possível
         com o perfil atual, a barra é apenas marcada como "NENHUM" e o processo
         segue normalmente para as demais.

    7. **Uniformização e reforço dos perfis dos montantes**

       Inicialmente, todos os montantes de um mesmo módulo recebem o **maior perfil**
       entre eles após o dimensionamento preliminar. Essa igualação intramódulo
       garante simetria estrutural e compatibilidade entre montantes de mesma altura.

       Em seguida, o algoritmo verifica as **ligações nas extremidades** dos módulos
       (base e topo, à esquerda e à direita). Caso alguma ligação reprove com o perfil atual,
       o algoritmo tenta reforçar iterativamente os perfis dos montantes críticos,
       sempre adotando o **menor perfil superior disponível** que satisfaça a ligação
       e os critérios normativos.

       Durante esse processo, a ligação mais exigente (entre tração e compressão)
       é identificada e registrada como a **pior ligação** da barra, para fins de relatório.

       Após a convergência (ou ao fim das 10 tentativas), uma nova **igualação dos perfis**
       é realizada para garantir a uniformidade intramódulo após o reforço.

       Finalmente, todas as ligações das extremidades são **recalculadas** com os perfis finais,
       garantindo que os dados exibidos reflitam corretamente o perfil adotado.

       Se, ao final do processo, alguma ligação ainda estiver inviável, o algoritmo
       interrompe (ou retorna None, conforme o parâmetro `interromper_se_inviavel`).

       Durante o reforço dos montantes, são considerados apenas os perfis previamente filtrados por:

        - Compatibilidade com o diâmetro de parafuso (`D máx`), e

        - viabilidade prática de uso como montante, com base na coluna "Notas" da tabela de perfis:
          excluem-se perfis marcados como “Não utilizar em montante!”, por estarem sujeitos à flambagem
          local significativa, cuja verificação normativa exigiria redução da tensão de escoamento (Fy).
          Essa restrição é adotada por critério de projeto prático, evitando o uso de perfis que, embora
          matematicamente viáveis, apresentariam desempenho estrutural inferior ou pouco eficiente.


    8. **Cálculo das taxas finais para exibição**
       Determina-se, por barra:

       * `taxa_trabalho_final` → maior entre Nₜ/Fₐ,ₜ e N𝚌/Fₐ,𝚌
       * `tx_lig_final`         → maior entre N/Fc (cisalhamento) e N/Fe (esmagamento)

       Esses valores somente alimentam a impressão da tabela de resultados.

    9. **Saída consolidada**
       A função devolve:

       * **resultado_final** — dicionário por barra, contendo:
         perfil adotado, hipótese crítica axial, hipótese crítica de ligação,
         taxas finais, metadados de comprimento, ângulo, módulo, etc.

       * **ligacoes_forcadas** — detalhamento final das ligações realmente
         executadas (após igualação/otimização).

       * **ids_ligacao_necessaria** — conjunto com os IDs das barras
         efetivamente ligadas (útil para formatação de relatórios).

    -------
    Args:
        esforcos_por_hipotese (dict[str, dict[str, float]]):
            Esforços axiais `N` (kgf) em cada barra para cada nome de hipótese
            (ex.: ``{"Fh(+)" : {"01": 500, "02": -300, ...}, "Fh(-)" : {...}}``).

        estruturas_por_hipotese (dict[str, SystemElements]):
            Objetos `anaStruct.SystemElements` já resolvidos, na mesma chave de
            `esforcos_por_hipotese`. São usados apenas para extrair metadados.

        df_montantes (pd.DataFrame):
            Tabela de perfis disponíveis para montantes (colunas mínimas:
            ``Perfil``, ``A(cm2)``, ``rx(cm)``, ``Wx(cm3)``, ``t(cm)``, ``Peso(kg/m)``).

        df_diagonais_horizontais (pd.DataFrame):
            Tabela análoga para diagonais e horizontais (raio mínimo = ``rz``).

        df_materiais (pd.DataFrame):
            Propriedades dos aços (``Fy``, ``Fu``, ``fc`` – parafuso).

        df_perfis (pd.DataFrame):
            União de todas as tabelas de perfis (montantes ∪ diagonais/horiz.).

        coef_minoracao (float, opcional):
            Coeficiente de minoração de resistência (γ), padrão = 0,9.

        diametros_furos (dict[str, float], opcional):
            Diâmetros de furo em centímetros por tipo de barra
            (``{"montante": 1.27, "diagonal": 1.59, ...}``).

        descontos_area_liquida (dict[str, int], opcional):
            Número de furos descontados no cálculo de área líquida na tração
            (permite sobrescrever o valor da planilha).

        limite_parafusos (dict[str, int], opcional):
            Quantidade máxima de parafusos por barra (por tipo).

        planos_cisalhamento (dict[str, int], opcional):
            N.º de planos de cisalhamento considerados por tipo de barra.

        fatores_esmagamento (list[float], opcional):
            Sequência de fatores multiplicativos (`f_p`) a testar no cálculo de
            esmagamento (ex.: ``[1.0833, 1.25]``).

        interromper_se_inviavel (bool, opcional):
            Se ``True`` (padrão), lança ``ValueError`` caso alguma barra não
            encontre perfil viável; caso contrário retorna ``None`` nos três
            resultados.

    Returns:
        tuple[Optional[dict[str, dict[str, any]]], Optional[dict[str, dict[str, any]]], Optional[set[str]]]:
        ``(resultado_final, ligacoes_forcadas, ids_ligacao_necessaria)``

            Uma tupla contendo:

            - **resultado_final**: Dicionário com os dados finais de dimensionamento por barra, contendo o perfil adotado, verificações por hipótese, taxas finais, entre outros.

            - **ligacoes_forcadas**: Dicionário com os parâmetros detalhados das ligações adotadas para os montantes nas extremidades da torre.

            - **ids_ligacao_necessaria**: Conjunto com os IDs das barras que exigem ligação metálica, geralmente nos topos e bases dos módulos.

            Os três elementos podem ser `None` caso `interromper_se_inviavel=False` e alguma barra resulte inviável.

    Raises:
        ValueError: Se `interromper_se_inviavel=True` e ao menos uma barra ficar
        sem perfil viável após a varredura completa.

    Nota:
        * O algoritmo **não** tenta perfis maiores quando o cisalhamento é o
          limitante mesmo com `np = np_max` — isso evita iterações inúteis com
          aumento de espessura que não resolvem o problema.
        * Caso não seja possível dimensionar a ligação de algum montante mesmo após
          igualação e reforço, a função é interrompida (ou retorna `None`, conforme
          `interromper_se_inviavel`).
        * O resultado é totalmente independente de efeitos de peso‐próprio; caso o
          Otimizador esteja em modo iterativo, ele deve **reexecutar** esta função
          após atualizar as cargas verticais, garantindo consistência de esforços,
          perfis e ligações a cada ciclo.
        * Perfis com restrições normativas ou incompatíveis com o diâmetro de parafuso
          exigido são automaticamente excluídos da seleção de perfil, tanto no
          dimensionamento inicial quanto no reforço dos montantes.

    """

    # === 1. Inicialização dos parâmetros e coleta de metadados ===
    # Define parâmetros padrão e extrai os metadados necessários a partir das estruturas resolvidas
    # para cada hipótese de carregamento. Também classifica o tipo de solicitação (tração/compressão)
    # e marca as extremidades relevantes dos montantes (base de módulo, topo de módulo, topo da estrutura).

    # Define os diâmetros de furo padrão (em cm), caso não tenham sido fornecidos
    if diametros_furos is None:
        diametros_furos = {"montante": 1.59, "diagonal": 1.59, "horizontal": 1.59}

    # Inicializa os dicionários para tipos de solicitação e metadados estruturais
    tipos_por_barra: dict[str, set[str]] = {}
    metadados_barras: dict[str, dict[str, any]] = {}

    # Percorre as hipóteses e acumula tipos de solicitação por barra
    for nome_hipotese, barras_dict in esforcos_por_hipotese.items():
        estrutura = estruturas_por_hipotese[nome_hipotese]
        for id_barra, forca_axial in barras_dict.items():
            solicitacao = "tracao" if forca_axial > 0 else "compressao"
            tipos_por_barra.setdefault(id_barra, set()).add(solicitacao)

            # Extrai os metadados estruturais da barra (coordenadas, tipo, ângulo, etc.)
            if id_barra not in metadados_barras:
                metadados_barras[id_barra] = estrutura.barras_para_dimensionar[id_barra]

    # Marca quais montantes estão nas extremidades (usado para identificar pontos de ligação)
    marcar_montantes_em_extremidades(metadados_barras)

    # Identifica os montantes que exigem ligação metálica (base de módulo ou topo da torre)
    # (montantes em topo de estrutura/base de módulo)
    ids_ligacao_necessaria = identificar_montantes_com_ligacao(
        metadados_barras, esforcos_por_hipotese
    )

    # Adiciona os montantes simétricos à verificação de ligação
    ids_ligacao_necessaria = expandir_ligacoes_montantes_simetricos(
        metadados_barras, ids_ligacao_necessaria, tolerancia=1e-3
    )

    # === 2. Pré-processamento por barra: identificação de tração exclusiva e hipóteses críticas ===

    # Identifica as barras que estão exclusivamente em tração
    barras_exclusivamente_tracionadas = {
        id_barra for id_barra, solicitacoes in tipos_por_barra.items() if solicitacoes == {"tracao"}
    }

    # Para cada barra, seleciona as hipóteses com pior tração e pior compressão, simulando se necessário
    resultado_final = {}

    for id_barra, solicitacoes in tipos_por_barra.items():
        dados_barra = metadados_barras[id_barra]

        # Extrai os esforços de todas as hipóteses para esta barra
        esforcos_barra = {
            hip: barras.get(id_barra)
            for hip, barras in esforcos_por_hipotese.items()
            if id_barra in barras
        }

        # Simulação antecipada de hipóteses faltantes
        forca_axial_simulada_minima = 0.01

        esforcos_barra = {
            hip: barras.get(id_barra)
            for hip, barras in esforcos_por_hipotese.items()
            if id_barra in barras
        }

        hipotese_critica_tracao = max(
            (hip for hip in esforcos_barra if esforcos_barra[hip] > 0),
            key=lambda h: esforcos_barra[h],
            default=None,
        )

        hipotese_critica_compressao = min(
            (hip for hip in esforcos_barra if esforcos_barra[hip] < 0),
            key=lambda h: esforcos_barra[h],
            default=None,
        )

        # Simula a hipótese ausente, se necessário
        if not hipotese_critica_tracao:
            esforcos_barra["hip_0_t"] = +forca_axial_simulada_minima
            esforcos_por_hipotese.setdefault("hip_0_t", {})[id_barra] = +forca_axial_simulada_minima
            hipotese_critica_tracao = "hip_0_t"

        if not hipotese_critica_compressao:
            esforcos_barra["hip_0_c"] = -forca_axial_simulada_minima
            esforcos_por_hipotese.setdefault("hip_0_c", {})[id_barra] = -forca_axial_simulada_minima
            hipotese_critica_compressao = "hip_0_c"

        barra_tem_forca_simulada = "hip_0_t" in esforcos_barra or "hip_0_c" in esforcos_barra

        # Cria dicionário com apenas as hipóteses críticas
        esforcos_filtrados: dict[str, float] = {}
        if hipotese_critica_tracao:
            esforcos_filtrados[hipotese_critica_tracao] = esforcos_barra[hipotese_critica_tracao]
        if hipotese_critica_compressao:
            esforcos_filtrados[hipotese_critica_compressao] = esforcos_barra[hipotese_critica_compressao]

        comprimento_real = dados_barra.get("comprimento")
        tipo_barra = dados_barra.get("tipo")
        angulo = dados_barra.get("alfa_graus", 0)

        if tipo_barra.startswith("montante"):
            comprimento_destravado = dados_barra.get("comprimento_destravado", comprimento_real)
        else:
            comprimento_destravado = comprimento_real

        comprimento = comprimento_destravado

        # Define qual tabela de perfis usar
        df_perf = df_montantes if tipo_barra.startswith("montante") else df_diagonais_horizontais

        # Filtro por diâmetro de parafuso
        tipo_base = (
            "montante" if "montante" in tipo_barra
            else "diagonal" if "diagonal" in tipo_barra
            else "horizontal"
        )
        diametro_furo = diametros_furos.get(tipo_base, 1.59)

        df_perf = filtrar_por_diametro_parafuso(df_perf, diametro_furo)

        # Define limites de esbeltez conforme o caso da barra
        limitar_esbeltez_tracao = id_barra in barras_exclusivamente_tracionadas
        forcar_verificacao_compressao = not limitar_esbeltez_tracao

        # === 3. Dimensionamento ideal por hipótese e verificação de flexão, esbeltez, ligação e taxa ===

        melhores_por_hipotese: dict[str, dict[str, any]] = {}

        for nome_hipotese in esforcos_filtrados:
            forca_axial = esforcos_por_hipotese[nome_hipotese][id_barra]
            perfis_viaveis: list[dict[str, any]] = []

            for _, dados_perfil in df_perf.iterrows():
                # Determina tipo base (montante, diagonal ou horizontal)
                tipo_base = (
                    "montante"
                    if "montante" in tipo_barra
                    else "diagonal" if "diagonal" in tipo_barra else "horizontal"
                )

                # Define o diâmetro de furo a ser considerado
                diametro_furo = diametros_furos.get(tipo_base, 1.59)

                # Verificação do limite absoluto de flambagem local (ASCE 10-15)
                # Cálculo da relação w/t
                largura_aba = dados_perfil["b(cm)"]
                espessura_aba = dados_perfil["t(cm)"]
                raio_laminacao = dados_perfil["raio lam.(cm)"]

                largura_util = largura_aba - espessura_aba - raio_laminacao
                rel_w_t = largura_util / espessura_aba

                # Checagem do limite absoluto da norma
                if rel_w_t > 25:
                    continue  # Perfil reprovado por flambagem local (não permitido pela ASCE 10-15)

                # Verificação de resistência axial conforme norma (compressão ou tração)
                verificacao_axial = calcula_tensao_axial_admissivel(
                    df_materiais,
                    dados_perfil,
                    forca_axial,
                    tipo_barra,
                    comprimento,
                    coef_minoracao,
                    diametro_furo=diametro_furo,
                    limitar_esbeltez_tracao=limitar_esbeltez_tracao,
                    forcar_verificacao_compressao=forcar_verificacao_compressao,
                    descontos_area_liquida=descontos_area_liquida,  # ← AQUI!
                )

                if not verificacao_axial["viavel"]:
                    continue  # perfil reprovado por resistência axial

                # Verificação de flexão
                modulo_resistencia_flexao_x = dados_perfil.get("Wx(cm3)", 0.0)
                tensao_fy = obter_fy(dados_perfil, df_materiais)

                flexao_ok = verifica_flexao_simples(
                    tipo_barra=tipo_barra,
                    angulo_graus=angulo,
                    comprimento=comprimento,
                    modulo_resistencia_flexao_x=modulo_resistencia_flexao_x,
                    tensao_fy=tensao_fy,
                    coef_minoracao=coef_minoracao,
                )

                if not flexao_ok:
                    continue  # perfil rejeitado por não resistir à flexão

                # Verificação de ligação completa (usa np_max e fp até 1.25) para diagonais e horizontais

                if not tipo_barra.startswith("montante"):
                    verificacao_ligacao = dimensionar_ligacao(
                        forca_axial=forca_axial,
                        tipo_barra=tipo_barra,  # diagonal / horizontal
                        perfil_nome=dados_perfil["Perfil"],
                        espessura_aba=dados_perfil["t(cm)"],
                        diametros_furos=diametros_furos,
                        fv_parafuso=df_materiais.loc["A394", "fc (kgf/cm²)"],
                        fu_peca=obter_fu(dados_perfil, df_materiais),
                        limite_parafusos=limite_parafusos,
                        planos_cisalhamento=planos_cisalhamento,
                        fatores_esmagamento=fatores_esmagamento,
                        df_perfis=df_perfis,
                        coef_minoracao=coef_minoracao,
                    )

                    if (
                        verificacao_ligacao.get("forca_adm_cisalhamento", 0) == 0
                        or verificacao_ligacao.get("forca_adm_esmagamento", 0) == 0
                    ):
                        continue  # pula perfil com ligação impossível

                    forca_normal = abs(forca_axial)
                    forca_adm_cisalhamento = verificacao_ligacao.get("forca_adm_cisalhamento", 0)
                    forca_adm_esmagamento = verificacao_ligacao.get("forca_adm_esmagamento", 0)
                    tx_lig = max(
                        forca_normal / forca_adm_cisalhamento if forca_adm_cisalhamento else 999,
                        forca_normal / forca_adm_esmagamento if forca_adm_esmagamento else 999,
                    )

                    if tx_lig > 1.0:
                        continue  # → tenta o próximo perfil

                # Se barra for diagonal ou horizontal e taxa > 90%, rejeita
                if (
                    tipo_barra.startswith("diagonal") or tipo_barra.startswith("horizontal")
                ) and verificacao_axial["taxa_trabalho"] > LIMITE_TAXA_TRABALHO_DIAG_HORIZ:
                    continue  # perfil reprovado por alta taxa de trabalho

                # Se passou por todas as verificações, adiciona aos viáveis
                perfis_viaveis.append(
                    {
                        "perfil": dados_perfil["Perfil"],
                        "peso": dados_perfil["Peso(kg/m)"],
                        "area": dados_perfil["A(cm2)"],
                        "raio": (
                            dados_perfil["rx(cm)"]
                            if tipo_barra.startswith("montante")
                            else dados_perfil["rz(cm)"]
                        ),
                        "verificacao_axial": verificacao_axial,
                        "modulo_resistencia_flexao_x": dados_perfil.get("Wx(cm3)", 0.0),
                    }
                )

            # Armazena o melhor perfil encontrado, ou marca como inviável
            if not perfis_viaveis:
                melhores_por_hipotese[nome_hipotese] = {
                    "perfil_escolhido": "NENHUM",
                    "area_bruta": 0.0,
                    "viavel": False,
                    "forca_axial": forca_axial,
                    "tipo": tipo_barra,
                    "alfa": angulo,
                    "comprimento": comprimento,
                }
            else:
                melhor = min(perfis_viaveis, key=lambda x: x["peso"])
                melhores_por_hipotese[nome_hipotese] = {
                    **melhor["verificacao_axial"],
                    "verificacao_ligacao": (
                        verificacao_ligacao if not tipo_barra.startswith("montante") else {}
                    ),
                    "perfil_escolhido": melhor["perfil"],
                    "area_bruta": melhor["area"],
                    "viavel": True,
                    "forca_axial": forca_axial,
                    "tipo": tipo_barra,
                    "alfa": angulo,
                    "raio": melhor["raio"],
                    "modulo_resistencia_flexao_x": melhor["modulo_resistencia_flexao_x"],
                    "modulo": dados_barra.get("modulo"),
                    "comprimento": comprimento_real,
                    "comprimento_destravado": comprimento_destravado,
                }
            # Se nenhuma das hipóteses críticas encontrou perfil viável
            if all(d.get("perfil_escolhido") == "NENHUM" for d in melhores_por_hipotese.values()):
                if interromper_se_inviavel:
                    raise ValueError(f"Nenhum perfil viável para a barra {id_barra}")
                else:
                    # Se, ao final da varredura desta barra, nenhuma hipótese teve perfil viável
                    if not melhores_por_hipotese:
                        if interromper_se_inviavel:
                            raise ValueError(f"Nenhum perfil viável para a barra {id_barra}")
                        else:
                            # registra a barra como inviável para que seja capturada mais tarde
                            resultado_final[id_barra] = {"perfil_escolhido": "NENHUM"}
                            continue

        # === 4. Escolha do perfil final considerando o pior caso entre as hipóteses ===
        hipoteses_resultantes = list(melhores_por_hipotese.items())

        if len(hipoteses_resultantes) == 1:
            # Apenas uma hipótese considerada (ex: quando N = 0), adota-se diretamente
            hipotese_critica = hipoteses_resultantes[0][0]
        else:
            perf_hip0 = hipoteses_resultantes[0][1]["perfil_escolhido"]
            perf_hip1 = hipoteses_resultantes[1][1]["perfil_escolhido"]

            if perf_hip0 == perf_hip1:
                # perfis iguais → seleciona a hipótese com maior taxa de trabalho
                def area_trabalho(dados):
                    if dados["solicitacao"] == "compressao":
                        return abs(dados["forca_axial"]) / dados.get("Fa_reduzido", 1e-6)
                    elif dados["solicitacao"] == "tracao":
                        return abs(dados["forca_axial"]) / dados.get("ft_admissivel", 1e-6)
                    else:
                        return 0.0

                # Filtra apenas hipóteses com perfil viável
                hipoteses_viaveis = [
                    (nome, dados)
                    for nome, dados in melhores_por_hipotese.items()
                    if dados["perfil_escolhido"] != "NENHUM"
                ]
                if not hipoteses_viaveis:
                    continue  # nenhuma hipótese viável para essa barra

                hipotese_critica = max(hipoteses_viaveis, key=lambda kv: area_trabalho(kv[1]))[0]
            else:
                # perfis diferentes → escolhe aquele com maior área bruta (mais robusto)
                hipotese_critica = max(
                    melhores_por_hipotese.items(), key=lambda kv: kv[1]["area_bruta"]
                )[0]

        # Aplica o perfil escolhido da hipótese crítica
        perfil_final = melhores_por_hipotese[hipotese_critica]["perfil_escolhido"]

        # === 5. Verificação final do perfil escolhido em cada hipótese extrema ===

        # Recalcula os dados do perfil adotado em ambas as hipóteses com seus respectivos esforços
        dados_perfil = None
        for df_perfil_origem in [df_montantes, df_diagonais_horizontais]:
            match = df_perfil_origem[df_perfil_origem["Perfil"].str.strip() == perfil_final.strip()]
            if not match.empty:
                dados_perfil = match.iloc[0]
                break

        # Recalcula os parâmetros normativos para o perfil final em cada hipótese crítica
        for nome_hipotese in esforcos_filtrados:
            forca_axial = esforcos_por_hipotese[nome_hipotese][id_barra]
            solicitacao = "tracao" if forca_axial > 0 else "compressao"

            tipo_base = (
                "montante"
                if "montante" in tipo_barra
                else "diagonal" if "diagonal" in tipo_barra else "horizontal"
            )
            diametro_furo = diametros_furos.get(tipo_base, 1.59)

            verificacao_axial = calcula_tensao_axial_admissivel(
                df_materiais,
                dados_perfil,
                forca_axial,
                tipo_barra,
                comprimento,
                coef_minoracao,
                diametro_furo=diametro_furo,
                limitar_esbeltez_tracao=(solicitacao == "tracao"),
                forcar_verificacao_compressao=(solicitacao == "compressao"),
                descontos_area_liquida=descontos_area_liquida,
            )

            espessura_aba_final = dados_perfil["t(cm)"]
            verificacao_ligacao_final = dimensionar_ligacao(
                forca_axial=forca_axial,
                tipo_barra=tipo_barra,
                perfil_nome=perfil_final,
                espessura_aba=espessura_aba_final,
                diametros_furos=diametros_furos,
                fv_parafuso=df_materiais.loc["A394", "fc (kgf/cm²)"],
                fu_peca=obter_fu(dados_perfil, df_materiais),
                limite_parafusos=limite_parafusos,
                planos_cisalhamento=planos_cisalhamento,
                fatores_esmagamento=fatores_esmagamento,
                df_perfis=df_perfis,
                coef_minoracao=coef_minoracao,
            )

            # Calcula a taxa de trabalho da ligação para essa hipótese
            forca_normal = abs(forca_axial)
            forca_adm_cisalhamento = verificacao_ligacao_final.get("forca_adm_cisalhamento")
            forca_adm_esmagamento = verificacao_ligacao_final.get("forca_adm_esmagamento")
            tx_cis = forca_normal / forca_adm_cisalhamento if forca_adm_cisalhamento else 999
            tx_esm = forca_normal / forca_adm_esmagamento if forca_adm_esmagamento else 999
            verificacao_ligacao_final["tx_lig"] = max(tx_cis, tx_esm)

            # Adiciona a esbeltez corrigida, se ainda não estiver presente
            raio_giracao = (
                dados_perfil["rx(cm)"]
                if tipo_barra.startswith("montante")
                else dados_perfil["rz(cm)"]
            )
            verificacao_axial["raio"] = raio_giracao
            verificacao_axial["esbeltez_corrigida"] = calcular_esbeltez_corrigida(
                tipo_barra, comprimento, raio_giracao
            )

            # Atualiza os dados da hipótese com os resultados do perfil final adotado
            melhores_por_hipotese[nome_hipotese].update(
                {
                    **verificacao_axial,
                    "perfil_escolhido": perfil_final,
                    "verificacao_ligacao": verificacao_ligacao_final,
                    "raio": (
                        dados_perfil["rx(cm)"]
                        if tipo_barra.startswith("montante")
                        else dados_perfil["rz(cm)"]
                    ),
                    "area_bruta": dados_perfil["A(cm2)"],
                    "comprimento": comprimento_real,
                    "comprimento_destravado": comprimento_destravado,
                    "forca_axial": forca_axial,
                    "tipo": tipo_barra,
                    "modulo": dados_barra.get("modulo"),
                    "solicitacao": "tracao" if forca_axial > 0 else "compressao",
                    "alfa": angulo,
                }
            )

            if nome_hipotese.startswith("hip_0"):
                melhores_por_hipotese[nome_hipotese]["simulada"] = True

        # Identifica a hipótese crítica considerando a ligação (maior taxa de trabalho da ligação)
        hipotese_critica_ligacao = max(
            melhores_por_hipotese.items(),
            key=lambda item: item[1].get("verificacao_ligacao", {}).get("tx_lig", 0),
        )[0]

        # Salva os resultados da barra no dicionário final
        resultado_final[id_barra] = {
            "pior_caso": hipotese_critica,
            "pior_ligacao": hipotese_critica_ligacao,
            "perfil_escolhido": perfil_final,
            "forcado_forca_simulada": barra_tem_forca_simulada,
            "hipotese_tracao": hipotese_critica_tracao or "hip_0_t",
            "hipotese_compressao": hipotese_critica_compressao or "hip_0_c",
            **{
                nome_hipotese: melhores_por_hipotese[nome_hipotese]
                for nome_hipotese in melhores_por_hipotese
            },
        }

    # Verifica se houve alguma barra sem perfil viável (tratamento de exceção)
    barras_sem_perfil = [
        id_barra
        for id_barra, dados_barra in resultado_final.items()
        if dados_barra.get("perfil_escolhido") == "NENHUM"
    ]

    if barras_sem_perfil:
        mensagem = f"Dimensionamento inviável! As barras a seguir não obtiveram perfil: {barras_sem_perfil}"
        if interromper_se_inviavel:
            raise ValueError(mensagem)
        else:
            print(mensagem)
            return None, None, None

    # Atualiza metadados com o perfil final escolhido
    for id_barra, dados in resultado_final.items():
        nome_hipotese_critica = dados["pior_caso"]
        perfil = dados[nome_hipotese_critica]["perfil_escolhido"]
        metadados_barras[id_barra]["perfil_escolhido"] = perfil

    # === 6. Dimensionamento das ligações definitivas nos montantes com ligação real ===

    # Recalcula as ligações com base nos perfis finais definidos
    ligacoes_forcadas = otimizar_ligacoes_montantes_extremidades(
        metadados_barras,
        esforcos_por_hipotese,
        df_materiais,
        diametros_furos,
        limite_parafusos,
        planos_cisalhamento,
        fatores_esmagamento,
        df_perfis,
        coef_minoracao=coef_minoracao,
    )

    # Se alguma ligação de montante for inviável, interrompe o processo (ou retorna None)
    if any(not lig.get("ligacao_viavel", True) for lig in ligacoes_forcadas.values()):
        if interromper_se_inviavel:
            raise ValueError("Pelo menos uma ligação de montante ficou inviável.")
        else:
            return None, None, None

    # Expandindo para simétricos e injetando no resultado final:
    for id_base, lig in ligacoes_forcadas.items():
        ids_simetricos = expandir_ligacoes_montantes_simetricos(
            metadados_barras, {id_base}, tolerancia=1e-3
        )
        for id_barra in ids_simetricos:
            if id_barra not in resultado_final or id_barra not in ligacoes_forcadas:
                continue

            nome_hipotese_critica = resultado_final[id_barra]["pior_caso"]
            caso = resultado_final[id_barra][nome_hipotese_critica]

            forca_axial = abs(caso["forca_axial"])
            perfil_nome = caso["perfil_escolhido"]

            linha = df_perfis[df_perfis["Perfil"].str.strip() == perfil_nome.strip()]
            if linha.empty:
                continue

            linha = linha.iloc[0]
            espessura_aba = linha["t(cm)"]
            fu = obter_fu(linha, df_materiais)

            lig = ligacoes_forcadas[id_barra]
            diametro_furo = lig["d_furo"]
            qtd_parafusos = lig["np"]
            fator_fp = lig["fator_fp"]
            forca_adm_cisalhamento = lig["forca_adm_cisalhamento"]

            forca_adm_esmagamento_corrigido = (
                qtd_parafusos * diametro_furo * espessura_aba * fator_fp * fu * coef_minoracao
            )
            tx_cisalhamento = (
                forca_axial / forca_adm_cisalhamento if forca_adm_cisalhamento else 999
            )
            tx_esmagamento = (
                forca_axial / forca_adm_esmagamento_corrigido
                if forca_adm_esmagamento_corrigido
                else 999
            )
            tx_ligacao = max(tx_cisalhamento, tx_esmagamento)

            nova_ligacao = deepcopy(lig)
            nova_ligacao["forca_adm_esmagamento"] = forca_adm_esmagamento_corrigido
            nova_ligacao["tx_lig"] = tx_ligacao

            resultado_final[id_barra][nome_hipotese_critica]["verificacao_ligacao"] = nova_ligacao

    # === 7. Ajuste final de perfil por ligação e simetrização entre montantes ===

    # 7-1. Igualar perfis dos montantes dentro de cada módulo
    igualar_perfis_montantes_por_modulo(
        resultado_final,
        df_montantes,
        df_materiais,
        coef_minoracao,
        diametros_furos,
        descontos_area_liquida=descontos_area_liquida,
    )

    # 7-2. Reforço iterativo por ligação até tx_lig ≤ 1,0 **e**
    #      todos os critérios normativos passarem (máx 10 ciclos)
    barras_reforcadas: set[str] = set()

    for tentativa in range(10):
        ligacoes_iter: dict[str, dict] = {}
        todos_ok = True

        for id_barra in sorted(ids_ligacao_necessaria, key=ordenar_id_barra):
            # pula barras que não chegaram a ser dimensionadas
            if id_barra not in resultado_final or resultado_final[id_barra].get("perfil_escolhido") == "NENHUM":
                todos_ok = False
                continue
            nome_hip = resultado_final[id_barra]["pior_caso"]
            caso = resultado_final[id_barra][nome_hip]
            perfil_ini = caso["perfil_escolhido"]
            N = abs(caso["forca_axial"])

            tipo_barra = metadados_barras[id_barra]["tipo"]
            angulo = metadados_barras[id_barra].get("alfa_graus", 0.0)
            if tipo_barra.startswith("montante"):
                comprimento = metadados_barras[id_barra].get(
                    "comprimento_destravado",
                    metadados_barras[id_barra]["comprimento"],
                )
            else:
                comprimento = metadados_barras[id_barra]["comprimento"]

            reforco = reforcar_montante_ate_viavel(
                id_barra=id_barra,
                perfil_atual=perfil_ini,
                forca_axial=N,
                df_perfis=df_perfis,
                df_materiais=df_materiais,
                diametros_furos=diametros_furos,
                limite_parafusos=limite_parafusos,
                planos_cisalhamento=planos_cisalhamento,
                fatores_esmagamento=fatores_esmagamento,
                coef_minoracao=coef_minoracao,
                descontos_area_liquida=descontos_area_liquida,
                criterios_norma_fn=verificar_axial_flexao,
                criterios_ligacao_fn=wrapper_ligacao_montante,
                tipo_barra=tipo_barra,
                comprimento=comprimento,
                angulo_graus=angulo,
                interromper_se_inviavel=interromper_se_inviavel,
            )

            # — se None: a função já marcou inviável ou lançou exceção —
            if reforco:
                novo_perfil, dados_lig = reforco
                caso["perfil_escolhido"] = novo_perfil
                caso["verificacao_ligacao"] = dados_lig
                ligacoes_iter[id_barra] = dados_lig
            else:
                todos_ok = False

        ligacoes_forcadas.update(ligacoes_iter)  # acumula ligações definitivas

        for id_barra, lig in ligacoes_iter.items():
            # recalcula a hipótese que agora tem maior tx_lig
            nome_pior = max(
                resultado_final[id_barra],
                key=lambda hip: isinstance(resultado_final[id_barra][hip], dict)
                                and resultado_final[id_barra][hip]
                                .get("verificacao_ligacao", {})
                                .get("tx_lig", 0),
            )
            resultado_final[id_barra]["pior_ligacao"] = nome_pior

        barras_reforcadas |= set(ligacoes_iter)  # idem para barras

        if todos_ok:
            break  # todas as barras passaram ligação + norma

    else:  # executa se o for terminar sem break
        if interromper_se_inviavel:
            raise ValueError("Reforço de ligação não convergiu em 10 ciclos.")
        return None, None, None

    # 7-3. Revalidação normativa das barras reforçadas
    if barras_reforcadas:
        for id_barra in sorted(barras_reforcadas, key=ordenar_id_barra):
            dados_barra = metadados_barras[id_barra]
            tipo_barra: str = dados_barra["tipo"]
            angulo = dados_barra.get("alfa_graus", 0.0)
            comp_real = dados_barra["comprimento"]
            comp_destravado = dados_barra.get("comprimento_destravado", comp_real)
            comprimento = comp_destravado if tipo_barra.startswith("montante") else comp_real

            tipo_base = (
                "montante" if "montante" in tipo_barra
                else "diagonal" if "diagonal" in tipo_barra
                else "horizontal"
            )
            diametro_furo = diametros_furos.get(tipo_base, 1.59)

            for nome_hipotese, dados_hip in resultado_final[id_barra].items():
                if not isinstance(dados_hip, dict):
                    continue  # pula campos auxiliares

                perfil_nome = dados_hip["perfil_escolhido"]
                if perfil_nome == "NENHUM":
                    continue

                dados_perfil = df_perfis.loc[
                    df_perfis["Perfil"].str.strip() == perfil_nome.strip()
                ].iloc[0]

                forca_axial = esforcos_por_hipotese[nome_hipotese][id_barra]

                limitar_esbeltez_tracao = (
                    id_barra in barras_exclusivamente_tracionadas
                    and dados_hip["solicitacao"] == "tracao"
                )
                verificacao_axial = calcula_tensao_axial_admissivel(
                    df_materiais=df_materiais,
                    dados_perfil=dados_perfil,
                    forca_axial=forca_axial,
                    tipo_barra=tipo_barra,
                    comprimento_efetivo=comprimento,
                    coef_minoracao=coef_minoracao,
                    diametro_furo=diametro_furo,
                    limitar_esbeltez_tracao=limitar_esbeltez_tracao,
                    forcar_verificacao_compressao=not limitar_esbeltez_tracao,
                    descontos_area_liquida=descontos_area_liquida,
                )

                flexao_ok = verifica_flexao_simples(
                    tipo_barra=tipo_barra,
                    angulo_graus=angulo,
                    comprimento=comprimento,
                    modulo_resistencia_flexao_x=dados_perfil.get("Wx(cm3)", 0.0),
                    tensao_fy=obter_fy(dados_perfil, df_materiais),
                    coef_minoracao=coef_minoracao,
                )

                barra_viavel = verificacao_axial["viavel"] and flexao_ok

                if not barra_viavel:
                    dados_hip["viavel"] = False
                    dados_hip["verificacao_axial"] = verificacao_axial
                    dados_hip["tx_flexao"] = 999.0 if not flexao_ok else 0.0

                    msg = (
                        f"Após reforço da ligação, a barra {id_barra} "
                        f"reprovou em {nome_hipotese}."
                    )
                    if interromper_se_inviavel:
                        raise ValueError(msg)
                    continue

                dados_hip.update(
                    {
                        "verificacao_axial": verificacao_axial,
                        "tx_trabalho": verificacao_axial["taxa_trabalho"],
                        "ft_admissivel": verificacao_axial.get("ft_admissivel"),
                        "Fa_reduzido": verificacao_axial.get("Fa_reduzido"),
                        "viavel": True,
                    }
                )
    # 7-4. Segunda igualação dos perfis dos montantes por módulo
    igualar_perfis_montantes_por_modulo(
        resultado_final,
        df_montantes,
        df_materiais,
        coef_minoracao,
        diametros_furos,
        descontos_area_liquida=descontos_area_liquida,
    )

    # — Atualiza ligações com os perfis já igualados —
    ligacoes_forcadas = otimizar_ligacoes_montantes_extremidades(
        metadados_barras,
        esforcos_por_hipotese,
        df_materiais,
        diametros_furos,
        limite_parafusos,
        planos_cisalhamento,
        fatores_esmagamento,
        df_perfis,
        coef_minoracao,
    )
    for id_barra, lig in ligacoes_forcadas.items():
        nome_hip = resultado_final[id_barra]["pior_caso"]
        resultado_final[id_barra][nome_hip]["verificacao_ligacao"] = lig

    # 7-5. Verificação final das ligações (abortiva)
    for id_barra in ids_ligacao_necessaria:
        nome_lig = resultado_final[id_barra].get("pior_ligacao")
        if not nome_lig:
            continue

        lig = resultado_final[id_barra].get(nome_lig, {}).get("verificacao_ligacao")
        if lig and lig.get("tx_lig", 0) > 1.0:
            if interromper_se_inviavel:
                raise ValueError(
                    f"Ligação da barra {id_barra} ainda reprovada após reforço."
                )
            else:
                return None, None, None

    # === 8. Recalcula a pior taxa de trabalho axial e de ligação com base nos esforços extremos ===

    for id_barra, dados in resultado_final.items():
        perfil = dados["perfil_escolhido"]
        if perfil == "NENHUM":
            continue

        dados_perfil = df_perfis[df_perfis["Perfil"].str.strip() == perfil.strip()]
        if dados_perfil.empty:
            continue
        dados_perfil = dados_perfil.iloc[0]

        tipo = next((d["tipo"] for d in dados.values() if isinstance(d, dict) and "tipo" in d), "")
        comprimento_destravado = next(
            (
                d["comprimento_destravado"]
                for d in dados.values()
                if isinstance(d, dict) and "comprimento_destravado" in d
            ),
            1,
        )

        d_furo = diametros_furos.get(
            (
                "montante"
                if "montante" in tipo
                else "diagonal" if "diagonal" in tipo else "horizontal"
            ),
            1.59,
        )

        # Recalcula força admissível para tração e compressão com o perfil final
        forca_normal_tracao = max(
            [
                hip.get("forca_axial", 0)
                for hip in dados.values()
                if isinstance(hip, dict) and hip.get("forca_axial", 0) > 0
            ],
            default=0,
        )
        forca_normal_compressao = min(
            [
                hip.get("forca_axial", 0)
                for hip in dados.values()
                if isinstance(hip, dict) and hip.get("forca_axial", 0) < 0
            ],
            default=0,
        )

        forca_admissivel_tracao = calcula_tensao_axial_admissivel(
            df_materiais,
            dados_perfil,
            forca_axial=forca_normal_tracao,
            tipo_barra=tipo,
            comprimento_efetivo=comprimento_destravado,
            coef_minoracao=coef_minoracao,
            diametro_furo=d_furo,
            limitar_esbeltez_tracao=True,
            forcar_verificacao_compressao=False,
            descontos_area_liquida=descontos_area_liquida,
        ).get("forca_axial_admissivel", 1e-6)
        forca_admissivel_compressao = calcula_tensao_axial_admissivel(
            df_materiais,
            dados_perfil,
            forca_axial=forca_normal_compressao,
            tipo_barra=tipo,
            comprimento_efetivo=comprimento_destravado,
            coef_minoracao=coef_minoracao,
            diametro_furo=d_furo,
            limitar_esbeltez_tracao=False,
            forcar_verificacao_compressao=True,
            descontos_area_liquida=descontos_area_liquida,
        ).get("forca_axial_admissivel", 1e-6)

        tx_axial_trac = (
            abs(forca_normal_tracao) / forca_admissivel_tracao if forca_admissivel_tracao else 0
        )
        tx_axial_comp = (
            abs(forca_normal_compressao) / forca_admissivel_compressao
            if forca_admissivel_compressao
            else 0
        )
        dados["taxa_trabalho_final"] = max(tx_axial_trac, tx_axial_comp)

        # Recalcula taxas de ligação com a ligação final da barra
        lig = dados.get(dados.get("pior_ligacao", ""), {}).get("verificacao_ligacao")
        if not lig:
            continue  # não há ligação para essa barra

        forca_admissivel_cisalhamento = lig.get("forca_adm_cisalhamento", 1)
        forca_admissivel_esmagamento = lig.get("forca_adm_esmagamento", 1)

        tx_lig_trac = (
            max(
                divisao_segura(abs(forca_normal_tracao), forca_admissivel_cisalhamento),
                divisao_segura(abs(forca_normal_tracao), forca_admissivel_esmagamento),
            )
            if forca_normal_tracao
            else 0
        )
        tx_lig_comp = (
            max(
                divisao_segura(abs(forca_normal_compressao), forca_admissivel_cisalhamento),
                divisao_segura(abs(forca_normal_compressao), forca_admissivel_esmagamento),
            )
            if forca_normal_tracao
            else 0
        )
        dados["tx_lig_final"] = max(tx_lig_trac, tx_lig_comp)

    # === 9. Retorno dos resultados finais do dimensionamento ===
    return resultado_final, ligacoes_forcadas, ids_ligacao_necessaria

