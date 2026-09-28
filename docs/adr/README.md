# Decisões de arquitetura

Cada decisão tem contexto, a decisão, as consequências, as boas e as que
custam, e as alternativas que ficaram de fora. As que tratam do Hermes Agent
são a 0001 (o runtime e o servidor de API), a 0004 (o plugin de guard-rail), a
0008 (a memória), a 0009 (o modelo e o esforço) e a 0011 (o agente como
serviço da plataforma).

| ADR | Decisão |
|---|---|
| [0001](0001-hermes-e-o-servidor-de-api-como-runtime.md) | O Hermes, com o servidor de API dele, é o runtime do agente |
| [0002](0002-motor-sem-llm-para-todo-numero.md) | Todo número sai de um motor sem LLM, em `Decimal`, com a conta |
| [0003](0003-portao-como-codigo.md) | O portão de viabilidade é código, não instrução |
| [0004](0004-guard-rail-numerico.md) | O guard-rail numérico confere cada valor da resposta |
| [0005](0005-auditor-independente.md) | Um auditor independente confere a conta do preço |
| [0006](0006-busca-hibrida-na-plataforma.md) | Busca híbrida sobre a plataforma inteira, com "não sei" calibrado |
| [0007](0007-catalogo-do-servidor-e-receita-por-id.md) | O catálogo é escrito só pelo servidor, e a receita anda pelo id |
| [0008](0008-memoria-em-camadas.md) | Memória em camadas, com uma fonte de verdade para cada fato |
| [0009](0009-modelo-esforco-e-sem-amostragem.md) | Modelo, esforço, e por que não há temperatura nem top_p |
| [0010](0010-mascara-durante-o-streaming.md) | Valor em reais mascarado enquanto a resposta chega |
| [0011](0011-agente-como-servico.md) | O agente como serviço da plataforma |
