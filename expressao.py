"""
Parser de expressões aritméticas usado pelas calculadoras da AT03.

O mesmo arquivo é copiado para os quatro repositórios de calculadora
(socket, RMI/Pyro5, JSON-RPC e HTTP-REST), por isso não depende de nada
além da biblioteca padrão.

Como funciona:
  1. tokenizar()    -> quebra a string em números, operadores e parênteses;
  2. para_arvore()  -> monta uma árvore sintática por descida recursiva,
                       respeitando precedência (* e / antes de + e -),
                       parênteses e sinais unários (-3, -(2+1));
  3. avaliar()      -> percorre a árvore e, para cada operação básica,
                       chama um "executor" injetado.

O executor é o ponto que liga o parser à comunicação:
  - Modo A: o cliente passa um executor que faz a chamada remota
            (uma chamada ao servidor por operação básica);
  - Modo B: o servidor passa executor_local e calcula tudo sozinho.

Não usamos eval() nem exec() em nenhum momento.

Gramática (descida recursiva):
    expressao := termo (('+' | '-') termo)*
    termo     := fator (('*' | '/') fator)*
    fator     := ('+' | '-') fator | NUMERO | '(' expressao ')'
"""

# Símbolo do operador -> nome da operação remota.
OPERACOES = {
    "+": "soma",
    "-": "subtracao",
    "*": "multiplicacao",
    "/": "divisao",
}

# Nome da operação -> símbolo, usado para imprimir as chamadas.
SIMBOLOS = {nome: simbolo for simbolo, nome in OPERACOES.items()}


class ErroExpressao(ValueError):
    """Expressão mal formada (token desconhecido, parênteses etc.)."""


# ---------------------------------------------------------------------------
# 1. Tokenização
# ---------------------------------------------------------------------------

def tokenizar(expr: str) -> list:
    """Converte a string em uma lista de tokens.

    Números viram float; operadores e parênteses ficam como str.
    Exemplo: "(10 + 2.5)*4" -> ['(', 10.0, '+', 2.5, ')', '*', 4.0]
    """
    if not isinstance(expr, str):
        raise ErroExpressao("A expressão deve ser um texto.")

    tokens = []
    i = 0
    while i < len(expr):
        c = expr[i]
        if c.isspace():
            i += 1
        elif c.isdigit() or c == ".":
            inicio = i
            while i < len(expr) and (expr[i].isdigit() or expr[i] == "."):
                i += 1
            texto = expr[inicio:i]
            try:
                tokens.append(float(texto))
            except ValueError:
                raise ErroExpressao(f"Número inválido: '{texto}' (posição {inicio + 1}).")
        elif c in OPERACOES or c in "()":
            tokens.append(c)
            i += 1
        else:
            raise ErroExpressao(f"Caractere desconhecido: '{c}' (posição {i + 1}).")

    if not tokens:
        raise ErroExpressao("Expressão vazia.")
    return tokens


# ---------------------------------------------------------------------------
# 2. Árvore sintática
# ---------------------------------------------------------------------------
# Um nó é um float (folha) ou uma tupla (operacao, esquerda, direita),
# por exemplo ("multiplicacao", ("soma", 10.0, 15.0), 4.0).

class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def atual(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def consumir(self):
        token = self.atual()
        self.pos += 1
        return token

    def expressao(self):
        no = self.termo()
        while self.atual() in ("+", "-"):
            op = OPERACOES[self.consumir()]
            no = (op, no, self.termo())
        return no

    def termo(self):
        no = self.fator()
        while self.atual() in ("*", "/"):
            op = OPERACOES[self.consumir()]
            no = (op, no, self.fator())
        return no

    def fator(self):
        token = self.atual()
        if token is None:
            raise ErroExpressao("Expressão incompleta: faltou um número no final.")
        if token in ("+", "-"):
            self.consumir()
            operando = self.fator()
            if token == "+":
                return operando
            # Sinal em número literal vira o próprio número negativo;
            # em subexpressão, -(x) vira a operação 0 - x.
            if isinstance(operando, float):
                return -operando
            return ("subtracao", 0.0, operando)
        if token == "(":
            self.consumir()
            no = self.expressao()
            if self.atual() != ")":
                raise ErroExpressao("Parênteses desbalanceados: falta fechar ')'.")
            self.consumir()
            return no
        if isinstance(token, float):
            self.consumir()
            return token
        if token == ")":
            raise ErroExpressao("Parênteses desbalanceados ou vazios: ')' inesperado.")
        raise ErroExpressao(f"Operador '{token}' sem operando à esquerda.")


def para_arvore(expr: str):
    """Transforma a expressão em uma árvore sintática."""
    parser = _Parser(tokenizar(expr))
    arvore = parser.expressao()
    if parser.atual() is not None:
        sobra = parser.atual()
        if sobra == ")":
            raise ErroExpressao("Parênteses desbalanceados: ')' sem '(' correspondente.")
        raise ErroExpressao(f"Token inesperado: '{sobra}'.")
    return arvore


# ---------------------------------------------------------------------------
# 3. Avaliação com executor injetado
# ---------------------------------------------------------------------------

def executor_local(op: str, a: float, b: float) -> float:
    """Executor do Modo B: faz a conta no próprio processo."""
    if op == "soma":
        return a + b
    if op == "subtracao":
        return a - b
    if op == "multiplicacao":
        return a * b
    if op == "divisao":
        if b == 0:
            raise ZeroDivisionError("Divisão por zero")
        return a / b
    raise ErroExpressao(f"Operação desconhecida: {op}")


def avaliar_arvore(no, executor):
    """Avalia a árvore em pós-ordem: primeiro os filhos, depois o nó."""
    if isinstance(no, float):
        return no
    op, esquerda, direita = no
    a = avaliar_arvore(esquerda, executor)
    b = avaliar_arvore(direita, executor)
    return float(executor(op, a, b))


def avaliar(expr: str, executor=executor_local) -> float:
    """Calcula a expressão chamando executor(op, a, b) para cada operação."""
    return avaliar_arvore(para_arvore(expr), executor)


# ---------------------------------------------------------------------------
# Utilidades para os clientes
# ---------------------------------------------------------------------------

def analisar_operacao_simples(expr: str):
    """Lê uma operação simples ("10 + 15", "-3 * 2.5") e devolve (op, a, b).

    Usado na opção 1 do menu dos clientes: exige exatamente dois números
    e um operador, sem parênteses nem operações encadeadas.
    """
    arvore = para_arvore(expr)
    if (
        isinstance(arvore, tuple)
        and isinstance(arvore[1], float)
        and isinstance(arvore[2], float)
        and "(" not in expr
    ):
        return arvore
    raise ErroExpressao("Operação simples deve ter dois números e um operador (ex: 10 + 15).")


def formatar(n) -> str:
    """Mostra 25.0 como 25 e mantém as casas decimais quando existirem."""
    if isinstance(n, float) and n.is_integer():
        return str(int(n))
    return str(n)
