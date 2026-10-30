# AT03 – Calculadora distribuída via HTTP-REST com Retry

Trabalho AT03 de Sistemas Distribuídos (SMD/UFC, 2026). Calculadora remota em **HTTP-REST**. O servidor em Flask faz o papel da página `CalculadoraPHP`, e o cliente em Python implementa uma **política de retry própria**.

## Paradigma

Requisição-resposta HTTP, com um recurso (rota) por operação:

| Rota | Corpo | Resposta |
|---|---|---|
| `POST /soma` | `{"a": 10, "b": 15}` | `200 {"resultado": 25.0}` |
| `POST /subtracao` | `{"a": .., "b": ..}` | `200 {"resultado": ..}` |
| `POST /multiplicacao` | `{"a": .., "b": ..}` | `200 {"resultado": ..}` |
| `POST /divisao` | `{"a": 5, "b": 0}` | `400 {"erro": "Divisão por zero"}` |
| `POST /expressao` | `{"expr": "(10+15)*4"}` | `200 {"resultado": 100.0}` |

Ao contrário do JSON-RPC, o **status HTTP carrega o significado**: `200` é sucesso, `400` é entrada inválida ou divisão por zero, e `503` é servidor indisponível.

## Política de Retry

Requisições pela rede falham por motivos passageiros: o servidor sobrecarregado responde 503, um pacote se perde, a conexão cai. Retry é **tentar de novo automaticamente** antes de devolver o erro ao usuário. O cliente implementa isso à mão em `ClienteREST.post()`, sem usar o `urllib3.Retry` pronto.

| Parâmetro | Argumento | Padrão |
|---|---|---|
| Máximo de tentativas | `--tentativas` | 5 |
| Espera inicial T | `--espera` | 1 s |
| Timeout de cada requisição | `--timeout` | 3 s |

**Espera entre tentativas: backoff exponencial com jitter**

```
espera = T × 2^(tentativa − 1) + aleatório(0, T)
       ≈ 1 s, 2 s, 4 s, 8 s ... (+ até 1 s)
```

- **Por que exponencial?** Se o servidor está sobrecarregado, repetir em intervalo fixo e curto só aumenta a carga. Dobrar a espera a cada falha dá tempo para ele se recuperar e limita o número de tentativas inúteis.
- **Por que jitter?** Se muitos clientes falham juntos e esperam exatamente o mesmo tempo, todos voltam juntos e derrubam o servidor de novo (o efeito "manada", *thundering herd*). O componente aleatório espalha as novas tentativas no tempo.

**Quando repetir e quando não repetir**

| Situação | Repete? | Por quê |
|---|---|---|
| Timeout | sim | o servidor pode só estar lento |
| Erro de conexão | sim | o servidor pode estar reiniciando |
| `5xx` (ex.: 503) | sim | falha do lado do servidor, possivelmente passageira |
| `429 Too Many Requests` | sim | o servidor pediu para esperar; o backoff resolve |
| `4xx` (ex.: 400, 404) | **não** | o erro é do pedido. Repetir o mesmo pedido dá o mesmo erro |

Ao esgotar as tentativas, o cliente mostra o erro e volta ao menu, sem encerrar. Repetir um POST aqui é seguro porque as operações da calculadora são puras: calcular `soma(10, 15)` duas vezes não tem efeito colateral. Num POST que cria um recurso (um pagamento, por exemplo), o retry exigiria uma chave de idempotência.

Exemplo real com o servidor em `--falhas 0.5`:

```
  Tentativa 1/5 falhou (503). Aguardando 1.4s...
  Tentativa 2/5 falhou (503). Aguardando 2.7s...
  Tentativa 3/5: sucesso.
  → servidor: subtracao(100, 0.6666666666666666) = 99.33333333333333
```

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `servidor.py` | API Flask com simulação de falhas e atraso (todas as linhas comentadas) |
| `cliente.py` | Cliente com menu e retry (todas as linhas comentadas) |
| `expressao.py` | Parser de expressões (descida recursiva, sem `eval`) |
| `test_expressao.py` | Testes do parser |

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Como executar

```bash
python servidor.py               # http://localhost:5003/
python cliente.py
```

Para **demonstrar o retry**:

```bash
python servidor.py --falhas 0.5  # metade das requisições responde 503
python servidor.py --atraso 5    # toda resposta demora 5 s > timeout de 3 s: o cliente repete e desiste
```

Também dá para desligar o servidor com o cliente aberto: aparecem os erros de conexão e as novas tentativas. Se o servidor voltar dentro da janela de tentativas, a chamada dá certo.

Opções do cliente: `--host`, `--porta`, `--tentativas`, `--espera`, `--timeout`.

Testes do parser: `python -m pytest -q` (ou `python -m unittest`).

## Captura no Wireshark

1. Interface de loopback: **Adapter for loopback traffic capture** no Windows (Npcap), `lo` no Linux, `lo0` no macOS.
2. Filtro: `tcp.port == 5003`. Para ver só as mensagens HTTP: `tcp.port == 5003 and http`.
3. Suba o servidor com `--falhas 0.5`.

O que observar:
- um POST por rota (`/soma`, `/multiplicacao`...) com o JSON no corpo;
- o status de cada resposta (`200`, `400`, `503`);
- as **repetições do retry**: o mesmo POST reenviado depois de um `503`, com intervalos crescentes (veja a coluna *Time*);
- com `--atraso`, o cliente desiste da conexão (FIN/RST) antes de chegar a resposta.
