# ADR 0009: modelo, esforço, e por que não há temperatura nem top_p

## Contexto

O agente conduz conversas longas com ferramenta no meio, recusa com
disciplina quando falta dado e fala num registro combinado com ela ("a
senhora", frases curtas, uma pergunta por vez). Errar a ordem das ferramentas ou
fazer conta de cabeça custa dinheiro dela.

O reflexo comum para "resposta repetível" é fixar `temperature: 0`. Os modelos
atuais da Anthropic usados aqui não aceitam o parâmetro: Fable 5.1, Opus 5.5,
Opus 5 e Sonnet 5 recusam `temperature`, `top_p` e `top_k` com HTTP 400, e o
próprio Hermes os remove antes de chamar a API (o `hermes/config.overlay.yaml`
cita o arquivo e a linha do adaptador). O controle que existe é o esforço
(`output_config.effort`, de `low` a `max`), com raciocínio adaptativo sempre
ligado no Fable 5.1.

## Decisão

- **Modelo:** `claude-fable-5-1`, com `claude-opus-5-5` como reserva
  (`fallback_providers`). Se a chamada ao Fable falhar de um jeito que o Hermes
  trata como motivo para trocar de modelo, o turno segue no Opus 5.5 com o mesmo
  `SOUL.md`, as mesmas skills e o mesmo esforço.
- **Esforço:** `medium`. No Fable 5.1 o esforço médio fica perto do alto dos
  modelos anteriores, com menos espera e menos custo. A medição com os cenários
  do agente confirma ou troca esse valor, e o resultado fica no README.
- **Sem parâmetro de amostragem no perfil.** O `hermes/tests/test_overlay.py`
  falha se `temperature`, `top_p` ou `top_k` aparecerem no overlay.
- **O determinismo vem da arquitetura:** número só do motor em `Decimal` (ADR
  0002), portão como código (ADR 0003), receita pelo id (ADR 0007), guard-rail
  (ADR 0004), auditor (ADR 0005), abstenção calibrada na busca (ADR 0006). O
  modelo escolhe palavras; os fatos e os números não passam por sorteio.
- **Onde o parâmetro existe, ele fica fixo.** O juiz de modelo das avaliações
  usa o Haiku 4.5, que ainda aceita temperatura, com `temperature: 0`
  (`evals/src/evals/juiz.py`).

## Consequências

- Duas execuções da mesma conversa podem ter frases diferentes, e os números, as
  receitas e as decisões são os mesmos, porque saem do motor.
- A medição do agente mede consistência por `pass^k` (o cenário passa só se
  passar em todas as k execuções), não por uma execução feliz.
- O histórico mostra que esforço maior não é melhor por padrão: na matriz da
  versão anterior, o Opus 5 em esforço alto passou 11 de 12 cenários em todas as
  5 execuções, e em esforço máximo, 9 de 12, com mais conta de cabeça
  (`docs/transcricoes/matriz/LEIA.md`).
- Preço por milhão de tokens na tabela de referência da API da Anthropic
  (24/06/2026, `telemetria/src/telemetria/custo.py`): Fable 5.1 a US$ 10 de
  entrada e US$ 50 de saída; Opus 5.5 a US$ 4 e US$ 20.

## Alternativas consideradas

- **Um modelo que aceita temperatura.** Trocaria o modelo que melhor segue as
  instruções por um parâmetro que não resolve o problema: temperatura zero não
  impede conta de cabeça, só a repete igual.
- **Esforço máximo.** Medido na versão anterior: mais lento, mais caro e com
  mais números sem origem.
- **Reserva de outro fornecedor.** Mudaria o comportamento com as mesmas
  instruções e o formato das ferramentas; a reserva no mesmo fornecedor mantém
  o adaptador do Hermes.
