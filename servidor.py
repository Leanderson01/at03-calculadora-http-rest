"""
Servidor da calculadora via HTTP-REST (Flask), no lugar da página PHP.

Rotas (todas por POST, corpo JSON):
  POST /soma, /subtracao, /multiplicacao, /divisao   {"a": 10, "b": 15}
  POST /expressao                                    {"expr": "(10+15)*4"}

Respostas:
  200 {"resultado": 100}
  400 {"erro": "Divisão por zero"}        (entrada inválida também é 400)
  503 {"erro": "Serviço indisponível..."} (falha simulada com --falhas)

Flags para demonstrar o retry do cliente:
  --falhas 0.5   metade das requisições responde 503 aleatoriamente
  --atraso 5     espera 5 s antes de responder (provoca timeout no cliente)
"""

import argparse  # lê host, porta, --falhas e --atraso da linha de comando
import random  # sorteia as falhas simuladas
import time  # implementa o atraso artificial

from flask import Flask, jsonify, request  # micro framework web: app, resposta JSON e acesso à requisição

from expressao import ErroExpressao, avaliar, executor_local  # parser próprio (sem eval)

app = Flask(__name__)  # cria a aplicação web
CONFIG = {"falhas": 0.0, "atraso": 0.0}  # parâmetros de simulação, preenchidos no main()


def numero(valor):  # valida que o valor recebido é número
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):  # bool é subclasse de int em Python, por isso é excluído
        raise ValueError(f"valor não numérico: {valor!r}")  # vira 400 na rota
    return float(valor)  # devolve sempre como float


@app.before_request  # roda antes de toda rota
def simular_problemas():  # injeta atraso e falhas para testar o retry do cliente
    if CONFIG["atraso"] > 0:  # atraso configurado
        print(f"    atrasando {CONFIG['atraso']}s antes de responder...")  # avisa no console
        time.sleep(CONFIG["atraso"])  # segura a resposta; se passar do timeout do cliente, ele desiste e tenta de novo
    if random.random() < CONFIG["falhas"]:  # sorteio: cai aqui com probabilidade --falhas
        print(f"    {request.path}: falha simulada -> 503")  # avisa no console
        return jsonify(erro="Serviço indisponível (falha simulada)"), 503  # 503 Service Unavailable; a rota nem é executada
    return None  # None faz o Flask seguir para a rota normalmente


def rota_operacao(nome):  # fábrica das quatro rotas de operação básica
    def tratar():  # função executada a cada POST na rota
        dados = request.get_json(silent=True)  # lê o corpo como JSON; None se não for JSON
        if not isinstance(dados, dict) or "a" not in dados or "b" not in dados:  # precisa de um objeto com "a" e "b"
            return jsonify(erro='Envie um JSON {"a": número, "b": número}'), 400  # 400 Bad Request
        try:  # conversão e cálculo podem falhar
            resultado = executor_local(nome, numero(dados["a"]), numero(dados["b"]))  # faz a conta
        except ZeroDivisionError:  # divisão por zero
            return jsonify(erro="Divisão por zero"), 400  # erro claro, o servidor continua no ar
        except ValueError as e:  # "a" ou "b" não é número
            return jsonify(erro=f"Entrada inválida: {e}"), 400  # 400 Bad Request
        print(f"    POST /{nome} {dados} -> {resultado}")  # registra a operação no console
        return jsonify(resultado=resultado), 200  # 200 OK com o resultado
    tratar.__name__ = f"rota_{nome}"  # o Flask exige um nome de função diferente para cada rota
    return tratar  # devolve a função pronta


for operacao in ("soma", "subtracao", "multiplicacao", "divisao"):  # registra uma rota para cada operação
    app.add_url_rule(f"/{operacao}", view_func=rota_operacao(operacao), methods=["POST"])  # POST /soma, POST /subtracao...


@app.post("/expressao")  # rota do Modo B
def rota_expressao():  # o servidor calcula a expressão inteira
    dados = request.get_json(silent=True)  # lê o corpo como JSON
    if not isinstance(dados, dict) or not isinstance(dados.get("expr"), str):  # precisa de {"expr": "texto"}
        return jsonify(erro='Envie um JSON {"expr": "expressão"}'), 400  # 400 Bad Request
    try:  # parser e cálculo podem falhar
        resultado = avaliar(dados["expr"], executor_local)  # parser + executor local
    except ZeroDivisionError:  # divisão por zero dentro da expressão
        return jsonify(erro="Divisão por zero"), 400  # erro claro
    except ErroExpressao as e:  # expressão mal formada
        return jsonify(erro=f"Expressão inválida: {e}"), 400  # explica o problema
    print(f"    POST /expressao {dados['expr']!r} -> {resultado}")  # registra no console
    return jsonify(resultado=resultado), 200  # 200 OK com o resultado


@app.errorhandler(404)  # rota inexistente
def nao_encontrado(_erro):  # troca a página HTML padrão por JSON
    return jsonify(erro="Rota não encontrada"), 404  # 404 Not Found


@app.errorhandler(405)  # método errado (ex.: GET /soma)
def metodo_nao_permitido(_erro):  # troca a página HTML padrão por JSON
    return jsonify(erro="Use POST"), 405  # 405 Method Not Allowed


def main():  # ponto de entrada do servidor
    parser = argparse.ArgumentParser(description="Servidor da calculadora via HTTP-REST (Flask)")  # define os argumentos
    parser.add_argument("--host", default="localhost", help="endereço onde escutar")  # host padrão
    parser.add_argument("--porta", type=int, default=5003, help="porta HTTP (padrão 5003)")  # porta fixa do projeto
    parser.add_argument("--falhas", type=float, default=0.0, help="probabilidade (0 a 1) de responder 503")  # simula instabilidade
    parser.add_argument("--atraso", type=float, default=0.0, help="segundos de atraso antes de responder")  # simula lentidão
    args = parser.parse_args()  # lê os argumentos digitados
    if not 0 <= args.falhas <= 1:  # probabilidade fora da faixa
        parser.error("--falhas deve estar entre 0 e 1")  # mostra o erro e encerra

    CONFIG["falhas"] = args.falhas  # guarda a probabilidade de falha
    CONFIG["atraso"] = args.atraso  # guarda o atraso
    print(f"Servidor REST em http://{args.host}:{args.porta}/  (falhas={args.falhas}, atraso={args.atraso}s)")  # avisa que está pronto
    app.run(host=args.host, port=args.porta, threaded=True)  # sobe o servidor HTTP, uma thread por requisição


if __name__ == "__main__":  # só executa main() quando o arquivo é rodado diretamente
    main()  # inicia o servidor
