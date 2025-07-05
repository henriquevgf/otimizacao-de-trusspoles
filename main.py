from otimizador import otimizar_estrutura
from utilitarios.constantes import FATOR_ESMAGAMENTO_PADRAO

# ------------------------------------------------------------
# Dados do problema
# ------------------------------------------------------------

alturas = [300, 300, 300]  # alturas dos módulos [1, 2, ...] em cm
largura = 100  # largura do tronco em cm

hipoteses = [
    {"nome": "Fh(+)", "forcas": [445, 883, 1293]},
    {"nome": "Fh(-)", "forcas": [-445, -883, -1293]},
]

diametros_furos = {
    "montante": 1.27,  # cm
    "diagonal": 1.27,  # cm
    "horizontal": 1.27,  # cm
}

descontos_area_liquida = {
    "diagonal": 1,
    "horizontal": 1,
}

limite_parafusos = {
    "montante": 20,
    "diagonal": 2,
    "horizontal": 2,
}

planos_cisalhamento = {
    "montante": 1,
    "diagonal": 1,
    "horizontal": 1,
}

fatores_esmagamento = [FATOR_ESMAGAMENTO_PADRAO, 1.25]

coef_minoracao = 0.9

# ------------------------------------------------------------
# Execução da otimização
# ------------------------------------------------------------

otimizar_estrutura(
    alturas=alturas,
    largura=largura,
    hipoteses=hipoteses,
    coef_minoracao=coef_minoracao,
    diametros_furos=diametros_furos,
    descontos_area_liquida=descontos_area_liquida,
    limite_parafusos=limite_parafusos,
    planos_cisalhamento=planos_cisalhamento,
    fatores_esmagamento=fatores_esmagamento,
    interromper_se_inviavel=False,
    exibir_estrutura=False,
    exibir_esforcos=False,
    exibir_deformada=False,
    exibir_reacoes_apoio=False,
    mostrar_na_tela=False,
    salvar_imagem=False,
    formatos_graficos=["svg", "png"],
    fator_deformada=10,
    impressao_tabela="resumida",
    animacao_deformada=False,
    exportar_planilha_resultados=False,
    gerar_log=False,
    label_x="Largura da Estrutura (cm)",
    label_y="Altura da Estrutura (cm)",
)
