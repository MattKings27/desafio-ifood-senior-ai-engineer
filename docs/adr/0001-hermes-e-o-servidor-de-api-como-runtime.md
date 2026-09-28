# ADR 0001: o Hermes, com o servidor de API dele, é o runtime do agente

## Contexto

O enunciado pede para instalar e customizar o Hermes Agent, da Nous Research. O
agente precisa atender em dois lugares com o mesmo comportamento: no
terminal, para quem avalia, e dentro do site da Dona Maria, ao lado de cada
tela. Ele precisa das mesmas instruções, das mesmas ferramentas, do mesmo
guard-rail e da mesma memória nos dois.

## Decisão

- **Um perfil isolado do Hermes 0.21**, `sabor-da-maria`, montado pelo
  `hermes/bootstrap.sh`: o `SOUL.md`, as 5 skills da consultoria, o plugin
  `guardrail-numerico` e o servidor MCP `mise` (o motor, pela porta de política
  do `gateway`). O `hermes/configurar_perfil.py` funde o overlay versionado
  (`hermes/config.overlay.yaml`) no `config.yaml` do perfil, sem tocar em
  credenciais, e registra o servidor MCP com o caminho do ambiente Python.
- **Só o que o agente usa.** O overlay desliga 11 conjuntos de
  ferramentas (arquivo, terminal, execução de código, controle do computador,
  navegador, delegação, agendamento, conexões, imagem, vídeo e voz). As skills
  genéricas do Hermes ficam desligadas pelo mecanismo oficial
  (`skills.disabled`), com a lista calculada a cada bootstrap; ficam as 5 da
  consultoria. O lembrete de criar skill fica em zero, e o plugin barra a
  ferramenta que reescreveria as skills.
- **No terminal**, `make chat` abre o Hermes nesse perfil.
- **Na web**, o backend fala com o servidor de API que o Hermes tem dentro do
  gateway (`127.0.0.1:8642`, prefixo `/p/sabor-da-maria`): abre uma sessão por
  conversa, manda a mensagem pelo `chat/stream` e para o turno pelo
  `/v1/runs/{id}/stop`. Só `gateway/src/gateway/hermes_cliente.py` fala com
  ele, e a chave fica no backend. O bootstrap gera as duas chaves que o servidor
  precisa, sem nunca imprimi-las (`hermes/api_da_agente.sh`).

## Consequências

- Um agente só, com as mesmas regras no terminal e na web. O Hermes cuida do
  laço de ferramentas, da sessão, da compressão de contexto e da troca para o
  modelo reserva.
- O agente depende de comportamento interno do Hermes: o nome que ele dá às
  ferramentas MCP, os argumentos dos hooks do plugin, os eventos do `chat/stream`
  e o `stop` pelo `run_id`. O bootstrap avisa quando a versão não é a 0.21
  medida, e o [runbook do agente na web](../runbooks/agente-na-web.md) registra,
  com arquivo e linha do Hermes, o que o chat supõe.
- Reiniciar o gateway do Hermes interrompe um turno que estiver rodando naquela
  hora.
- Numa das primeiras medições, com o pacote inteiro do Hermes ligado, o agente
  usou ferramentas de arquivo na pasta pessoal para achar a planilha
  (`docs/transcricoes/depois-das-primeiras-correcoes/LEIA.md`). Desligar o que
  ele não usa é também uma decisão de segurança.

## Alternativas consideradas

- **Um laço próprio sobre a API da Anthropic, no FastAPI.** Mais controle e
  menos dependência, mas deixa de ser o Hermes customizado que o desafio pede, e
  refaria sessão, compressão e reserva de modelo.
- **Rodar `hermes chat` como subprocesso a cada turno da web.** É o que o
  harness de avaliação faz, e funciona para medir. Na web, cada turno pagaria a
  subida do processo e a conexão do servidor MCP, e parar ou retomar um turno
  viraria sinal de processo.
- **Usar o perfil padrão do Hermes.** Misturaria o agente com qualquer outra
  configuração da máquina; o perfil isolado pode ser recriado do zero pelo
  bootstrap.
