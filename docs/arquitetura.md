# Arquitetura

Visão em três níveis (contexto, contêineres, componentes) e quatro fluxos em
sequência. As decisões e o porquê de cada uma estão nos [ADRs](adr/README.md).

## Contexto

```mermaid
flowchart LR
    M["Dona Maria"] --> W["Sabor da Maria: telas e agente"]
    A["Quem avalia"] --> T["terminal: make chat"]
    T --> H["Hermes Agent, perfil sabor-da-maria"]
    W --> H
    H --> AN["API da Anthropic: Fable 5.1, reserva Opus 5.5"]
    H --> WEB["sites de receita"]
    W --> P["planilha da despensa"]
```

A Dona Maria usa o site; o agente é o mesmo no site e no terminal. O modelo
é chamado só pelo Hermes. As páginas de receita são lidas pelo servidor, nunca
pelo navegador.

## Contêineres

```mermaid
flowchart TB
    NAV["Navegador"] --> NX["webapp: Next 16, porta 3000"]
    NX -- "/motor/* vira /api/*" --> API["gateway HTTP: FastAPI, porta 8777"]
    API -- "chat/stream com chave" --> HAPI["servidor de API do Hermes, porta 8642"]
    HAPI --> AG["agente: SOUL, 5 skills, guard-rail"]
    AG -- "MCP stdio" --> MCP["gateway MCP: política das ferramentas"]
    MCP --> MISE["mise: motor em Decimal"]
    API --> MISE
    MISE --> DB[("dossiê SQLite")]
    API --> CV[("conversas.db")]
    MISE --> RET["retrieval: web segura, extrator, busca"]
    MISE --> AUD["auditor: A2A ou no processo"]
```

| Contêiner | Onde | Papel |
|---|---|---|
| `webapp` | `webapp/` | as telas (Início, Despensa, Cozinha, Receitas, Cardápio, Histórico, Pôr preço), o painel da conversa em toda tela e a engrenagem de Preferências |
| gateway HTTP | `gateway/src/gateway/http.py` e `rotas/` | as rotas da tela e da conversa, dono do turno do chat, máscara, cards e ações |
| gateway MCP | `gateway/src/gateway/principal.py` | o servidor `mise` que o Hermes sobe, com autenticação, escopos, limite de taxa, cota, disjuntor e trilha de auditoria |
| Hermes | perfil criado por `hermes/bootstrap.sh` | o laço do agente, as sessões, a compressão, a reserva de modelo e o servidor de API |
| `mise` | `mise/src/mise/` | custo, viabilidade, preço, catálogo, avaliações, dossiê, corpus da busca, preço de referência (média de São Paulo) e peso estimado da embalagem, com a fonte, as 27 ferramentas |
| `retrieval` | `retrieval/src/retrieval/` | busca de página só em endereço público, extração de JSON-LD e microdata, índice híbrido |
| `auditor` | `auditor/src/auditor/` | refaz a conta do preço sem importar o motor |
| `telemetria` | `telemetria/src/telemetria/` | rastro OpenTelemetry, métricas por ferramenta, custo do modelo |

As duas portas do motor chamam as mesmas regras (`Sessao` em
`mise/src/mise/mcp_server.py`): a conversa e a tela nunca calculam por caminhos
diferentes.

## Componentes do motor

```mermaid
flowchart LR
    PL["despensa.py: planilha e unidades"] --> CMV["cmv.py: custo por porção"]
    CAT["catalogo.py: receitas por id"] --> VIA["viabilidade.py: o portão"]
    PER["perfil.py: tem, não tem, não sabemos"] --> VIA
    VIA --> CMV
    CMV --> PRE["preco.py: mínimo, lucro, cenários"]
    VIA --> EST["estimativa.py: preço preliminar"]
    DOS["dossie.py: SQLite"] --> COR["corpus.py: trechos da busca"]
```

## Um turno da conversa na web

```mermaid
sequenceDiagram
    participant N as Navegador
    participant G as gateway HTTP
    participant H as Hermes
    participant M as motor via MCP
    N->>G: POST /api/conversas/ID/turnos com texto, contexto e id_cliente
    G-->>N: 202 com turno_id
    N->>G: GET .../eventos, SSE com desde
    G->>H: POST /p/sabor-da-maria/api/sessions/ID/chat/stream
    H->>M: chamada de ferramenta, por exemplo calcular_cmv
    M-->>H: resultado em Decimal com a derivação
    G-->>N: atividade.iniciada e atividade.concluida
    G->>G: chama a própria rota da tela para montar o card
    G-->>N: cartao
    H-->>G: texto do modelo em pedaços
    G-->>N: texto.parcial com os valores mascarados
    H-->>G: fim da execução
    G->>G: confere cada valor contra as saídas do motor
    G-->>N: estado.alterado, texto.final, sugestoes, turno.concluido
```

## Descoberta de receitas

```mermaid
sequenceDiagram
    participant N as Navegador
    participant G as gateway HTTP
    participant H as Hermes
    participant M as motor via MCP
    participant S as site de receita
    N->>G: POST /api/receitas/descoberta
    G-->>N: 202 com execucao_id
    N->>G: GET /api/receitas/descoberta/eventos, SSE
    G->>H: POST /v1/runs com o pedido fixo de hermes/prompts/descoberta.md
    H->>M: pauta_de_descoberta
    H->>H: web_search, até 8 pesquisas
    H->>M: buscar_receita_na_web, até 20 páginas, 3 por pesquisa
    M->>S: GET só em endereço público
    S-->>M: página com JSON-LD
    M->>M: grava no catálogo e devolve receita_id
    G->>G: marca a receita como descoberta e confere a aba dela
    G-->>N: progresso e receita.encontrada
    G-->>N: fim
```

Com `SABOR_DESCOBERTA` desligada, a rota responde 501 e a tela abre a conversa
com o pedido pronto; a busca acontece no turno, com as mesmas ferramentas.

## A conferência de viabilidade

```mermaid
sequenceDiagram
    participant H as agente
    participant M as motor
    H->>M: avaliar_receita com receita_id
    M->>M: ingredientes, equipamentos, técnicas, rotina e gosto
    alt falta saber
        M-->>H: veredito falta saber e a próxima pergunta
        H->>H: pergunta a ela, uma coisa por vez, gosto, equipamento, técnica ou rotina
        H->>M: registrar_resposta, inclusive não sei
    else não dá
        M-->>H: veredito não dá, com o motivo
    else dá ou dá comprando
        M-->>H: tem e falta por ingrediente, custo da compra e se cabe nos R$ 80
    end
```

## O preço

```mermaid
sequenceDiagram
    participant H as agente
    participant M as motor
    participant A as auditor
    H->>M: calcular_cmv com receita_id
    M->>M: exige avaliação que libera preço
    M->>A: linhas e total por porção
    A-->>M: confere ou não confere
    M-->>H: custo por porção com a conta de cada linha
    H->>M: cenarios_preco
    M->>A: cada cenário
    M-->>H: mínimo e três cenários, nenhum recomendado
    H->>M: testar_sensibilidade com o preço que ela propõe
    M-->>H: taxa, o que chega para ela e o lucro
    H->>M: registrar_decisao aceito, só quando ela decide
    alt a receita usa o que toda cozinha tem e ela não confirmou
        M-->>H: recusa com a pergunta, uma só
        H->>H: pergunta a ela: tem fogão e panela funda e sabe refogar?
        H->>M: registrar_resposta tipo cozinha, o sim dela
        H->>M: registrar_decisao aceito de novo
    end
```

O que toda cozinha tem (fogão, panela funda, faca, refogar, arroz) começa como
suposto e não vira pergunta item por item. O aceite e a compra, pela conversa
e pela tela, pedem que ela confirme o que a receita usa disso, numa pergunta
só (`mise/src/mise/certeza.py`); o checklist de produção de cada receita
(`mise/src/mise/checklist.py`) mostra, grupo por grupo, o que está confirmado,
suposto, pré-determinado com a fonte, ou ainda por saber.

Discordância do auditor segura o preço; auditor fora do ar deixa a conta seguir,
marcada como sem segunda opinião ([ADR 0005](adr/0005-auditor-independente.md)).
