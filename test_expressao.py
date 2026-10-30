"""Testes do parser de expressões. Rodar com: python -m pytest -q"""

import unittest

from expressao import (
    ErroExpressao,
    analisar_operacao_simples,
    avaliar,
    formatar,
    para_arvore,
    tokenizar,
)


class TestTokenizar(unittest.TestCase):
    def test_tokens_basicos(self):
        self.assertEqual(tokenizar("(10 + 2.5)*4"), ["(", 10.0, "+", 2.5, ")", "*", 4.0])

    def test_caractere_desconhecido(self):
        with self.assertRaises(ErroExpressao):
            tokenizar("2 ^ 3")

    def test_numero_invalido(self):
        with self.assertRaises(ErroExpressao):
            tokenizar("1.2.3 + 1")

    def test_vazia(self):
        with self.assertRaises(ErroExpressao):
            tokenizar("   ")


class TestAvaliar(unittest.TestCase):
    def test_operacoes_basicas(self):
        self.assertEqual(avaliar("10 + 15"), 25)
        self.assertEqual(avaliar("10 - 15"), -5)
        self.assertEqual(avaliar("10 * 15"), 150)
        self.assertEqual(avaliar("10 / 4"), 2.5)

    def test_precedencia(self):
        self.assertEqual(avaliar("2 + 3 * 4"), 14)
        self.assertEqual(avaliar("10 - 6 / 2"), 7)

    def test_associatividade_esquerda(self):
        self.assertEqual(avaliar("10 - 4 - 3"), 3)
        self.assertEqual(avaliar("100 / 10 / 2"), 5)

    def test_parenteses(self):
        self.assertEqual(avaliar("(10 + 15) * 4"), 100)
        self.assertEqual(avaliar("((2 + 3) * (4 - 1)) / 5"), 3)

    def test_negativos(self):
        self.assertEqual(avaliar("-3 + (2.5 * -4)"), -13)
        self.assertEqual(avaliar("-(2 + 3) * 2"), -10)
        self.assertEqual(avaliar("--4"), 4)

    def test_decimais(self):
        self.assertAlmostEqual(avaliar("0.1 + 0.2"), 0.3)
        self.assertEqual(avaliar(".5 * 4"), 2)

    def test_divisao_por_zero(self):
        with self.assertRaises(ZeroDivisionError):
            avaliar("1 / (2 - 2)")


class TestErros(unittest.TestCase):
    def test_parenteses_desbalanceados(self):
        for expr in ["(1 + 2", "1 + 2)", "((3)", "()"]:
            with self.subTest(expr=expr), self.assertRaises(ErroExpressao):
                avaliar(expr)

    def test_operador_sobrando(self):
        for expr in ["1 +", "* 2", "1 + * 2", "3 4"]:
            with self.subTest(expr=expr), self.assertRaises(ErroExpressao):
                avaliar(expr)


class TestExecutorInjetado(unittest.TestCase):
    def test_uma_chamada_por_operacao(self):
        chamadas = []

        def executor(op, a, b):
            chamadas.append((op, a, b))
            return {"soma": a + b, "multiplicacao": a * b}[op]

        self.assertEqual(avaliar("(10 + 15) * 4", executor), 100)
        self.assertEqual(chamadas, [("soma", 10, 15), ("multiplicacao", 25, 4)])

    def test_arvore(self):
        self.assertEqual(para_arvore("(10+15)*4"), ("multiplicacao", ("soma", 10.0, 15.0), 4.0))


class TestOperacaoSimples(unittest.TestCase):
    def test_validas(self):
        self.assertEqual(analisar_operacao_simples("10 + 15"), ("soma", 10.0, 15.0))
        self.assertEqual(analisar_operacao_simples("-3 * -2.5"), ("multiplicacao", -3.0, -2.5))

    def test_invalidas(self):
        for expr in ["10", "1 + 2 + 3", "(1 + 2)", "-(3)"]:
            with self.subTest(expr=expr), self.assertRaises(ErroExpressao):
                analisar_operacao_simples(expr)

    def test_formatar(self):
        self.assertEqual(formatar(25.0), "25")
        self.assertEqual(formatar(2.5), "2.5")


if __name__ == "__main__":
    unittest.main()
