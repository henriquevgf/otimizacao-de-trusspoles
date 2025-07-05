"""
Constantes globais do projeto de otimização estrutural de Trusspoles.

Contém parâmetros normativos, materiais e computacionais utilizados em múltiplos módulos
para análise, dimensionamento e otimização estrutural.
"""

# ------------------------------
# Constantes Normativas (ASCE 10-15)
# ------------------------------

# Limites de esbeltez (L/r)
LIMITE_ESBELTEZ_TRACAO = 375  # Para barras exclusivamente tracionadas
LIMITE_ESBELTEZ_MONTANTE = 150  # Para montantes comprimidos
LIMITE_ESBELTEZ_DIAG_HORIZ = 200  # Para diagonais e horizontais comprimidos

# ------------------------------
# Constantes Computacionais
# ------------------------------

# Comprimento máximo do menor tramo dos montantes para consideração como critério de parada do algoritmo
LIMITE_TRAMO = 50  # em cm

# Quantidade limite de diagonais na face de cada mmódulo
MAX_DIAGONAIS = 30

# Módulo de elasticidade do aço (kgf/cm²)
MODULO_ELASTICIDADE_ACO = 2_038_894

# Coeficiente de minoração padrão
COEF_MINORACAO_PADRAO = 0.90

# Coeficiente de majoração das cargas de peso próprio
COEF_MAJORACAO_PESO_PROPRIO = 1.30

# Coeficiente de majoração das forças horizontais
COEF_MAJORACAO_FORCAS_HORIZONTAIS = 1.00

# Peso próprio inicial atribuído por módulo, se nenhum valor for fornecido
PESO_PROPRIO_INICIAL_PADRAO = 41  # kgf

# Limite da taxa de trabalho para diagonais e horizontais (critério adicional de desempenho)
LIMITE_TAXA_TRABALHO_DIAG_HORIZ = 0.90  # 90%

# Fator de esmagamento padrão
# Derivado de 1,3 / 1,2 conforme critério normativo
FATOR_ESMAGAMENTO_PADRAO = 1.3 / 1.2  # ≈ 1.083333...

# Caminho base onde os gráficos devem ser salvos
REPOSITORIO_IMAGENS = r"D:\ajuste o caminho aqui\algoritmo_otimizacao\repositorio de imagens"

# Caminho base onde as imagens temporárias e vídeos propriamente ditos devem ser salvos
REPOSITORIO_VIDEOS = r"D:\ajuste o caminho aqui\algoritmo_otimizacao\repositorio de videos"

# Caminho base onde as imagens temporárias e gifs devem ser salvos
REPOSITORIO_GIFS = r"D:\ajuste o caminho aqui\algoritmo_otimizacao\repositorio de gifs"

# Caminho base onde as planilhas geradas devem ser salvos
REPOSITORIO_PLANILHAS = r"D:\ajuste o caminho aqui\algoritmo_otimizacao\repositorio de planilhas"

# Caminho base onde os logs de execução devem ser salvos
REPOSITORIO_LOGS = r"D:\ajuste o caminho aqui\algoritmo_otimizacao\logs"