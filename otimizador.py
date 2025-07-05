import itertools
import math
from math import prod
import time
from datetime import datetime

import pandas as pd

import sys
import os
import contextlib

from dimensionamento import (
    dimensionar_barras,
)
from gerador_estrutura import montar_estrutura_modular
from utilitarios.analise_estrutural import executar_hipoteses_carregamento
from utilitarios.constantes import (
    COEF_MINORACAO_PADRAO,
    PESO_PROPRIO_INICIAL_PADRAO,
    LIMITE_TRAMO,
    FATOR_ESMAGAMENTO_PADRAO,
    REPOSITORIO_PLANILHAS,
    REPOSITORIO_LOGS,
    MAX_DIAGONAIS,
)

from utilitarios.classes import DuplicadorSaida

from utilitarios.ferramentas_montantes import (
    calcular_areas_equivalentes_montantes,
    obter_menores_tramos_montantes,
)
from utilitarios.forcas import gerar_cargas_peso_proprio

from utilitarios.impressao_resultados import (
    imprimir_tabela_resultados,
    imprimir_tabela_resultados_resumida,
    exibir_resultados_graficos,
    gerar_gif_combinado_final,
)

from utilitarios.io_excel import carregar_tabela_materiais, carregar_tabela_perfis
from utilitarios.peso import calcular_peso_por_modulo, calcular_peso_total


def otimizar_estrutura(
    alturas: list[float],
    largura: float,
    hipoteses: list[dict],
    coef_minoracao: float = COEF_MINORACAO_PADRAO,
    diametros_furos: dict[str, float] = None,
    descontos_area_liquida: dict[str, int] = None,
    limite_parafusos: dict[str, int] = None,
    planos_cisalhamento: dict[str, int] = None,
    fatores_esmagamento: list[float] = None,
    peso_proprio_inicial_por_modulo: list[float] = None,
    areas_iniciais: dict[str, float] = None,
    interromper_se_inviavel: bool = True,
    exibir_estrutura: bool = False,
    exibir_esforcos: bool = False,
    exibir_deformada: bool = False,
    exibir_reacoes_apoio: bool = True,
    mostrar_na_tela: bool = True,
    salvar_imagem: bool = True,
    formatos_graficos: list[str] = ["png", "svg"],
    fator_deformada: float = 1,
    impressao_tabela: str = "completa",
    animacao_deformada: bool = False,
    exportar_planilha_resultados: bool = False,
    gerar_log: bool = True,
    label_x: str | None = None,
    label_y: str | None = None,
    titulo_grafico: str | None = None,
) -> None:
    """
    Executa a otimização estrutural de uma torre modular para todas as combinações possíveis
    de número de diagonais por módulo, respeitando os critérios normativos e geométricos definidos.

    A função explora exaustivamente todas as combinações viáveis, iterando sobre diferentes quantidades
    de diagonais por módulo e dimensionando cada configuração até a convergência dos perfis e do peso próprio.

    O algoritmo é dividido nas seguintes etapas principais:

    1. **Geração de combinações de diagonais**
       Cria todas as combinações possíveis de número de diagonais por módulo,
       iniciando com 2 diagonais por módulo e aumentando até que os menores tramos
       verticais (montantes) sejam maiores ou iguais ao limite `LIMITE_TRAMO`.

    2. **Loop principal de avaliação**
       Para cada combinação:
       - Realiza até 10 ciclos de análise estrutural e dimensionamento,
         atualizando o peso próprio e as áreas das barras a cada iteração;
       - Em cada ciclo:
         - Executa todas as hipóteses de carregamento na estrutura gerada;
         - Dimensiona as barras, incluindo verificação de ligações;
         - Recalcula o peso da estrutura e gera novas cargas verticais por módulo;
         - Verifica a convergência dos perfis (mantêm-se os mesmos entre iterações).

    3. **Validação da solução**
       Se houver barras sem perfil viável, ausentes, ou deslocamentos irrealistas (> 100 cm),
       a configuração é descartada. Caso contrário, é armazenada como solução viável.

    4. **Seleção da melhor configuração**
       Ao fim da varredura, são selecionadas:
       - A **melhor configuração global** (menor peso);
       - A **melhor configuração com menor tramo igual 100cm**.

    5. **Exibição dos resultados**
       Os resultados são impressos em forma de tabela, cujo formato é definido pelo usuário através do
       parâmetro `impressao_tabela`. As opções disponíveis são:

       - `"completa"`: Imprime a tabela completa com todas as informações, incluindo o tipo de barra e o ângulo.
       - `"resumida"`: Imprime a tabela simplificada, sem as colunas "Tipo" e "α", e com identificadores curtos
         (M1e, M2d, H3, D4...).
       - `"ambas"`: Imprime as duas versões sequencialmente, uma após a outra.

       Caso `exibir_estrutura`, `exibir_esforcos`, `exibir_deformada` ou `exibir_reacoes_apoio` sejam True,
       os gráficos são gerados com base nos controles definidos pelos parâmetros `mostrar_na_tela`,
       `salvar_imagem`, `formatos_graficos` e `fator_deformada`.

       Se `animacao_deformada` for True, é gerado também um GIF animado da deformada para cada hipótese,
       e ao final da execução um GIF combinado com todas as hipóteses será salvo automaticamente.

       Esta etapa corresponde logicamente aos blocos 6 e 7 do código:
       - **Bloco 6**: Geração de gráficos para a melhor configuração encontrada.
       - **Bloco 7**: Geração de gráficos para a melhor configuração com tramos de 100 cm, se houver.

    6. **Exportação automática dos resultados para planilha**
       Se o parâmetro `exportar_planilha_resultados` for True, a função gera automaticamente
       uma planilha `.xlsx` com todas as configurações viáveis testadas pelo otimizador,
       "incluindo a quantidade de diagonais por módulo, o peso de cada módulo e o peso total correspondente."

       O número de colunas de diagonais se adapta dinamicamente à quantidade de módulos da torre.
       A planilha é salva no diretório definido pela constante `REPOSITORIO_PLANILHAS`.

    Args:
        alturas (list[float]): Alturas dos módulos da torre (em centímetros).
        largura (float): Largura da base da torre (em centímetros).
        hipoteses (list[dict]): Lista de hipóteses de carregamento, cada uma com nome e forças aplicadas.
        coef_minoracao (float): Coeficiente de minoração da resistência dos materiais.
        diametros_furos (dict[str, float], optional): Diâmetros dos furos por tipo de barra.
        descontos_area_liquida (dict[str, int], optional): Número de furos a descontar na tração, por tipo de barra.
        limite_parafusos (dict[str, int], optional): Número máximo de parafusos permitidos por tipo de barra.
        planos_cisalhamento (dict[str, int], optional): Número de planos de cisalhamento por tipo de barra.
        fatores_esmagamento (list[float], optional): Fatores de amplificação do esforço admissível ao esmagamento.
        peso_proprio_inicial_por_modulo (list[float], optional): Estimativa inicial do peso próprio por módulo (em kgf).
        areas_iniciais (dict[str, float], optional): Áreas iniciais das barras, por tipo (usadas apenas na 1ª iteração).
        interromper_se_inviavel (bool): Se True, interrompe o processo caso alguma barra não encontre perfil viável.
        exibir_estrutura (bool): Se True, exibe/salva a geometria da estrutura final.
        exibir_esforcos (bool): Se True, exibe/salva os esforços axiais nas barras.
        exibir_deformada (bool): Se True, exibe/salva a configuração deformada da estrutura.
        exibir_reacoes_apoio (bool): Se True, exibe/salva as reações de apoio da estrutura.
        mostrar_na_tela (bool): Se True, exibe os gráficos na tela com `plt.show()`.
        salvar_imagem (bool): Se True, salva os gráficos em arquivos no diretório configurado.
        formatos_graficos (list[str], optional): Lista de formatos desejados para salvar os gráficos (ex: ["png", "svg"]).
        fator_deformada (float, optional): Fator de escala visual aplicado à deformada no gráfico. Padrão é 1.0.
        impressao_tabela (str): Tipo de impressão da tabela ("completa", "resumida", "ambas").
        animacao_deformada (bool): Se True, gera um GIF animado da deformada para cada hipótese e um combinado final.
        label_x (str, optional): Rótulo do eixo X nos gráficos. Aplica-se a todos os gráficos exibidos ou salvos.
        label_y (str, optional): Rótulo do eixo Y nos gráficos. Aplica-se a todos os gráficos exibidos ou salvos.
        titulo_grafico (str, optional): Título personalizado para o gráfico da geometria da estrutura. Não afeta os
                                        títulos dos gráficos de esforços, deformada ou reações.
        exportar_planilha_resultados (bool): Se True, exporta uma planilha `.xlsx` com todas as configurações viáveis
                                            e seus respectivos pesos.
        gerar_log (bool): Se True, salva a execução completa em um arquivo `.txt` no diretório definido por
                          `REPOSITORIO_LOGS`.

    Returns:
        None: Os resultados são impressos no console e, opcionalmente, visualizados e/ou salvos como imagem.

    Raises:
        ValueError: Se algum perfil viável não for encontrado durante o dimensionamento.
        RuntimeError: Se houver falha crítica na geração ou análise estrutural.

    Notes:
        - A cada nova configuração testada, as áreas das barras são atualizadas iterativamente
          até convergirem com os esforços aplicados e o peso próprio real.
        - Apenas configurações que resultem em uma estrutura estável e verificável
          são consideradas candidatas à solução ótima.
        - Os perfis finais utilizados por barra, a tabela de resultados e as ligações são
          automaticamente recalculados com base na convergência obtida.
        - Os gráficos são salvos no diretório definido pela constante `REPOSITORIO_IMAGENS`, respeitando os formatos indicados.
        - Ao final da execução, são impressas estatísticas de desempenho: total de combinações testadas, viáveis e inviáveis, além do tempo total de execução formatado.
    """

    if gerar_log:
        agora = datetime.now()
        timestamp = agora.strftime("%Y-%m-%d_%Hh%M")
        nome_log = f"log_execucao_{timestamp}.txt"
        caminho_log = os.path.join(REPOSITORIO_LOGS, nome_log)

        f_log = open(caminho_log, "w", encoding="utf-8")
        duplicador = DuplicadorSaida(sys.stdout, f_log)
        contexto_log = contextlib.redirect_stdout(duplicador)
        contexto_log.__enter__()
        print(f"🟢 Início da execução: {agora.strftime('%d/%m/%Y %H:%M:%S')}\n")
    else:
        f_log = None
        contexto_log = None

    # === 1. Inicialização de parâmetros opcionais ===

    if diametros_furos is None:
        diametros_furos = {
            "montante": 1.59,
            "diagonal": 1.27,
            "horizontal": 1.27,
        }

    if limite_parafusos is None:
        limite_parafusos = {
            "montante": 20,
            "diagonal": 2,
            "horizontal": 2,
        }

    if planos_cisalhamento is None:
        planos_cisalhamento = {
            "montante": 1,
            "diagonal": 1,
            "horizontal": 1,
        }

    if fatores_esmagamento is None:
        fatores_esmagamento = [FATOR_ESMAGAMENTO_PADRAO, 1.25]

    if peso_proprio_inicial_por_modulo is None:
        peso_proprio_inicial_por_modulo = [PESO_PROPRIO_INICIAL_PADRAO for _ in alturas]

    if areas_iniciais is None:
        areas_iniciais = {
            "montante_esq": 4.30,
            "montante_dir": 4.30,
            "horizontal_sup": 4.30,
            "diagonal": 4.30,
        }

    # === 2. Carregamento das tabelas de perfis e materiais ===
    df_montantes, df_diagonais_e_horizontais = carregar_tabela_perfis("dados/tabela_perfis.xlsx")
    df_materiais = carregar_tabela_materiais("dados/propriedades_materiais.xlsx")

    df_perfis_completo = pd.concat([df_montantes, df_diagonais_e_horizontais]).drop_duplicates(
        subset="Perfil"
    )

    qtd_modulos = len(alturas)

    # === 3. Geração de combinações de diagonais por módulo ===

    # Gera as faixas de diagonais por módulo com teto absoluto definido por MAX_DIAGONAIS
    limites_diagonais_por_modulo = [
        list(range(2, min(math.floor(altura / LIMITE_TRAMO) + 1, MAX_DIAGONAIS + 1)))
        for altura in alturas
    ]
    configuracoes_viaveis = []

    # === 4. Loop principal de teste para cada combinação de diagonais por modulo ===

    tempo_inicio_otimizacao = time.time()
    total_testadas = 0
    # Contadores de estatísticas da execução
    total_viaveis = 0
    total_inviaveis = 0

    espaco_real = prod(len(v) for v in limites_diagonais_por_modulo)
    print(f"Tamanho do espaço de busca: {espaco_real} combinações")
    for diagonais_por_modulo in itertools.product(*limites_diagonais_por_modulo):

        total_testadas += 1

        tramos = obter_menores_tramos_montantes(alturas, diagonais_por_modulo)

        # [CHECK DESATIVADO]
        # A verificação dos tramos dos montantes foi identificada como redundante,
        # pois o processo de geração do espaço de busca já garante que todas as
        # combinações possíveis atendem ao limite mínimo de tramo vertical (LIMITE_TRAMO).
        # Este bloco foi mantido comentado apenas por precaução, caso alterações futuras
        # na lógica do pipeline ou no gerador de estrutura exijam reativá-lo.

        #if not all(t >= LIMITE_TRAMO for t in tramos):
        #    total_inviaveis += 1
        #    continue

        valor_formatado = (
            diagonais_por_modulo[0] if len(diagonais_por_modulo) == 1 else diagonais_por_modulo
        )
        print(
            f"[TESTANDO] diagonais_por_modulo = {valor_formatado} | Menores tramos: {[f'{t:.1f}' for t in tramos]}"
        )

        # Inicializa variáveis que serão atualizadas em cada iteração
        areas_por_id = None
        resultados = None
        ids_expandidos_final = None  # salva a versão final que deve ser usada na impressão
        cargas_verticais_por_no = None
        ids_obrigatorios = None

        # === 4.1 Iteração interna até estabilização dos perfis (máx. 10 ciclos) ===

        for iteracao in range(10):

            # Ciclo de ajuste iterativo: atualiza esforços, perfis e peso próprio até estabilizar

            # === 4.1.1 Análise estrutural com áreas atuais e cargas atuais ===

            # Gera nova malha com base nas áreas atuais e reaplica todas as hipóteses de carregamento
            esforcos_por_hipotese, estruturas_por_hipotese = executar_hipoteses_carregamento(
                hipoteses=hipoteses,
                alturas=alturas,
                largura=largura,
                diagonais_por_modulo=list(diagonais_por_modulo),
                areas_iniciais=areas_iniciais if areas_por_id is None else None,
                areas_por_id=areas_por_id,
                peso_proprio_inicial_por_modulo=(
                    peso_proprio_inicial_por_modulo if cargas_verticais_por_no is None else None
                ),
                cargas_verticais_por_no=cargas_verticais_por_no,
            )

            # === 4.1.2 Dimensionamento estrutural ===

            try:
                novos_resultados, ligacoes_forcadas, ids_expandidos = dimensionar_barras(
                    esforcos_por_hipotese,
                    estruturas_por_hipotese,
                    df_montantes,
                    df_diagonais_e_horizontais,
                    df_materiais,
                    df_perfis=df_perfis_completo,
                    coef_minoracao=coef_minoracao,
                    diametros_furos=diametros_furos,
                    descontos_area_liquida=descontos_area_liquida,
                    limite_parafusos=limite_parafusos,
                    planos_cisalhamento=planos_cisalhamento,
                    fatores_esmagamento=fatores_esmagamento,
                    interromper_se_inviavel=interromper_se_inviavel,  # força interrupção se falhar
                )

                # Armazena o conjunto de barras esperadas na primeira execução
                if ids_obrigatorios is None:  # 1ª malha completa
                    ids_obrigatorios = set(ids_expandidos)

                # Verificação unificada de inviabilidade por:
                # - Falha no dimensionamento
                # - Barras sem perfil definido
                # - Barras ausentes

                barras_sem_perfil = []

                # Verifica se o dimensionamento falhou completamente, se há barras sem perfil ou se faltaram barras no retorno
                if novos_resultados is None:
                    motivo = "dimensionamento retornou None"
                else:
                    barras_sem_perfil = [
                        id_barra
                        for id_barra, dados_barra in novos_resultados.items()
                        if dados_barra.get("perfil_escolhido") in (None, "NENHUM")
                    ]
                    if barras_sem_perfil:
                        motivo = f"barras sem perfil: {sorted(barras_sem_perfil)}"
                    else:
                        barras_ausentes = (
                            ids_obrigatorios - set(novos_resultados.keys())
                            if ids_obrigatorios
                            else set()
                        )
                        if barras_ausentes:
                            motivo = f"barras ausentes: {sorted(map(str, barras_ausentes))}"
                            barras_sem_perfil = list(barras_ausentes)
                        else:
                            motivo = None

                if motivo:
                    print(
                        f"❌ Configuração {diagonais_por_modulo} descartada por inviabilidade no dimensionamento."
                    )
                    resultados = None
                    total_inviaveis += 1
                    break
            except ValueError as e:

                # Intercepta falhas críticas no dimensionamento (ex: ligação inviável com interrupção forçada)
                print(f"[DESCARTADA] Configuração inválida: {e}")
                if interromper_se_inviavel:
                    raise
                resultados = None
                break  # pula para fora do loop de iteração de perfis

            # === 4.1.3 Atualização do peso por módulo e geração de novas cargas ===

            (
                peso_total_por_modulo,
                peso_montantes_por_modulo,
                peso_diagonais_e_horizontais_por_modulo,
            ) = calcular_peso_por_modulo(
                novos_resultados,
                df_perfis_completo,
                estruturas_por_hipotese,
            )

            # Usa uma das estruturas para gerar as cargas de peso próprio atualizadas
            estrutura_referencia = next(iter(estruturas_por_hipotese.values()))

            cargas_verticais_por_no = gerar_cargas_peso_proprio(
                estrutura_referencia,
                peso_montantes_por_modulo,
                peso_diagonais_e_horizontais_por_modulo,
            )

            # Calcula a área real usada em cada sub-barra de montante, ponderando os perfis
            # selecionados nos segmentos superiores/inferiores de cada módulo.
            # Remove barras com área None (sem perfil atribuído).
            novas_areas_por_id = {
                id_barra: area
                for id_barra, area in calcular_areas_equivalentes_montantes(
                    novos_resultados
                ).items()
                if area is not None
            }

            # === 4.1.4 Verificação de convergência dos perfis ===

            # Verifica se os perfis estabilizaram (não mudaram em relação à iteração anterior)
            if resultados is not None:
                convergiu = all(
                    novos_resultados[id_barra]["perfil_escolhido"]
                    == resultados[id_barra]["perfil_escolhido"]
                    for id_barra in resultados
                    if id_barra in novos_resultados
                )
                if convergiu:
                    resultados = novos_resultados
                    areas_por_id = novas_areas_por_id
                    ids_expandidos_final = ids_expandidos
                    break

            resultados = novos_resultados
            areas_por_id = novas_areas_por_id
            ids_expandidos_final = ids_expandidos  # salva mesmo que ainda não tenha convergido

        if resultados is None:
            total_inviaveis += 1
            continue  # pula para a próxima combinação de diagonais

        # === 4.2 Reavaliação do peso final após estabilização ===

        # Recalcula corretamente as cargas verticais reais com base na estrutura analisada (com sub_barras)
        estrutura_base = next(iter(estruturas_por_hipotese.values()))

        (
            peso_total_por_modulo,
            peso_montantes_por_modulo,
            peso_diagonais_e_horizontais_por_modulo,
        ) = calcular_peso_por_modulo(
            resultados,
            df_perfis_completo,
            {"final": estrutura_base},
        )

        cargas_verticais_por_no = gerar_cargas_peso_proprio(
            estrutura_base,
            peso_montantes_por_modulo,
            peso_diagonais_e_horizontais_por_modulo,
        )

        # Remove entradas com área None (barras sem perfil válido)
        areas_por_id = {
            id_barra: area for id_barra, area in areas_por_id.items() if area is not None
        }

        # Monta a estrutura definitiva com os perfis finais e cargas reais atualizadas
        estrutura_final = montar_estrutura_modular(
            alturas_modulos=alturas,
            largura=largura,
            forcas=hipoteses[0]["forcas"],
            limite_diagonais_por_modulo=max(diagonais_por_modulo),
            diagonais_por_modulo=list(diagonais_por_modulo),
            areas_por_id=areas_por_id,
            cargas_verticais_por_no=cargas_verticais_por_no,
        )

        # Calcula o deslocamento máximo resultante da estrutura final
        deslocamentos = estrutura_final.get_node_displacements()
        desloc_max = max(math.hypot(d["ux"], d["uy"]) for d in deslocamentos)

        # filtro: deslocamento infinito ou > 100 cm
        if (not math.isfinite(desloc_max)) or desloc_max > 100:
            print(
                f"❌ Configuração {diagonais_por_modulo} descartada por inviabilidade no dimensionamento."
            )
            total_inviaveis += 1
            continue
        peso = calcular_peso_total(resultados, df_perfis_completo)

        # Se o deslocamento foi válido e o peso pôde ser calculado, armazena a configuração como viável
        if peso is not None:
            total_viaveis += 1
            configuracoes_viaveis.append(
                (
                    peso,
                    diagonais_por_modulo,
                    resultados,
                    estrutura_final,
                    ids_expandidos_final,
                    cargas_verticais_por_no.copy(),
                    peso_total_por_modulo.copy(),  # <== novo
                )
            )
            configuracao_formatada = (
                diagonais_por_modulo[0] if len(diagonais_por_modulo) == 1 else diagonais_por_modulo
            )
            peso_modulos_str = " | ".join(
                f"M{i + 1}: {peso_total_por_modulo[k]:.2f} kg"
                for i, k in enumerate(sorted(peso_total_por_modulo))
            )
            print(f"[ACEITA] Peso total = {peso:.2f} kg | {peso_modulos_str} | Configuração = {configuracao_formatada}")

        else:
            # Se saiu do loop sem convergir, ainda assim salva o último estado de ids_expandidos
            ids_expandidos_final = ids_expandidos

    tempo_fim_otimizacao = time.time()
    duracao = tempo_fim_otimizacao - tempo_inicio_otimizacao

    minutos = int(duracao // 60)
    segundos = int(duracao % 60)

    horas = int(minutos // 60)
    minutos = minutos % 60

    duracao_formatada = (
        f"{horas}h {minutos}min {segundos}s" if horas > 0 else
        f"{minutos}min {segundos}s" if minutos > 0 else
        f"{segundos}s"
    )

    # Impressão do resumo da execução
    print(f"\n{total_testadas} combinações testadas!")
    print(f"{total_viaveis} combinações viáveis")
    print(f"{total_inviaveis} combinações inviáveis")
    print(f"\n⏱️ Tempo de execução: {duracao_formatada} ({duracao:.2f}s)")

    # === 5. Seleção da melhor configuração encontrada ===

    if not configuracoes_viaveis:
        print("Nenhuma configuração viável encontrada.")
        return

    configuracoes_viaveis.sort()
    peso, diagonais_por_modulo, resultados, estrutura, ids_expandidos_final, cargas_da_vencedora, peso_modulos = (
        configuracoes_viaveis[0]
    )

    print("\n=== MELHOR CONFIGURAÇÃO ENCONTRADA ===")
    valor_formatado = diagonais_por_modulo[0] if len(diagonais_por_modulo) == 1 else diagonais_por_modulo
    print(f"Quantidade de diagonais por módulo = {valor_formatado} | Peso = {peso:.2f} kg")

    deslocamentos = estrutura.get_node_displacements()
    deslocamento_maximo = max(math.hypot(d["ux"], d["uy"]) for d in deslocamentos)
    print(f"Deslocamento máximo: {deslocamento_maximo:.3f} cm")

    if impressao_tabela == "completa":
        imprimir_tabela_resultados(
            resultados,
            ids_expandidos_final,
            df_montantes,
            df_diagonais_e_horizontais
        )
    elif impressao_tabela == "resumida":
        imprimir_tabela_resultados_resumida(
            resultados,
            ids_expandidos_final,
            df_montantes,
            df_diagonais_e_horizontais
        )
    elif impressao_tabela == "ambas":
        imprimir_tabela_resultados(
            resultados,
            ids_expandidos_final,
            df_montantes,
            df_diagonais_e_horizontais
        )
        imprimir_tabela_resultados_resumida(
            resultados,
            ids_expandidos_final,
            df_montantes,
            df_diagonais_e_horizontais
        )

    # === 6. Visualização da melhor estrutura encontrada (opcional) ===

    areas_finais_por_id = calcular_areas_equivalentes_montantes(resultados)

    for hipotese in hipoteses:
        estrutura_para_plot = montar_estrutura_modular(
            alturas_modulos=alturas,
            largura=largura,
            forcas=hipotese["forcas"],
            limite_diagonais_por_modulo=max(diagonais_por_modulo),
            diagonais_por_modulo=list(diagonais_por_modulo),
            areas_por_id=areas_finais_por_id,
            cargas_verticais_por_no=cargas_da_vencedora,
        )

        print(f"\n--- Visualização para hipótese: {hipotese['nome']} ---")
        exibir_resultados_graficos(
            estrutura=estrutura_para_plot,
            nome_hipotese=hipotese["nome"],
            imprimir_estrutura=exibir_estrutura,
            imprimir_esforcos_axiais=exibir_esforcos,
            imprimir_deformada=exibir_deformada,
            imprimir_reacoes_apoio=exibir_reacoes_apoio,
            mostrar_na_tela=mostrar_na_tela,
            salvar_imagem=salvar_imagem,
            formatos=formatos_graficos,
            fator_deformada=fator_deformada,
            verbosity=0,
            titulo_personalizado=titulo_grafico,
            label_x=label_x,
            label_y=label_y,
            animacao_deformada=animacao_deformada,
        )

    if animacao_deformada:
        gerar_gif_combinado_final(
            nome_saida="gif_deformadas_melhor_configuracao.gif",
            duracao=0.01,
            sufixo_filtragem=None  # combina todos os que começam com "gif_deformada_" e **não** têm "_100"
        )

    # === 7. Comparação extra: melhor configuração com tramos de 100 cm em todos os módulos ===

    def diagonais_necessarias_para_tramo_100(alturas_cm):
        return tuple(math.ceil(h / 100) for h in alturas_cm)

    alvo_diagonais = diagonais_necessarias_para_tramo_100(alturas)

    configuracoes_tramo_100 = [
        tupla for tupla in configuracoes_viaveis if tuple(tupla[1]) == alvo_diagonais
    ]

    if configuracoes_tramo_100:
        configuracoes_tramo_100.sort(key=lambda x: x[0])  # ordena pelo peso

        (
            peso_100,
            diagonais_100,
            resultados_100,
            estrutura_100,
            ids_expandidos_100,
            cargas_100,
            peso_modulos_100,
        ) = configuracoes_tramo_100[0]

        print("\n=== MELHOR CONFIGURAÇÃO COM TRAMOS DE 100cm ===")
        valor_formatado_igual = diagonais_100[0] if len(
            diagonais_100) == 1 else diagonais_100
        print(
            f"Quantidade de diagonais por módulo = {valor_formatado_igual} | Peso total = {peso_100:.2f} kg")

        deslocamentos_100 = estrutura_100.get_node_displacements()
        deslocamento_maximo = max(
            math.hypot(d["ux"], d["uy"]) for d in deslocamentos_100
        )
        print(f"Deslocamento máximo: {deslocamento_maximo:.3f} cm")

        if impressao_tabela == "completa":
            imprimir_tabela_resultados(
                resultados_100,
                ids_expandidos_100,
                df_montantes,
                df_diagonais_e_horizontais
            )
        elif impressao_tabela == "resumida":
            imprimir_tabela_resultados_resumida(
                resultados_100,
                ids_expandidos_100,
                df_montantes,
                df_diagonais_e_horizontais
            )
        elif impressao_tabela == "ambas":
            imprimir_tabela_resultados(
                resultados_100,
                ids_expandidos_100,
                df_montantes,
                df_diagonais_e_horizontais
            )
            imprimir_tabela_resultados_resumida(
                resultados_100,
                ids_expandidos_100,
                df_montantes,
                df_diagonais_e_horizontais
            )

        for hipotese in hipoteses:
            nome_hipotese_verificada = f"{hipotese['nome']} - L de 200 cm"
            nome_original = hipotese['nome']
            titulo_personalizado = f"Melhor configuração com L de 200 cm - {nome_original}"

            estrutura_para_plot = montar_estrutura_modular(
                alturas_modulos=alturas,
                largura=largura,
                forcas=hipotese["forcas"],
                limite_diagonais_por_modulo=max(diagonais_100),
                diagonais_por_modulo=list(diagonais_100),
                areas_por_id=calcular_areas_equivalentes_montantes(resultados_100),
                cargas_verticais_por_no=cargas_100,
            )


            exibir_resultados_graficos(
                estrutura=estrutura_para_plot,
                nome_hipotese=nome_hipotese_verificada,
                imprimir_estrutura=exibir_estrutura,
                imprimir_esforcos_axiais=exibir_esforcos,
                imprimir_deformada=exibir_deformada,
                imprimir_reacoes_apoio=exibir_reacoes_apoio,
                mostrar_na_tela=mostrar_na_tela,
                salvar_imagem=salvar_imagem,
                formatos=formatos_graficos,
                fator_deformada=fator_deformada,
                verbosity=0,
                titulo_personalizado=titulo_grafico,
                label_x=label_x,
                label_y=label_y,
                animacao_deformada=animacao_deformada,
            )

    if animacao_deformada:
        gerar_gif_combinado_final(
            nome_saida="gif_deformadas_100.gif",
            duracao=0.01,
            sufixo_filtragem="_100"  # combina **somente** os gifs das hipóteses que têm "_100" no nome
        )

    # === 8. Exportação automática da planilha de resultados (se habilitado) ===
    if exportar_planilha_resultados:
        # Geração da planilha com colunas dinâmicas de diagonais e pesos por módulo
        dados = []
        for peso, config, _, _, _, _, peso_modulos in configuracoes_viaveis:
            pesos_modulares = [round(peso_modulos.get(k, 0), 2) for k in sorted(peso_modulos)]
            linha = list(config) + pesos_modulares + [round(peso, 2)]
            dados.append(linha)

        num_modulos = len(configuracoes_viaveis[0][1])
        colunas = (
                [f"Diagonais Módulo {i + 1}" for i in range(num_modulos)] +
                [f"Peso Módulo {k} (kg)" for k in sorted(peso_modulos)] +
                ["Peso total (kg)"]
        )
        df_resultados = pd.DataFrame(dados, columns=colunas)

        caminho_planilha = os.path.join(REPOSITORIO_PLANILHAS, "resultados_otimizador.xlsx")
        df_resultados.to_excel(caminho_planilha, index=False)

        print(f"\n📁 Planilha de resultados salva em: {caminho_planilha}")
    if gerar_log and contexto_log:
        print(f"\n🟢 Fim da execução: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        # Finaliza o redirecionamento da saída para o log
        contexto_log.__exit__(None, None, None)
        f_log.close()
        print(f"\n📝 Log completo salvo em: {caminho_log}")

