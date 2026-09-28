# Roteiro da demonstração

Oito minutos, dentro dos 5 a 10 do enunciado, na ordem do §2.1 ao §2.4, que é a
mesma que o sistema impõe. Tudo pelo site, com o painel do agente aberto ao
lado das telas. As falas do agente mudam de uma gravação para outra; os
números não, porque saem do motor.

## Antes de gravar

- [ ] `make verificar` sem nenhum ✗.
- [ ] `make test` e `make evals` verdes.
- [ ] `make agente-status` diz que o chat pode conversar (gateway do Hermes no
      ar, as duas chaves, o modelo `claude-fable-5-1`).
- [ ] `make mcp` conecta o servidor `mise` e lista as ferramentas.
- [ ] Dossiê limpo, para a conversa não herdar teste. Pare a API e o gateway do
      Hermes (`hermes gateway stop`), mova a pasta `.estado/` para outro nome
      (não apague) e suba de novo (`hermes gateway start`); ou use "Restaurar os
      dados da planilha", nas Preferências, sem parar nada.
- [ ] `make demo` no ar (o mesmo que `make dev`, com a interface em modo de produção): API em `:8777`, interface em `http://localhost:3000`.
- [ ] Navegador em 1280 px de largura, tema claro, zoom 100%, notificações
      desligadas.
- [ ] O `make demo` diz "busca automática de receitas: ligada".
- [ ] Uma busca de teste pela conversa, para confirmar que a pesquisa na web
      responde.
- [ ] Um terminal aberto na raiz do repositório para o minuto 7.

Cada turno leva dezenas de segundos. Na edição, corte a espera; ao vivo, use o
tempo para mostrar a linha "o que o agente está fazendo".

## 0:00 · A despensa que veio da planilha

Abra **Despensa**. A tela mostra os 37 itens da planilha e os R$ 663,39 pagos,
cada custo com a conta ao lado (as alcaparras: "1 × 2 kg = 2 kg; R$ 82,00 ÷ 2 kg
= R$ 41,00/kg"). Aponte a cobertura de chocolate, comprada como "1 un" sem
peso. O motor não chuta nem pergunta; usa o peso de uma embalagem de
supermercado com preço próximo, marcado como estimativa e com a fonte, que ela
pode corrigir.

> "Seis dos 37 itens dão custo errado se você dividir preço por quantidade, porque
> a unidade mistura grandeza e embalagem. O motor normaliza antes de dividir."

## 1:00 · Receitas reais

Abra **Receitas** e clique em "Procurar mais receitas". O agente procura em
segundo plano (até 8 pesquisas e 20 páginas), e a grade enche enquanto ele lê:
cada receita com foto, site, tempo e quanto aproveita da despensa, na aba "Dá
para fazer" ou "Falta uma resposta sua". A que a cozinha dela não permite não
aparece. No painel, o mesmo vale pela conversa: "Me acha umas receitas de
verdade que usem o que eu tenho parado aqui."

> "O modelo não escreve no catálogo. O servidor buscou a página, leu a receita
> estruturada e deu um id; daqui em diante a receita anda por esse id."

## 2:30 · Equipamento e técnica antes de qualquer compra

Escolha uma receita da aba "Falta uma resposta sua". O agente pergunta
primeiro se ela gosta de fazer o prato e, depois, uma coisa por vez, o que falta
saber da cozinha (forno, bocas do fogão, tempo por cozinhada, se ela domina a
técnica). Peso, medida e preço ele não pergunta, porque vêm estimados, com a
fonte. Responda "não tenho" para um equipamento que a receita exige, e a
receita sai das candidatas, com o motivo. Responda "não sei" para outra coisa,
e ela fica em aberto, nunca como "tem".

> "Isso é código, não instrução: sem essa conferência, nenhuma ferramenta de
> preço, compra ou aceite roda."

## 4:00 · O que tem, o que falta e os R$ 80

Abra o detalhe de uma receita que dá comprando. Mostre, ingrediente por
ingrediente, quanto a receita pede, quanto ela tem e o que falta, com o custo da
compra e se cabe no que resta dos R$ 80,00. O preço do que falta é a média de
São Paulo em vários supermercados, marcado como estimativa, com as fontes e um
"corrigir" para o preço dela.

## 5:00 · O aceite, a conta e a escolha dela

Diga que gosta do prato e peça o preço. O agente mostra o custo por porção
linha a linha, o mínimo sem prejuízo (`CMV ÷ 0,90`, arredondado para cima) e três
cenários, sem recomendar nenhum. Proponha um preço seu: ele mostra a taxa de
10%, o que chega para a senhora e o lucro. Antes do aceite, ele pede numa
pergunta só que ela confirme o que toda cozinha tem e a receita usa; responda
que sim. Decida. O prato vai para o **Cardápio**.

## 6:00 · Editar na tela e ver recalcular

Em **Despensa**, mude o estoque de um ingrediente da receita; em **Cozinha**,
troque a resposta de um equipamento. Volte a **Receitas**: a aba e o que falta
comprar mudaram sozinhos. Mostre o "Desfazer".

## 7:00 · O número sem origem não passa

No terminal:

```bash
mise/.venv/bin/python -m pytest -q hermes/plugins/guardrail-numerico -k "redige" -p no:cacheprovider
mise/.venv/bin/python -m pytest -q mise/tests/unit/test_mcp_server.py -k "auditor" -p no:cacheprovider
```

> "O guard-rail confere cada valor da resposta contra o que o motor devolveu e o
> que ela disse; o que não tem origem vira '[valor retirado]'. O auditor refaz a
> conta com outro código; se discordar, o preço não sai."

Mostre em `docs/transcricoes/antes-das-correcoes/LEIA.md` o caso real em que o
guard-rail retirou números e o que isso ensinou.

## 7:40 · Preferências

Clique na engrenagem no canto do cabeçalho: tema claro, escuro ou automático,
tamanho do texto, movimento, apagar conversas, baixar os dados e o modelo em
uso. Troque para o escuro e feche.
