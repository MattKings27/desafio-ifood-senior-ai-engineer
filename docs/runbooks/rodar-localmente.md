# Rodar localmente

## Requisitos

- Linux, macOS ou o WSL2 no Windows.
- Python 3.11 a 3.13, e de preferência o `uv` (o instalador do Hermes traz um).
- Node 22 ou mais novo, com o npm, para a interface; git, make e curl.
- O Hermes Agent 0.21.4, da Nous Research, no commit em que o projeto foi
  medido. `make instalar-hermes` roda o instalador oficial com `--commit
  ee8a919fd2769166d45ebf67f45ff5b1acec69fe --skip-setup --skip-browser
  --skip-computer-use`.
- A chave da Anthropic no perfil padrão do Hermes, antes do bootstrap: `hermes
  setup model`. O perfil do projeto nasce como cópia do padrão, com a chave
  junto.

## Subir

```bash
make instalar-hermes           # o Hermes no commit testado, pelo instalador oficial
hermes setup model             # a chave da Anthropic, antes do bootstrap
make bootstrap                 # ambiente Python, perfil do Hermes, skills, plugin, MCP, as chaves da API e o gateway
(cd webapp && npm ci)          # dependências da interface
make verificar                 # confere tudo e diz o comando que conserta cada item
make demo                      # API em :8777 e interface em :3000 (make dev, para desenvolver)
make chat                      # o mesmo agente, no terminal
```

- O `make instalar-hermes` não faz nada quando o Hermes 0.21.4 já está
  instalado, e não troca um Hermes de outra versão sem `FORCAR=1`.
  `SIMULAR=1 make instalar-hermes` só mostra o comando que rodaria.
- O `make bootstrap` é idempotente e, no fim, reinicia o gateway do Hermes para
  abrir o servidor de API em `127.0.0.1:8642`. Numa máquina em que o gateway
  ainda não é serviço do sistema, ele instala o serviço (systemd ou launchd),
  que já sobe; no WSL sem systemd, avisa e pede `hermes gateway run` num
  terminal à parte. `SEM_REINICIAR=1 make bootstrap` faz tudo menos isso.
- O `make verificar` só lê: roda com o Python do sistema, antes de existir o
  ambiente do projeto, e sai com erro enquanto houver algum ✗.
- O `make dev` confere o ambiente, as portas e o agente, e sobe a API e a
  interface; o agente fora do ar é só um aviso, e o resto do site funciona.
  Ele liga a busca automática de receitas (`SABOR_DESCOBERTA=ligada`), que
  chama o modelo; `SABOR_DESCOBERTA=desligada make dev` desliga.
  Ctrl-C derruba as duas. Outras portas: `MISE_HTTP_PORT=8778 DEV_PORTA_WEB=3001 make dev`.
  O `make demo` faz o mesmo com a interface compilada para produção, sempre nas
  portas 3000 e 8777.
- Sem o Hermes, dá para ver o site e o motor: `scripts/preparar_ambiente.sh`,
  `(cd webapp && npm ci)` e `make demo`; o chat diz que o agente está fora do ar.

## Conferir

```bash
make verificar         # sistema, ferramentas, agente, chaves (só presença) e portas, com o conserto de cada item
make agente-status     # gateway, chaves (só presença), servidor de API e modelo do perfil
make mcp               # o Hermes conecta no servidor mise e lista as ferramentas
make test              # lint, tipos e testes com cobertura dos seis pacotes, do plugin e das instruções
make evals             # casos do portão e ataques
scripts/clone_limpo.sh # clona o commit e roda tudo do zero, como quem avalia
```

Os dados locais ficam em `.estado/` (dossiê, conversas, trilha de auditoria,
vetores), fora do git. Para recomeçar do zero, pare a API (Ctrl-C no `make
demo`) e o gateway do Hermes (`hermes gateway stop`), que mantém o dossiê aberto
pelo servidor MCP, mova a pasta e suba de novo (`hermes gateway start` e `make
demo`); não apague, é o histórico dela. Para só voltar ao começo da planilha,
"Restaurar os dados da planilha", nas Preferências, não precisa parar nada.

## Quando não funciona

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| O chat diz que o agente está fora do ar | gateway do Hermes parado ou sem a chave do servidor de API | `make agente-status`; depois o [runbook do agente na web](agente-na-web.md) |
| O agente responde sem usar ferramenta nenhuma | o servidor MCP não subiu a tempo | `make mcp`; no WSL com o projeto num disco do Windows, o bootstrap põe o ambiente Python no disco do Linux; confira que ele avisou isso |
| `make dev` recusa por porta ocupada | processo antigo segurando 8777 ou 3000 | veja quem está na porta com `ss -ltnp` e encerre esse processo pelo PID |
| 400 na API | `Host` fora de `localhost` e `127.0.0.1` | acrescente o nome em `MISE_HOSTS` |
| 403 ao salvar pela tela aberta de outro aparelho | origem fora de `MISE_CORS` | acrescente a origem em `MISE_CORS` antes do `make dev` |
| A busca não usa o modelo multilíngue | o extra `semantico` não está instalado | [`docs/rag.md`](../rag.md#o-vetorizador-neural-opcional) |
| `make design` falha sem rede | o linter vem do npm | rode com rede; o CI confere os tokens do mesmo jeito |

Segredos ficam só nos `.env` do Hermes, fora do repositório. Para saber se uma
chave existe, use `make verificar` ou `make agente-status`, que mostram só a
presença; nunca imprima um `.env`.
