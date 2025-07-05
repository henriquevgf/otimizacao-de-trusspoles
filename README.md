# Otimização de Trusspoles

Este projeto implementa um conjunto de ferramentas em Python para modelagem, análise, dimensionamento e otimização de torres treliçadas modulares ("trusspoles").

O código foi desenvolvido para explorar diversas quantidades de diagonais por módulo e encontrar, de forma automática, a configuração estrutural com menor peso que atenda aos critérios normativos da ASCE 10‑15. As principais rotinas utilizam a biblioteca [anaStruct](https://github.com/ritchie46/anaStruct) para a análise de treliças.

## Funcionalidades principais

- **Geração paramétrica da geometria** (`gerador_estrutura.py`)
  - Criação dos nós e barras da torre a partir das alturas dos módulos, largura e número de divisões verticais.
  - Aplicação de cargas horizontais e verticais, incluindo peso próprio estimado.
  - Resolução das estruturas para múltiplas hipóteses de carregamento.

- **Dimensionamento de barras e ligações** (`dimensionamento.py`)
  - Verificação de tração, compressão e flexão simples, com limites de esbeltez distintos para montantes e diagonais.
  - Checagem de flambagem local, compatibilidade de furos e dimensionamento de ligações parafusadas.
  - Reforço iterativo dos montantes e uniformização dos perfis por módulo até convergência.

- **Otimização global da torre** (`otimizador.py`)
  - Teste exaustivo de diferentes combinações de diagonais por módulo.
  - Ajuste iterativo do peso próprio, recalculando cargas e esforços a cada ciclo.
  - Seleção automática da configuração de menor peso e geração opcional de gráficos, GIFs e planilhas.

- **Utilitários auxiliares** (`utilitarios/`)
  - Funções de análise estrutural, cálculo de comprimentos destravados, manipulação de planilhas Excel e geração de relatórios.
  - Módulo de visualização que produz imagens da estrutura, esforços, deformadas e reações.

## Estrutura de diretórios

```
├── dados/                         # Planilhas de perfis e materiais
├── utilitarios/                   # Módulos auxiliares usados em todo o projeto
├── repositorio de planilhas/      # Saída padrão das planilhas geradas
├── main.py                        # Exemplo de execução do otimizador
├── gerador_estrutura.py           # Rotinas de geração da malha estrutural
├── dimensionamento.py             # Algoritmo de dimensionamento das barras
├── otimizador.py                  # Loop de otimização da configuração final
```

Os caminhos para salvamento de imagens, GIFs, vídeos, planilhas e logs são configurados no arquivo `utilitarios/constantes.py`. Ajuste esses diretórios conforme a sua máquina antes de executar o código.

## Instalação

Recomenda‑se o uso do Python 3.10 ou superior. Instale as dependências básicas com:

```bash
pip install pandas anastruct matplotlib imageio pillow
```

A leitura e escrita de planilhas utiliza o `openpyxl`, instalado automaticamente pelo `pandas`.

## Como usar

O script `main.py` apresenta um exemplo completo de utilização. Basta executar:

```bash
python main.py
```

O otimizador irá:

1. Carregar as tabelas em `dados/`.
2. Gerar todas as combinações de diagonais permitidas.
3. Dimensionar as barras para cada hipótese de carregamento.
4. Selecionar a configuração de menor peso e exibir (ou salvar) os resultados.

As opções de visualização, salvamento de imagens, animações e exportação para planilha podem ser ajustadas nos argumentos da função `otimizar_estrutura` presente em `main.py` ou chamadas diretamente em outro script.

## Licença

Este projeto está licenciado sob a [GPL v2](LICENSE).

Contribuições são bem‑vindas! Abra uma *issue* ou *pull request* para sugestões ou correções.
