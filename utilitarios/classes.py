from anastruct import SystemElements


class EstruturaComMetadados(SystemElements):
    """
    Subclasse de SystemElements com suporte a atributos personalizados
    usados no projeto de otimização estrutural.

    Atributos adicionais:
        contador_barras (int): ID incremental para cada barra adicionada.
        metadados_barras (dict): Dicionário com os metadados de cada barra.
        metadados_nos (dict): Metadados dos nós.
        nos (dict): Coordenadas dos nós, com IDs.
    """

    def __init__(self):
        super().__init__()
        self.contador_barras = 0
        self.metadados_barras = {}
        self.metadados_nos = {}
        self.nos = {}

class DuplicadorSaida:
    """
    Redireciona a saída para múltiplos destinos simultaneamente (ex: console e arquivo de log).

    Exemplo de uso com contextlib:
        with contextlib.redirect_stdout(DuplicadorSaida(sys.stdout, arquivo_log)):
            print("Essa mensagem vai para o console e para o arquivo.")
    """
    def __init__(self, *destinos):
        self.destinos = destinos

    def write(self, texto):
        for destino in self.destinos:
            destino.write(texto)
            destino.flush()

    def flush(self):
        for destino in self.destinos:
            destino.flush()