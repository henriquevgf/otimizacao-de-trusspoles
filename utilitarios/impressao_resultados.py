from utilitarios.geral import ordenar_id_barra
import matplotlib.pyplot as plt
import matplotlib as mpl
from utilitarios.constantes import REPOSITORIO_IMAGENS, REPOSITORIO_GIFS
from utilitarios.classes import EstruturaComMetadados
import os
import imageio
from PIL import Image
from re import sub


def exibir_resultados_graficos(
    estrutura: EstruturaComMetadados,
    nome_hipotese: str = "Hipótese",
    imprimir_estrutura: bool = True,
    imprimir_esforcos_axiais: bool = False,
    imprimir_deformada: bool = False,
    imprimir_reacoes_apoio: bool = False,
    mostrar_na_tela: bool = True,
    salvar_imagem: bool = True,
    formatos: list[str] = ["png", "svg"],
    fator_deformada: float = 1.0,
    animacao_deformada: bool = False,
    verbosity: int = 0,
    titulo_personalizado: str | None = None,
    label_x: str | None = None,
    label_y: str | None = None,
    diretorio_override: str | None = None,
    dpi_override: int | None = None,
) -> None:
    """
    Exibe ou salva os gráficos personalizados de uma estrutura resolvida.

    Gera visualizações da estrutura, esforços axiais, deformada e reações de apoio.
    Também pode gerar um GIF animado da configuração deformada, com steps definidos automaticamente
    a partir do fator máximo especificado.

    O diretório onde os arquivos serão salvos pode ser sobrescrito com o argumento `diretorio_override`.
    Isso permite redirecionar as imagens para um caminho alternativo sem afetar a lógica padrão.

    Args:
        estrutura (EstruturaComMetadados): Estrutura resolvida (objeto anaStruct customizado).
        nome_hipotese (str): Título dos gráficos e base para os nomes dos arquivos.
        imprimir_estrutura (bool): Se True, gera imagem da estrutura.
        imprimir_esforcos_axiais (bool): Se True, gera gráfico dos esforços normais.
        imprimir_deformada (bool): Se True, gera imagem da configuração deformada.
        imprimir_reacoes_apoio (bool): Se True, gera gráfico das reações nos apoios.
        mostrar_na_tela (bool): Se True, exibe os gráficos com plt.show().
        salvar_imagem (bool): Se True, salva os gráficos nos formatos indicados.
        formatos (list[str]): Lista de formatos a salvar (ex: ["png", "svg"]).
        fator_deformada (float): Fator de escala para a deformada.
            Usado tanto na visualização estática quanto como valor máximo da animação, se ativada.
        animacao_deformada (bool): Se True, gera um GIF animado da deformada no intervalo 0%–100%.
        verbosity (int): Nível de detalhamento nos gráficos (0 = com rótulos, 1 = sem rótulos).
        titulo_personalizado (str | None): Título alternativo a ser exibido nos gráficos. Se None, usa nome_hipotese.
        label_x (str | None): Rótulo do eixo X nos gráficos. Se None, usa o padrão do Matplotlib.
        label_y (str | None): Rótulo do eixo Y nos gráficos. Se None, usa o padrão do Matplotlib.
        diretorio_override (str | None): Caminho alternativo para salvar as imagens.
            Se None, utiliza o diretório padrão definido por REPOSITORIO_IMAGENS.
        dpi_override (int | None): Valor de DPI a ser usado ao salvar as imagens. Se None, usa o padrão (300 dpi).
            Útil para reduzir a resolução e o consumo de memória em aplicações como geração de vídeos.
    """
    def _personalizar(fig, titulo, tamanho_forca=10, tamanho_outros=10):
        ax = fig.axes[0]
        ax.set_title(titulo, fontsize=14, fontweight="bold")
        if label_x:
            ax.set_xlabel(label_x, fontsize=12)
        if label_y:
            ax.set_ylabel(label_y, fontsize=12)
        ax.grid(False)

        for text in ax.texts:
            conteudo = text.get_text().strip()
            if conteudo.startswith("F="):
                try:
                    valor = float(conteudo.replace("F=", "").strip())
                    text.set_text(f"F={valor:.2f}")
                    text.set_fontsize(tamanho_forca)
                except ValueError:
                    pass
            else:
                try:
                    float(conteudo)
                    text.set_fontsize(tamanho_outros)
                except ValueError:
                    continue
        plt.tight_layout()

    def _mostrar_e_ou_salvar(fig, nome_saida):
        if mostrar_na_tela:
            plt.show()
        if salvar_imagem:
            for fmt in formatos:
                if fmt == "svg":
                    mpl.rcParams["svg.fonttype"] = "none"
                repositorio = diretorio_override or REPOSITORIO_IMAGENS
                caminho = os.path.join(repositorio, f"{nome_saida}.{fmt}")
                dpi_efetivo = dpi_override if dpi_override is not None else 300
                fig.savefig(caminho, dpi=dpi_efetivo, format=fmt)
            plt.close(fig)
        elif not mostrar_na_tela:
            plt.close(fig)

    if imprimir_estrutura:
        fig = estrutura.show_structure(show=False, verbosity=verbosity)
        _personalizar(fig, titulo_personalizado or f"Estrutura - {nome_hipotese}", label_x, label_y)
        _mostrar_e_ou_salvar(fig, f"estrutura_{nome_hipotese}")

    if imprimir_esforcos_axiais:
        fig = estrutura.show_axial_force(show=False)
        _personalizar(fig, f"Esforços normais - {nome_hipotese}", label_x, label_y)
        _mostrar_e_ou_salvar(fig, f"esforcos_{nome_hipotese}")

    if imprimir_deformada:
        fig = estrutura.show_displacement(factor=fator_deformada, show=False)
        _personalizar(fig, f"Configuração deformada - {nome_hipotese}", label_x, label_y)
        _mostrar_e_ou_salvar(fig, f"deformada_{nome_hipotese}")

    if imprimir_reacoes_apoio:
        fig = estrutura.show_reaction_force(show=False)
        _personalizar(fig, f"Reações de Apoio - {nome_hipotese}", label_x, label_y)
        _mostrar_e_ou_salvar(fig, f"reacoes_{nome_hipotese}")

    if animacao_deformada:
        gerar_animacao_deformada(
            estrutura=estrutura,
            nome_hipotese=nome_hipotese,
            fator_maximo_deformada=fator_deformada,
            quantidade_steps=5,
            nome_gif=f"gif_deformada_{nome_hipotese}.gif"
        )

def gerar_animacao_deformada(
    estrutura: EstruturaComMetadados,
    nome_hipotese: str = "Hipótese",
    fator_maximo_deformada: float = 8.0,
    quantidade_steps: int = 4,
    nome_gif: str = None,
    acumular_para_combinado: bool = False,
    lista_frames_combinado: list[str] = None,
    duracao: float = 0.6,
) -> None:
    """
    Gera uma animação GIF da deformada da estrutura na ordem 0 → ida → volta ← 0.

    Args:
        estrutura (EstruturaComMetadados): Estrutura resolvida.
        nome_hipotese (str): Nome da hipótese para títulos e arquivos.
        fator_maximo_deformada (float): Valor máximo do fator de escala da deformada.
        quantidade_steps (int): Quantidade de steps intermediários entre 0 e o fator máximo.
        nome_gif (str): Nome do arquivo GIF final (opcional, gerado automaticamente se None).
        acumular_para_combinado (bool): Se True, adiciona os frames à lista externa.
        lista_frames_combinado (list[str]): Lista acumuladora dos caminhos dos frames.
        duracao (float): Duração de cada frame no GIF, em segundos.
    """
    if acumular_para_combinado and lista_frames_combinado is None:
        raise ValueError("Se acumular_para_combinado=True, forneça lista_frames_combinado.")

    # Sanitiza o nome da hipótese para uso seguro em arquivos
    nome_hipotese_limpo = sub(r'\W+', '_', nome_hipotese).strip('_')
    if nome_gif is None:
        nome_gif = f"gif_deformada_{nome_hipotese_limpo}.gif"

    print(f"🟡 Gerando GIF da deformada para a hipótese: {nome_hipotese}...")

    # Geração dos fatores de escala (de 0 até o máximo)
    fatores_escala = [round(i * fator_maximo_deformada / quantidade_steps, 6) for i in range(quantidade_steps + 1)]
    arquivos_png = []

    for fator in fatores_escala:
        fig = estrutura.show_displacement(factor=fator, show=False)
        ax = fig.axes[0]
        titulo = f"Configuração Deformada (x{fator}) - {nome_hipotese}"
        ax.set_title(titulo, fontsize=14, fontweight="bold")
        plt.tight_layout()

        nome_arquivo = f"deformada_{nome_hipotese_limpo}_escala{fator}.png"
        caminho = os.path.join(REPOSITORIO_GIFS, nome_arquivo)
        fig.savefig(caminho, dpi=300)
        arquivos_png.append(caminho)

        if acumular_para_combinado:
            lista_frames_combinado.append(caminho)

        plt.close(fig)

    # Criação do GIF: 0 → ida → volta ← 0 (não repete 0 no fim)
    imagens = [imageio.imread(arquivos_png[0])]  # quadro inicial
    imagens += [imageio.imread(arq) for arq in arquivos_png[1:]]  # ida
    imagens += [imageio.imread(arq) for arq in arquivos_png[-2:0:-1]]  # volta

    caminho_gif = os.path.join(REPOSITORIO_GIFS, nome_gif)
    imageio.mimsave(caminho_gif, imagens, duration=duracao, loop=0)

    # Remove imagens intermediárias (exceto se estiver acumulando para o combinado)
    if not acumular_para_combinado:
        for caminho in arquivos_png:
            if os.path.exists(caminho):
                os.remove(caminho)

    print(f"✅ GIF salvo em: {caminho_gif}")

def gerar_gif_combinado_final(
    nome_saida: str = "gif_deformadas_todas_hipoteses.gif",
        duracao: float = 0.6,
        sufixo_filtragem: str | None = None
) -> None:
    """
    Combina todos os GIFs individuais de deformada salvos no repositório de imagens
    em um único GIF animado.

    A sequência dos frames respeita a ordem de animação completa de cada hipótese
    (ex: 0-2-4-6-8-6-4-2), e os GIFs são processados em ordem alfabética pelo nome.

    Args:
        nome_saida (str): Nome do arquivo GIF final gerado.
        duracao (float): Duração de cada frame no GIF combinado, em segundos.
    """
    arquivos_gif = sorted([
        arq for arq in os.listdir(REPOSITORIO_GIFS)
        if arq.startswith("gif_deformada_")
        and arq.endswith(".gif")
        and (sufixo_filtragem is None and "_verificacao" not in arq
             or sufixo_filtragem is not None and sufixo_filtragem in arq)
    ])

    if not arquivos_gif:
        print("Nenhum GIF individual de deformada foi encontrado.")
        return

    frames_combinados = []
    tamanhos_detectados = set()

    print("🟡 Gerando GIF combinado de todas as hipóteses...")

    # === Lê e acumula os frames de todos os GIFs ===
    for gif_nome in arquivos_gif:
        caminho = os.path.join(REPOSITORIO_GIFS, gif_nome)
        try:
            with imageio.get_reader(caminho) as leitor:
                for frame in leitor:
                    img_pil = Image.fromarray(frame)
                    tamanhos_detectados.add(img_pil.size)
                    frames_combinados.append(img_pil)
        except Exception as e:
            print(f"Erro ao ler {caminho}: {e}")

    # === Salva o GIF final ===
    caminho_saida = os.path.join(REPOSITORIO_GIFS, nome_saida)
    frames_combinados[0].save(
        caminho_saida,
        save_all=True,
        append_images=frames_combinados[1:],
        duration=int(duracao * 1000),
        loop=0
    )
    print(f"✅ GIF combinado salvo em: {caminho_saida}")


def forca_axial_adm_com_sinal(caso: dict) -> float:
    """
    Retorna o valor da força axial admissível com o sinal coerente ao tipo de solicitação da barra.

    Se a barra estiver em tração, retorna o valor positivo da força axial admissível.
    Se estiver em compressão, retorna o valor negativo.
    Caso o valor da força admissível não esteja presente no dicionário, retorna 0.0 para evitar erros de formatação.

    Args:
        caso (dict): Dicionário com os dados do caso de dimensionamento, incluindo as chaves
            "forca_axial_admissivel" e "solicitacao".

    Returns:
        float: Valor da força axial admissível com sinal adequado, ou 0.0 se ausente.
    """
    forca_axial_admissivel = caso.get("forca_axial_admissivel")
    if forca_axial_admissivel is None:
        return 0.0

    return (
        -forca_axial_admissivel
        if caso.get("solicitacao") == "compressao"
        else forca_axial_admissivel
    )


def formatar_forca_axial(valor: float, forca_simulada: bool) -> str:
    """
    Retorna a força axial formatada como string com duas casas decimais e sinal explícito, alinhada à direita.

    Quando `forca_simulada` for True e o valor absoluto da força for muito pequeno (< 0.011),
    força a exibição como ±0.00 para indicar uma simulação de ausência de força, mantendo o sinal.

    Args:
        valor (float): Valor da força axial (em kgf) a ser formatado.
        forca_simulada (bool): Indica se a força foi artificialmente simulada como próxima de zero.

    Returns:
        str: Força formatada como texto com sinal e 2 casas decimais, com 8 caracteres de largura.
    """
    valor = float(valor)

    if forca_simulada and abs(valor) < 0.011:
        return f"{-0.0:+.2f}".rjust(8) if valor < 0 else f"{0.0:+.2f}".rjust(8)

    return f"{valor:>8.2f}"


def imprimir_tabela_resultados(
    resultados: dict,
    ids_ligacao_necessaria: set | list,
    df_montantes=None,
    df_diagonais_horizontais=None,
) -> None:
    """
    Imprime a tabela final de dimensionamento das barras estruturais.

    A tabela apresenta, para cada barra, uma linha com a hipótese de tração (incluindo
    dados geométricos, perfil, ligação e taxa de trabalho) e outra com a hipótese de compressão
    (complementando com o tipo de aço e dados da ligação). Perfis simulados são tratados
    com sinal correto e exibidos com força igual a ±0.00.

    Os dados devem ter sido previamente processados no módulo de dimensionamento, contendo:
    - 'hipotese_tracao', 'hipotese_compressao'
    - 'perfil_escolhido', 'taxa_trabalho_final', 'tx_lig_final'
    - dados por hipótese com: 'forca_axial', 'area_bruta', 'raio', 'verificacao_ligacao', etc.

    Args:
        resultados (dict): Dicionário com os dados finais de dimensionamento, organizados por ID da barra.
        ids_ligacao_necessaria (set | list): IDs das barras (montantes) que obrigatoriamente devem ter ligação.
        df_montantes: DataFrame com os perfis dos montantes.
        df_diagonais_horizontais: DataFrame com os perfis das diagonais e horizontais.

    Returns:
        None
    """

    # === 1. Impressão do cabeçalho da tabela ===
    print("=" * 180)
    print(f"{'VERIFICAÇÃO DOS PERFILADOS E LIGAÇÕES'.center(180)}")
    print("=" * 180)
    print(
        "NB *     Tipo      *     HIP     *     FMAX   *   L    *    Lef  *    α   *     PERFIL    *     R      *    A    *  ESB   *     NA    *   NP  *    D  *  SD *  FCA   *  FEA   *   %"
    )
    print(
        "                                       (kgf)     (cm)      (cm)      (°)                       (cm)       (cm²)                (kgf)                          (kgf)    (kgf)      "
    )
    print("-" * 180)

    # === 2. Loop pelas barras ordenadas ===
    for nb in sorted(resultados.keys(), key=ordenar_id_barra):
        dados = resultados[nb]

        # === 3. Recupera diretamente os nomes das hipóteses de tração e compressão ===
        nome_hipotese_tracao = dados.get("hipotese_tracao")
        nome_hipotese_compressao = dados.get("hipotese_compressao")

        resultado_tracao = dados.get(nome_hipotese_tracao)
        resultado_compressao = dados.get(nome_hipotese_compressao)

        pior = dados.get("pior_caso")

        # Substitui nomes de hipóteses simuladas por string vazia para exibição
        if nome_hipotese_tracao in {"hip_0_t", "hip_0_c"}:
            nome_hipotese_tracao = ""

        if nome_hipotese_compressao in {"hip_0_t", "hip_0_c"}:
            nome_hipotese_compressao = ""

        # === 4. Aplicação dos dados do perfil final nas hipóteses ===
        perfil = dados.get("perfil_escolhido", "")
        perfil_final = dados.get("perfil_escolhido")

        for r in [resultado_tracao, resultado_compressao]:
            if r is None:
                continue
            if r.get("perfil_escolhido") == perfil_final:
                # Já é o perfil certo, nada a fazer
                continue
            else:
                # Procurar outra hipótese (qualquer nome) onde o perfil final foi avaliado
                for hip_nome, hip in dados.items():
                    if not isinstance(hip, dict):
                        continue
                    if hip.get("perfil_escolhido") == perfil_final:
                        for campo in [
                            "raio",
                            "area_bruta",
                            "area_efetiva",
                            "esbeltez_corrigida",
                            "forca_axial_admissivel",
                            "taxa_trabalho",
                        ]:
                            if campo in hip:
                                r[campo] = hip[campo]

        # === 5. Aplicação dos comprimentos reais e destravados do caso crítico ===
        dados_pior = dados.get(pior, {})
        campos_comprimento = ["comprimento", "comprimento_destravado"]

        for resultado in [resultado_tracao, resultado_compressao]:
            if not resultado:
                continue
            for campo in campos_comprimento:
                valor = dados_pior.get(campo)
                if valor is not None:
                    resultado[campo] = valor

        # === 6. Cálculo da taxa de utilização e forças admissíveis com sinal ===
        taxa_utilizacao_percentual = round(dados["taxa_trabalho_final"], 3) * 100

        forca_adm_tracao = forca_axial_adm_com_sinal(resultado_tracao) if resultado_tracao else 0.0
        forca_adm_compressao = (
            forca_axial_adm_com_sinal(resultado_compressao) if resultado_compressao else 0.0
        )

        # === 7. Verificação e formatação dos dados de ligação ===
        hipotese_ligacao = dados.get("pior_ligacao", dados.get("pior_caso"))
        verificacao_ligacao = dados.get(hipotese_ligacao, {}).get("verificacao_ligacao", {})

        tipo = resultado_tracao.get("tipo", "") if resultado_tracao else ""
        barra_deve_ter_ligacao = (
            tipo.startswith("diagonal")
            or tipo.startswith("horizontal")
            or nb in ids_ligacao_necessaria
        )

        if not barra_deve_ter_ligacao or not verificacao_ligacao.get("ligacao_viavel", False):
            np_txt = d_txt = sd_txt = fca_txt = fea_txt = tx_lig_txt = ""
        else:
            np = verificacao_ligacao.get("np", "")
            d = verificacao_ligacao.get("d_furo", "")
            sd = verificacao_ligacao.get("planos", "")
            fca = verificacao_ligacao.get("forca_adm_cisalhamento", "")
            fea = verificacao_ligacao.get("forca_adm_esmagamento", "")
            tx_lig = dados.get("tx_lig_final", verificacao_ligacao.get("tx_lig", 0))
            fator_fp = verificacao_ligacao.get("fator_fp", "")

            np_txt = str(np) if np != "" else ""
            d_txt = f"{d * 10:.1f}" if isinstance(d, (int, float)) else ""
            sd_txt = str(sd) if sd != "" else ""
            fca_txt = f"{fca:.0f}" if isinstance(fca, (int, float)) else ""
            fea_txt = f"{fea:.0f}" if isinstance(fea, (int, float)) else ""
            tx_lig_txt = f"{tx_lig * 100:.1f}" if isinstance(tx_lig, (int, float)) else ""
            fator_fp_txt = (
                "1.25*Fu"
                if isinstance(fator_fp, (int, float)) and abs(fator_fp - 1.25) < 1e-4
                else ""
            )

        # === 8. Recuperação do aço do perfil para impressão ===
        aco_utilizado = ""

        for df in (df_montantes, df_diagonais_horizontais):
            linha = df[df["Perfil"] == perfil]
            if not linha.empty:
                aco_utilizado = linha.iloc[0].get("Aço", "")
                break

        # === 9. Impressão da linha da hipótese de tração ===
        if resultado_tracao:
            forca_simulada = resultado_tracao.get("simulada", False)

            print(
                f"{nb:<4} {resultado_tracao.get('tipo', ''):<16}    {nome_hipotese_tracao or '':<9} "
                f"{formatar_forca_axial(resultado_tracao.get('forca_axial', 0), forca_simulada):>10}"
                f"{(resultado_tracao.get('comprimento') or 0):>10.1f}   "
                f"{(resultado_tracao.get('comprimento_destravado') or resultado_tracao.get('comprimento') or 0):>6.1f}   "
                f"{(resultado_tracao.get('alfa') or 0):>7.1f}   {perfil:<14}   "
                f"{(resultado_tracao.get('raio') or 0):>6.3f}     "
                f"{(resultado_tracao.get('area_bruta') or 0):>7.3f}  "
                f"{(resultado_tracao.get('esbeltez_corrigida') or resultado_tracao.get('esbeltez_tracao') or 0):>7.2f}   "
                f"{forca_adm_tracao:>9.2f}   {np_txt:>3} {d_txt:>10} {sd_txt:>3}   "
                f"{fca_txt:>6}  {fea_txt:>6}   {taxa_utilizacao_percentual:>6.1f}"
            )

            # === 10. Impressão da linha da hipótese de compressão ===
            forca_simulada = resultado_compressao.get("simulada", False)
            print(
                f"{'':<4} {'':<16}    {nome_hipotese_compressao or '':<9} "
                f"{formatar_forca_axial(resultado_compressao.get('forca_axial', 0), forca_simulada):>10}"
                f"{'':>10}   {'':>6}   {'':>7}   {aco_utilizado:<14}   {'':>6}     "
                f"{(resultado_compressao.get('area_efetiva') or 0):>7.3f}   {'':>7}  "
                f"{forca_adm_compressao:>9.2f}   {'':>3} {fator_fp_txt:>10} {'':>3} "
                f"{'':>6} {'':>6}      {tx_lig_txt:>6}"
            )

        # === 11. Linha separadora entre barras ===
        print("-" * 180)

def imprimir_tabela_resultados_resumida(
    resultados: dict,
    ids_ligacao_necessaria: set | list,
    df_montantes=None,
    df_diagonais_horizontais=None,
) -> None:
    """
    Imprime a versão resumida da tabela final de dimensionamento das barras estruturais.

    Esta versão remove as colunas “Tipo”, “α” e o comprimento real (`L`), deixando
    apenas o comprimento destravado (`Lef`). Além disso, substitui o número da barra (`NB`)
    por um identificador compacto, que facilita a leitura e localização:

    - Montante esquerdo   →  M1e, M2e, ...
    - Montante direito    →  M1d, M2d, ...
    - Horizontal          →  H1, H2, ...
    - Diagonal            →  D1, D2, ...

    A tabela é formatada para ocupar menos largura e simplificar a interpretação,
    mantendo apenas os valores relevantes para análise estrutural.

    Args:
        resultados (dict):
            Dicionário com os dados finais de dimensionamento, organizados por ID da barra.
            Contém informações de tração, compressão, perfil escolhido, ligações, etc.
        ids_ligacao_necessaria (set | list):
            Conjunto ou lista de IDs de barras que obrigatoriamente devem ter ligação.
        df_montantes (pd.DataFrame, optional):
            DataFrame contendo os perfis de montantes e suas propriedades.
        df_diagonais_horizontais (pd.DataFrame, optional):
            DataFrame contendo os perfis de diagonais e horizontais.

    Returns:
        None: A tabela é impressa diretamente no console.

    Raises:
        KeyError: Se algum campo esperado não for encontrado no dicionário de resultados.
        ValueError: Se houver inconsistências nos dados dos perfis.

    Notes:
        - A coluna de comprimento real (L) foi removida; apenas o comprimento destravado (Lef) é exibido.
        - Os identificadores são gerados com base no tipo e no número da barra (ex.: M1e, D5, H3).
        - A impressão é centralizada para melhor leitura.
        - A função espera que os DataFrames de perfis estejam devidamente carregados e validados.
    """

    # === 1. Cabeçalho resumido ===
    print("=" * 133)
    print(f"{'VERIFICAÇÃO DOS PERFILADOS E LIGAÇÕES'.center(133)}")
    print("=" * 133)
    print(
        "NB    *   HIP   *    FMAX   *  Lef  *      PERFIL      *"
        "   R   *   A   *  ESB   *     NA     * NP *   D  * SD"
        " *  FCA  *  FEA  *    %"
    )
    print(
        "                     (kgf)     (cm)                       "
        "(cm)   (cm²)               (kgf)                      "
        "(kgf)   (kgf)      "
    )
    print("-" * 133)

    # === 1.b  Contadores para gerar M1e / M1d / H1 / D1 ===
    #seq = dict(montante_esq=1, montante_dir=1, horizontal=1, diagonal=1)

    # === 2. Loop pelas barras ordenadas ===
    for nb in sorted(resultados.keys(), key=ordenar_id_barra):
        dados = resultados[nb]

        # === 3. Recupera diretamente os nomes das hipóteses de tração e compressão ===
        nome_hipotese_tracao = dados.get("hipotese_tracao")
        nome_hipotese_compressao = dados.get("hipotese_compressao")

        resultado_tracao = dados.get(nome_hipotese_tracao)
        resultado_compressao = dados.get(nome_hipotese_compressao)

        pior = dados.get("pior_caso")

        # Substitui nomes de hipóteses simuladas por string vazia para exibição
        if nome_hipotese_tracao in {"hip_0_t", "hip_0_c"}:
            nome_hipotese_tracao = ""

        if nome_hipotese_compressao in {"hip_0_t", "hip_0_c"}:
            nome_hipotese_compressao = ""

        # === 4. Aplicação dos dados do perfil final nas hipóteses ===
        perfil = dados.get("perfil_escolhido", "")
        perfil_final = dados.get("perfil_escolhido")

        for r in [resultado_tracao, resultado_compressao]:
            if r is None:
                continue
            if r.get("perfil_escolhido") == perfil_final:
                # Já é o perfil certo, nada a fazer
                continue
            else:
                # Procurar outra hipótese (qualquer nome) onde o perfil final foi avaliado
                for hip_nome, hip in dados.items():
                    if not isinstance(hip, dict):
                        continue
                    if hip.get("perfil_escolhido") == perfil_final:
                        for campo in [
                            "raio",
                            "area_bruta",
                            "area_efetiva",
                            "esbeltez_corrigida",
                            "forca_axial_admissivel",
                            "taxa_trabalho",
                        ]:
                            if campo in hip:
                                r[campo] = hip[campo]

        # === 5. Aplicação do comprimento destravado do caso crítico ===
        dados_pior = dados.get(pior, {})
        # Apenas o comprimento destravado
        valor_lef = dados_pior.get("comprimento_destravado")

        for resultado in [resultado_tracao, resultado_compressao]:
            if not resultado:
                continue
            if valor_lef is not None:
                resultado["comprimento_destravado"] = valor_lef

        # === 6. Cálculo da taxa de utilização e forças admissíveis com sinal ===
        taxa_utilizacao_percentual = round(dados["taxa_trabalho_final"], 3) * 100

        forca_adm_tracao = forca_axial_adm_com_sinal(resultado_tracao) if resultado_tracao else 0.0
        forca_adm_compressao = (
            forca_axial_adm_com_sinal(resultado_compressao) if resultado_compressao else 0.0
        )

        # === 7. Verificação e formatação dos dados de ligação ===
        hipotese_ligacao = dados.get("pior_ligacao", dados.get("pior_caso"))
        verificacao_ligacao = dados.get(hipotese_ligacao, {}).get("verificacao_ligacao", {})

        tipo = resultado_tracao.get("tipo", "") if resultado_tracao else ""
        barra_deve_ter_ligacao = (
            tipo.startswith("diagonal")
            or tipo.startswith("horizontal")
            or nb in ids_ligacao_necessaria
        )

        if not barra_deve_ter_ligacao or not verificacao_ligacao.get("ligacao_viavel", False):
            np_txt = d_txt = sd_txt = fca_txt = fea_txt = tx_lig_txt = ""
        else:
            np = verificacao_ligacao.get("np", "")
            d = verificacao_ligacao.get("d_furo", "")
            sd = verificacao_ligacao.get("planos", "")
            fca = verificacao_ligacao.get("forca_adm_cisalhamento", "")
            fea = verificacao_ligacao.get("forca_adm_esmagamento", "")
            tx_lig = dados.get("tx_lig_final", verificacao_ligacao.get("tx_lig", 0))
            fator_fp = verificacao_ligacao.get("fator_fp", "")

            np_txt = str(np) if np != "" else ""
            d_txt = f"{d * 10:.1f}" if isinstance(d, (int, float)) else ""
            sd_txt = str(sd) if sd != "" else ""
            fca_txt = f"{fca:.0f}" if isinstance(fca, (int, float)) else ""
            fea_txt = f"{fea:.0f}" if isinstance(fea, (int, float)) else ""
            tx_lig_txt = f"{tx_lig * 100:.1f}" if isinstance(tx_lig, (int, float)) else ""
            fator_fp_txt = (
                "1.25*Fu"
                if isinstance(fator_fp, (int, float)) and abs(fator_fp - 1.25) < 1e-4
                else ""
            )

        # === 8. Recuperação do aço do perfil para impressão ===
        aco_utilizado = ""

        for df in (df_montantes, df_diagonais_horizontais):
            linha = df[df["Perfil"] == perfil]
            if not linha.empty:
                aco_utilizado = linha.iloc[0].get("Aço", "")
                break

        # === 9. Identificador compacto + impressão resumida ================

        # 9.1 – gera M1e / M1d / H1 / D1 …
        #if "esq" in tipo:
        #    id_barra = f"M{seq['montante_esq']}e"; seq['montante_esq'] += 1
        #elif "dir" in tipo:
        #    id_barra = f"M{seq['montante_dir']}d"; seq['montante_dir'] += 1
        #elif "horizontal" in tipo:
        #    id_barra = f"H{seq['horizontal']}";     seq['horizontal']   += 1
        #elif "diagonal" in tipo:
        #    id_barra = f"D{seq['diagonal']}";       seq['diagonal']     += 1
        #else:
        #    id_barra = str(nb)                      # fallback raro

        # 9.1 – gera D16, H23, M16e, M17d ...
        if "esq" in tipo:
            id_barra = f"M{nb}e"
        elif "dir" in tipo:
            id_barra = f"M{nb}d"
        elif "horizontal" in tipo:
            id_barra = f"H{nb}"
        elif "diagonal" in tipo:
            id_barra = f"D{nb}"
        else:
            id_barra = str(nb)          # fallback (caso apareça outro tipo)

        # 9.2 – linha da hipótese de tração  (SEM colunas “Tipo” e “α”)
        if resultado_tracao:
            forca_simulada = resultado_tracao.get("simulada", False)
            print(
                f"{id_barra:<7} "
                f"{(nome_hipotese_tracao or ''):^9}"
                f"{formatar_forca_axial(resultado_tracao.get('forca_axial', 0), forca_simulada):>10}"
                f"{(resultado_tracao.get('comprimento_destravado') or resultado_tracao.get('comprimento') or 0):>8.1f}   "
                f"{perfil:<14}"
                f"{(resultado_tracao.get('raio') or 0):>10.3f}"
                f"{(resultado_tracao.get('area_bruta') or 0):>8.3f}"
                f"{(resultado_tracao.get('esbeltez_corrigida') or resultado_tracao.get('esbeltez_tracao') or 0):>9.2f}"
                f"{forca_adm_tracao:>13.2f} "
                f"{np_txt:>4}{d_txt:>7}{sd_txt:>4}"
                f"{fca_txt:>9}{fea_txt:>8}{taxa_utilizacao_percentual:>8.1f}"
            )

            # 9.3 – linha da hipótese de compressão
            forca_simulada = resultado_compressao.get("simulada", False)
            print(
                f"{'':<7} "
                f"{(nome_hipotese_compressao or ''):^9}"
                f"{formatar_forca_axial(resultado_compressao.get('forca_axial', 0), forca_simulada):>10}"
                f"{'':>8}   "
                f"{aco_utilizado:<14}"
                f"{'':>10}"
                f"{(resultado_compressao.get('area_efetiva') or 0):>8.3f}"
                f"{'':>9}"
                f"{forca_adm_compressao:>13.2f} "
                f"{'':>4}{fator_fp_txt:>7}{'':>4}"
                f"{'':>9}{'':>8}{tx_lig_txt:>8}"
            )

        # === 10. Linha separadora ===
        print("-" * 133)