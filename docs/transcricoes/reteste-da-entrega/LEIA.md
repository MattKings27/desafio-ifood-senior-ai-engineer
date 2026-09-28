# Reteste da entrega

Os três cenários que falharam na [rodada da entrega](../rodada-da-entrega/LEIA.md),
depois das correções, e o cenário novo da conversa que o botão "Responder
agora" do Início começa. Uma execução cada, `claude-fable-5-1` com esforço
medium.

| | |
|---|---|
| Cenários aprovados | **4 de 4** |
| Latência por turno (p50 / p95) | 20,0 s / 278,5 s |
| Custo da rodada | US$ 4,63 |

O p95 alto é um turno só, o segundo da conversa do "Responder agora": ela disse
os pratos de que gosta, e o agente fez uma busca inteira na internet dentro do
turno, que levou 8,5 minutos. O cenário passou, mas uma conversa não pode
esperar isso. O `SOUL.md` passou a dizer que, nessa conversa, o agente trabalha
com as receitas do catálogo e só oferece buscar na internet no fim, avisando que
leva alguns minutos. A execução seguinte está em
[`../entrevista-da-cozinha/`](../entrevista-da-cozinha/LEIA.md).

Entre a rodada da entrega e este reteste também entrou uma correção do motor que
um destes cenários revelou: a receita contada em primeira pessoa ("refogo a
cebola, cozinho 20 minutos") não exigia fogão, então o "não tenho fogão" dela
não bloqueava o prato. Agora bloqueia, com o caso dourado
`receita_contada_em_primeira_pessoa_sem_fogao_bloqueia`.
