def ordenar_id_barra(id_barra: str | int) -> tuple[int, str]:
    """
    Gera uma chave de ordenação natural a partir de um identificador de barra.

    Se o ID contiver um número seguido de letras (ex: '12b'), a função separa as partes e retorna uma tupla.
    Isso facilita a ordenação alfanumérica correta (ex: '2a', '2b', '10').

    Args:
        id_barra (str | int): Identificador da barra, como um número inteiro (ex: 5)
                              ou uma string com parte numérica e sufixo (ex: '6a').

    Returns:
        tuple[int, str]: Tupla com a parte numérica como inteiro e o sufixo como string.

    Exemplos:
        >>> ordenar_id_barra("12b")
        (12, 'b')
        >>> ordenar_id_barra(5)
        (5, '')
    """
    if isinstance(id_barra, int):
        return (id_barra, '')
    num = int(''.join(filter(lambda c: c.isdigit(), str(id_barra))))
    suf = ''.join(filter(lambda c: c.isalpha(), str(id_barra)))
    return (num, suf)


def divisao_segura(numerador: float, denominador: float) -> float:
    """Retorna o resultado da divisão ou infinito se o denominador for zero ou inválido.

    Args:
        numerador (float): Valor do numerador.
        denominador (float): Valor do denominador.

    Returns:
        float: Resultado da divisão (numerador / denominador) ou infinito.
    """
    return numerador / denominador if denominador else float("inf")
