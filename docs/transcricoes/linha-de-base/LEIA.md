# Linha de base da agente

Primeira execução real da agente no Hermes desde que as ferramentas novas
entraram, antes de qualquer correção. Serve de ponto de partida:
cada mudança nas instruções ou no motor é medida contra ela.

| | |
|---|---|
| Cenário | `sem-forno-pergunta-air-fryer` (§2.2), 2 turnos, k = 1 |
| Configuração | a versionada em `hermes/config.overlay.yaml`: `claude-opus-5`, esforço `max` |
| Estado | dossiê, auditoria e memória zerados (`evals.agente.isolamento`) |
| Resultado | passou nas expectativas da época |
| Latência | 48 s e 47 s por turno |
| Tokens | 4.527 de saída, 230.513 lidos do cache, 55.396 gravados no cache |
| Custo | ≈ US$ 0,58 (US$ 0,78 se as gravações de cache forem de 1 h) |

Preços usados no custo: Opus 5 a US$ 5 de entrada e US$ 25 de saída por milhão
de tokens; leitura de cache a 0,1× da entrada; gravação a 1,25× (5 min) ou 2×
(1 h). Fonte: referência de preços da API da Anthropic.

## O que a transcrição mostra

- **Trajetória certa.** Turno 1: `avaliar_receita` → `proxima_pergunta`, e a
  pergunta do gosto antes de qualquer custo. Turno 2: `registrar_resposta`
  (forno = não tem), reavaliação, e a pergunta pelo substituto (air fryer ou
  forninho elétrico) em vez de repetir a do forno.
- **Atribuição errada.** "A senhora tem fogão e disse que domina fritar e
  refogar." Ela não disse. `consultar_perfil` devolve os itens que a taxonomia
  marca como `pressuposto=True` misturados com os que ela confirmou, e a agente
  não tem como separar. A geladeira, que o §2.2 manda perguntar, também entra
  como pressuposta. Virou expectativa do cenário e entrou nas primeiras correções.
- **Saída das ferramentas.** O `stream-json` do Hermes 0.21 emite `tool_result`
  com `output` vazio. O harness completa as saídas a partir do `state.db` do
  perfil de avaliação, por `tool_call_id`.
