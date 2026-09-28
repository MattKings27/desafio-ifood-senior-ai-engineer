# Incidente: a agente conversou sem o servidor do motor

Rodada de 24/09/2026, 4 de 12 cenários. Não é medida da agente: é o registro de
uma falha de infraestrutura que nenhum teste pegava.

O servidor MCP do motor levou mais de 30 segundos para subir, o Hermes desistiu
da conexão pelo limite padrão, e a agente conversou sem nenhuma ferramenta do
motor. Nas transcrições ela procura as ferramentas (`tool_search`,
`tool_describe`) e recebe "não encontrada". Nada avisou a pessoa do outro lado.

A causa foi o ambiente Python num disco do Windows visto pelo WSL: importar o
pacote `mcp` faz mais de mil consultas de arquivo, cada uma atravessando a ponte
entre os dois sistemas (43 s só nesse import).

O que mudou:

- o ambiente vai para o disco Linux quando o repositório está num disco do Windows;
- o servidor é registrado pelo caminho real do ambiente, não pelo link (69 s → 9 s);
- o limite de conexão do servidor do motor subiu para 90 s;
- `make evals-agente` confere a conexão antes de gastar com o modelo, e para se ela falhar.

O custo desta rodada foi de US$ 5,28 (preços da referência da API da Anthropic,
tabela de 24/06/2026), e os tokens do stream conferiram com o banco do Hermes.
