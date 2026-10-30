"""
Cliente da calculadora via HTTP-REST, com política de RETRY própria.

Política (implementada à mão, sem urllib3.Retry):
  - até --tentativas tentativas (padrão 5);
  - espera entre tentativas = T * 2^(tentativa-1) + jitter aleatório em [0, T)
    (backoff exponencial com jitter; T = --espera, padrão 1 s);
  - cada requisição tem --timeout segundos (padrão 3 s);
  - repete em: timeout, erro de conexão, status 5xx e 429;
  - NÃO repete em 4xx (exceto 429): erro do cliente não se resolve repetindo.
"""

import argparse  # lê os parâmetros da linha de comando
import random  # gera o jitter
import time  # espera entre as tentativas

import requests  # cliente HTTP

from expressao import SIMBOLOS, ErroExpressao, analisar_operacao_simples, avaliar, formatar  # parser próprio


class ErroServidor(Exception):  # o servidor respondeu com erro definitivo (4xx) ou o retry esgotou
    pass  # não precisa de nada além do nome e da mensagem


class ClienteREST:  # encapsula URL base e a política de retry
    def __init__(self, url_base, tentativas, espera, timeout):  # configura o cliente
        self.url_base = url_base  # ex.: http://localhost:5003
        self.tentativas = tentativas  # número máximo de tentativas
        self.espera = espera  # espera inicial T, em segundos
        self.timeout = timeout  # tempo máximo de cada requisição
        self.sessao = requests.Session()  # sessão HTTP; o servidor de desenvolvimento do Flask responde "Connection: close", então cada chamada abre uma conexão TCP nova

    def calcular_espera(self, tentativa):  # backoff exponencial com jitter
        return self.espera * 2 ** (tentativa - 1) + random.uniform(0, self.espera)  # T, 2T, 4T... mais um aleatório em [0, T)

    def post(self, rota, corpo):  # faz um POST aplicando a política de retry
        url = f"{self.url_base}/{rota}"  # monta a URL da rota, ex.: /soma
        for tentativa in range(1, self.tentativas + 1):  # tentativa 1, 2, ..., N
            try:  # a requisição pode falhar na rede
                resposta = self.sessao.post(url, json=corpo, timeout=self.timeout)  # envia o POST com corpo JSON
            except requests.Timeout:  # o servidor não respondeu a tempo
                motivo = "timeout"  # falha transitória: vale repetir
            except requests.ConnectionError:  # conexão recusada ou caiu
                motivo = "erro de conexão"  # falha transitória: vale repetir
            else:  # a requisição chegou e voltou com algum status
                if resposta.status_code == 200:  # sucesso
                    print(f"  Tentativa {tentativa}/{self.tentativas}: sucesso.")  # registra o sucesso
                    return resposta.json()["resultado"]  # devolve o resultado do corpo JSON
                if resposta.status_code != 429 and resposta.status_code < 500:  # 4xx (menos 429): erro do cliente
                    print(f"  Tentativa {tentativa}/{self.tentativas}: erro {resposta.status_code}, sem retry.")  # repetir não resolveria
                    raise ErroServidor(self.mensagem_de_erro(resposta))  # erro definitivo para o usuário
                motivo = str(resposta.status_code)  # 5xx ou 429: falha transitória, vale repetir

            if tentativa == self.tentativas:  # era a última tentativa
                print(f"  Tentativa {tentativa}/{self.tentativas} falhou ({motivo}). Desistindo.")  # registra o fim
                break  # sai do laço sem esperar
            espera = self.calcular_espera(tentativa)  # quanto esperar antes da próxima
            print(f"  Tentativa {tentativa}/{self.tentativas} falhou ({motivo}). Aguardando {espera:.1f}s...")  # registra a falha
            time.sleep(espera)  # espera antes de tentar de novo
        raise ErroServidor(f"servidor indisponível após {self.tentativas} tentativas")  # retry esgotado

    @staticmethod  # não usa self
    def mensagem_de_erro(resposta):  # extrai a mensagem de erro do corpo
        try:  # o corpo pode não ser JSON
            return resposta.json()["erro"]  # mensagem enviada pelo servidor
        except (ValueError, KeyError):  # corpo vazio ou em outro formato
            return f"HTTP {resposta.status_code}"  # usa só o status

    def operacao(self, op, a, b):  # chamada de uma operação básica
        return self.post(op, {"a": a, "b": b})  # POST /<op> com {"a", "b"}

    def expressao(self, expr):  # Modo B
        return self.post("expressao", {"expr": expr})  # POST /expressao com {"expr"}


def executor_remoto(cliente):  # cria o executor do Modo A, ligado a este cliente
    def executar(op, a, b):  # chamado pelo parser para cada operação básica
        resultado = cliente.operacao(op, a, b)  # um POST (com retry) por operação
        print(f"  → servidor: {op}({formatar(a)}, {formatar(b)}) = {formatar(resultado)}")  # mostra cada chamada remota
        return resultado  # devolve o valor para o parser continuar
    return executar  # o parser recebe essa função como executor


MENU = """
=== Calculadora HTTP-REST ===
1) Operação simples (ex: 10 + 15)
2) Expressão – Modo A (cliente decompõe e chama o servidor por operação)
3) Expressão – Modo B (servidor calcula a expressão inteira)
0) Sair"""  # texto do menu


def main():  # ponto de entrada do cliente
    parser = argparse.ArgumentParser(description="Cliente da calculadora via HTTP-REST com retry")  # define os argumentos
    parser.add_argument("--host", default="localhost", help="endereço do servidor")  # host padrão
    parser.add_argument("--porta", type=int, default=5003, help="porta do servidor (padrão 5003)")  # porta padrão
    parser.add_argument("--tentativas", type=int, default=5, help="máximo de tentativas (padrão 5)")  # limite do retry
    parser.add_argument("--espera", type=float, default=1.0, help="espera inicial T em segundos (padrão 1)")  # base do backoff
    parser.add_argument("--timeout", type=float, default=3.0, help="timeout por requisição em segundos (padrão 3)")  # limite de cada tentativa
    args = parser.parse_args()  # lê os argumentos digitados

    cliente = ClienteREST(f"http://{args.host}:{args.porta}", args.tentativas, args.espera, args.timeout)  # cria o cliente
    print(f"Servidor: {cliente.url_base}  (tentativas={args.tentativas}, T={args.espera}s, timeout={args.timeout}s)")  # mostra a configuração
    try:  # Ctrl+C encerra
        while True:  # repete o menu até o usuário sair
            print(MENU)  # mostra as opções
            opcao = input("Escolha: ").strip()  # lê a opção digitada
            if opcao == "0":  # sair
                break  # sai do laço
            if opcao not in ("1", "2", "3"):  # opção inexistente
                print("Opção inválida.")  # avisa e mostra o menu de novo
                continue  # volta ao início do laço
            texto = input("Digite: ").strip()  # lê a operação ou expressão
            try:  # erros de entrada ou do servidor não encerram o programa
                if opcao == "1":  # operação simples
                    op, a, b = analisar_operacao_simples(texto)  # extrai operação e operandos
                    resultado = cliente.operacao(op, a, b)  # um POST (com retry)
                    print(f"{formatar(a)} {SIMBOLOS[op]} {formatar(b)} = {formatar(resultado)}")  # mostra o resultado
                elif opcao == "2":  # Modo A
                    resultado = avaliar(texto, executor_remoto(cliente))  # parser local + um POST por operação
                    print(f"Resultado final: {formatar(resultado)}")  # mostra o resultado
                else:  # Modo B
                    resultado = cliente.expressao(texto)  # um POST com a expressão inteira
                    print(f"Resultado (calculado no servidor): {formatar(resultado)}")  # mostra o resultado
            except ErroExpressao as e:  # o parser local recusou a entrada
                print(f"Entrada inválida: {e}")  # explica o erro
            except ErroServidor as e:  # erro definitivo ou retry esgotado
                print(f"Erro: {e}")  # informa sem encerrar o programa
    except (KeyboardInterrupt, EOFError):  # Ctrl+C ou fim da entrada
        print()  # pula linha antes de sair
    finally:  # sempre executa
        cliente.sessao.close()  # fecha as conexões abertas pela sessão HTTP
        print("Até logo!")  # despedida


if __name__ == "__main__":  # só executa main() quando o arquivo é rodado diretamente
    main()  # inicia o cliente
