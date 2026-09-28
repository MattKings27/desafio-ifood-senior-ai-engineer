# ADR 0005: um auditor independente confere a conta do preço

## Contexto

O motor tira o modelo da conta (ADR 0002), mas o motor também é código e pode
errar. Numa das primeiras medições, o erro de conta veio dele, porque o mínimo era
arredondado para o centavo mais próximo, e a R$ 2,74 para um custo de R$ 2,47 a
Dona Maria receberia R$ 2,466, abaixo do custo
(`docs/transcricoes/antes-das-correcoes/LEIA.md`). Um teste escrito por quem
escreveu a fórmula tende a repetir a mesma leitura errada.

## Decisão

Um pacote separado, `auditor`, refaz a conta do §2.4 a partir do enunciado, sem
importar nada do motor (`auditor/src/auditor/conferencia.py`).

- **O que confere:** que as linhas exibidas somam o custo por porção; que o
  lucro informado é `0,90·P − CMV`; se o preço dá prejuízo. A tolerância é de
  R$ 0,01. Um preço abaixo do mínimo com a conta certa passa, com aviso, porque
  a decisão continua sendo dela.
- **Quando é chamado:** no custo por porção, em cada um dos três cenários, na
  conferência do custo antes de preço e no registro do aceite
  (`mise/src/mise/ferramentas/preco.py`, `mise/src/mise/mcp_server.py`).
- **Discordância segura o preço.** `Sessao.auditar` levanta `ContaNaoConfere`, e
  a ferramenta devolve o erro no lugar do número. Motor e auditor divergindo
  sobre um preço dar prejuízo também segura.
- **Auditor fora do ar não trava a conversa.** O parecer volta com
  `confere: null` e a observação "auditor indisponível", e a conta do motor
  segue, marcada como sem segunda opinião.
- **Dois transportes, o mesmo código.** Com `MISE_AUDITOR_URL`, o gateway
  conversa com o auditor pelo protocolo A2A (JSON-RPC 2.0 em `POST /a2a`, cartão
  em `/.well-known/agent-card.json`, `make auditor` sobe em `127.0.0.1:8899`).
  Sem a variável, que é o padrão do bootstrap, a mesma função roda no processo.

## Consequências

- Um erro de sinal, de arredondamento ou de ordem de operação no motor precisa
  acontecer igual em dois códigos escritos separadamente para passar.
- A duplicação é deliberada e pequena, e a conferência inteira cabe num arquivo.
- O auditor confere a aritmética do preço, e não a origem dos custos; ele não relê
  a planilha nem refaz o custo unitário de cada item. A normalização de unidade
  é coberta pelos casos dourados da planilha real
  (`mise/tests/golden/test_despensa_real.py`).

## Alternativas consideradas

- **Só testes no motor.** Continuam existindo, mas testam a fórmula com a
  leitura de quem a escreveu.
- **Um segundo modelo conferindo a resposta.** Trocaria uma verificação exata
  por uma opinião probabilística, com custo e latência a cada preço.
- **Auditor que reusa as funções do motor.** Confirmaria a fórmula usando a
  própria fórmula, que é o que o arquivo proíbe logo no começo.
