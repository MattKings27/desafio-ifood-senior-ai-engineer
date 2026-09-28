# Contratos da web (v1)

Os arquivos desta pasta são o acordo entre a interface (`webapp/`) e a API
(`gateway/`). Cada `.json` mostra o campo `dados` do envelope de uma rota, com
valores reais da planilha da Dona Maria. Os `.jsonl` mostram, evento por
evento, o fluxo do turno e o da descoberta. A pasta `cartoes/` tem um card de exemplo de cada tipo.

Os testes do backend conferem que as rotas devolvem esta forma; os testes do
front leem estes arquivos como fixture. Quem mudar uma forma muda o arquivo
aqui, no mesmo PR, e atualiza todos os espelhos: este LEIA, os tipos em
`webapp/src/lib/api/*.ts`, os mapas de chaves de
`webapp/src/lib/api/dominios.test.ts` e o motor falso
(`webapp/e2e/motor-falso/servidor.mjs`). Os dois lados ficam vermelhos até
concordarem.

## Regras que valem para todas as rotas

- **Envelope** igual ao de hoje (`responder` em `gateway/src/gateway/rotas/_comum.py`):
  `{ok, dados, erro, categoria, pergunta}`. Categoria nova: `ausente` (HTTP 404),
  para item, receita ou conversa que não existe. As exceções são arquivos para
  baixar (`/api/despensa/planilha.txt`, `/api/exportacao`) e as imagens.
- **Dinheiro** sempre como `{"valor": 2.47, "texto": "R$ 2,47"}`. A interface
  mostra `texto` e usa `valor` só para ordenar e filtrar o que já recebeu. Nunca
  soma, subtrai, multiplica ou divide.
- **Todo número calculado** vem com `derivacao` (a conta escrita, em pt-BR, com
  vírgula decimal).
- **Quantidades e datas** vêm prontas em `*_texto` (`"0,5 kg"`, `"hoje, 14:32"`).
  O cliente não formata data.
- **Sem jargão** em nenhum texto que chega a ela: nada de motor, portão, APTO,
  FALTA INFO, BLOQUEADO, veredito, CMV, food cost. O campo `veredito` continua
  existindo como valor técnico (`APTO`, `APTO COM COMPRA`, `FALTA INFO`,
  `BLOQUEADO`); o que a tela mostra é `veredito_rotulo` (`Dá pra fazer`,
  `Dá, comprando`, `Falta saber`, `Não dá`).
- **Imagens** sempre por `{"url": "/motor/imagens/<chave>", "credito": "..."}`,
  ou `null`. A `chave` são os 32 primeiros caracteres hexadecimais do sha256 do
  endereço original da foto. A interface nunca carrega imagem de outro endereço.
  A API só serve foto registrada: a dos itens da planilha (Wikimedia Commons,
  licença livre, crédito "Foto: <autor>, <licença>, Wikimedia Commons", em
  `dados/fotos_ingredientes.json`), a miniatura de cada equipamento e técnica
  da cozinha (as mesmas regras, em `dados/fotos_cozinha.json`) e a que a página
  de uma receita declarou
  quando o servidor a leu (crédito "Foto: <site>"). O item que ela acrescenta
  não tem foto (`null`), nem o item da planilha sem foto livre que o mostre de
  verdade (o adoçante líquido: o motivo fica em `sem_foto`, no mesmo arquivo). Chave desconhecida é 404; a foto passa pelas mesmas
  travas da página (endereço público, até 5 MB, tipo pelos bytes: JPEG, PNG,
  WebP, AVIF ou GIF, nunca SVG) e fica em cache em `.estado/imagens/`.
- **Ids:** ingrediente da planilha = slug do nome (`alcaparras`); ingrediente
  adicionado = `item-<8 hex>`; receita = `slug`, que as ferramentas chamam de
  `receita_id` (16 hex do sha256 da URL canônica, ou slug do nome quando ela
  ditou a receita). URL canônica: host minúsculo sem `www.`, caminho sem barra
  final, sem esquema, consulta nem fragmento.

## Tabela de decisões

Quem precisar mudar uma linha muda aqui primeiro.

| Assunto | Decisão |
|---|---|
| Abas da lista de receitas | `aba=pode_fazer\|falta_resposta\|ranking\|nao_quer` (substitui `todas\|avaliacao\|ranking`) |
| Custo por porção de uma receita | `GET /api/receitas/{slug}/custo` em todo lugar (sai `/api/custo?prato=`) |
| Conferência de uma receita | vem dentro de `GET /api/receitas/{slug}`; sai `/receitas/{slug}/avaliar` do cliente, e pôr preço numa receita é pela conversa |
| Preço preliminar (e o card) | `GET /api/receitas/{slug}/estimativa` (sai `POST /api/estimativa`) |
| Imagens | `GET /api/imagens/{chave}`, chave = 32 primeiros hex do sha256 do endereço original; a web usa `/motor/imagens/<chave>` |
| Referência de mercado | não entra nesta versão: `referencias_de_mercado` vem sempre `[]`, com a frase que diz que não há preço conferido |
| Guard-rail v2 | confere valores em R$ e quantias escritas como "reais"; porcentagem e quantidade ficam fora |
| Card "De onde eu tirei isso" | tipo `fontes`, da `consultar_conhecimento`, com chips `{rotulo, rota}` |
| Seus dados | `GET /api/exportacao` baixa tudo o que ela tem, em `sabor-da-maria-dados.json` |
| Restaurar os dados | `POST /api/dados/restaurar {confirmar: true}` volta tudo à planilha, dentro dos mesmos arquivos, depois de guardar uma cópia; ficam as receitas lidas e as fotos |
| Aceite e compra | só com a cozinha confirmada: o que toda cozinha tem e a receita usa (fogão, panela funda, refogar) começa suposto, e `POST /api/decisao` (aceito), `POST /api/compra` e as ferramentas `registrar_decisao` e `registrar_compra` recusam com categoria `regra` e a `pergunta`, uma só, até ela confirmar (`POST /api/perfil/supostos/confirmar`). A grade continua com o veredito e ganha `nota_da_cozinha` |

## Rotas

| Método e caminho | Arquivo |
|---|---|
| `GET /api/visao-geral` | `visao-geral.json` |
| `GET /api/despensa` (lista, com `q`, `categoria`, `ordem`) | `despensa.json` |
| `GET /api/despensa/itens/{id}` | `despensa-item.json` |
| `POST /api/despensa/itens` · `PATCH|DELETE /api/despensa/itens/{id}` | `despensa-escrita.json` (`despensa-item-comprado.json` é o item comprado com os R$ 80,00) |
| `GET /api/despensa/eventos` · `POST /api/despensa/eventos/{id}/desfazer` | `despensa-eventos.json` |
| `GET /api/despensa/planilha.txt` | texto UTF-8 (ver `despensa-planilha.txt.exemplo`) |
| `POST /api/compras/{id}/estorno` | `despensa-escrita.json#estorno` |
| `GET /api/receitas` (`aba`, `q`, `usa`, `tempo_max`, `so_com_o_que_tenho`, `nota_min`, `ordem`) | `receitas.json` |
| `GET /api/receitas/{slug}` | `receita.json` |
| `POST /api/receitas {url}` | `receita.json` (a receita trazida, já no catálogo; 201 nova, 200 já lida) |
| `POST /api/receitas/{slug}/resposta {campo, resposta, por_unidade?}` | `receita.json` (a receita conferida de novo) |
| `GET /api/receitas/{slug}/custo` (custo por porção; passa pela conferência; 409 quando não libera) | `custo.json` |
| `GET /api/receitas/{slug}/estimativa` (preço preliminar) | `estimativa.json` |
| `GET|PUT /api/receitas/{slug}/avaliacao` | `avaliacao-escrita.json` (pedido do PUT; a resposta é a mesma no GET) |
| `PUT /api/receitas/{slug}/notas` | `notas-escrita.json` |
| `POST /api/receitas/descoberta` (202; 409 `ocupado` com a rodada que está rodando; 501 `regra` com a busca automática desligada) · `GET /api/receitas/descoberta/eventos[?execucao=]` (SSE; 204 sem nada a mandar; 404 para rodada que não existe) | `descoberta-inicio.json`, `receitas-descoberta.jsonl` |
| `GET /api/perfil` | `perfil.json` |
| `PUT /api/perfil/{equipamentos|tecnicas}/{id}` · `PUT /api/perfil/restricoes/{campo}` (o `impacto` conta as receitas em avaliação e as do catálogo que mudam de aba na grade) | `perfil-escrita.json` |
| `POST /api/perfil/supostos/confirmar` (`{}`, `{receita}` ou `{itens}`) | `perfil-supostos.json` |
| `GET|PUT /api/parametros/{nome}` | `estimativa.json#premissas[]`, `parametro-escrita.json` |
| `GET /api/cardapio` | `cardapio.json` |
| `POST /api/cardapio/{prato}/desfazer` · `PUT /api/cardapio/{prato}/notas` | `cardapio.json` |
| `GET /api/atividades` (`cursor`, `limite`, `q`, `categoria`, `quem`, `dia`) | `atividades.json` |
| `GET /api/imagens/{chave}` · `GET /api/imagens/{chave}/credito` | binário / `{credito, licenca, fonte_url}` |
| `GET /api/exportacao` | arquivo JSON para baixar (ver `exportacao.json`) |
| `POST /api/dados/restaurar {confirmar, id_cliente?}` (e `Idempotency-Key`) | `restauracao.json` |
| `GET|POST /api/conversas` · `GET|PATCH|DELETE /api/conversas/{id}` | `conversas.json`, `conversa.json` |
| `POST /api/conversas/{id}/turnos` · `GET .../turnos/{t}` · `GET .../turnos/{t}/eventos` (SSE) · `POST .../turnos/{t}/parar` | `conversa-turno.json`, `chat-eventos.jsonl` |

As rotas de hoje continuam (`/api/orcamento`, `/api/avaliar`, `/api/cmv`,
`/api/precos`, `/api/preco-em`, `/api/gosto`, `/api/preco-mercado`,
`/api/receita`, `/api/compra`, `/api/decisao`, `/api/resposta`). As que a tela
nova substitui (`/api/candidatas`, `/api/receita-da-web`, `/api/auditoria`,
`/api/escopos`) ficam até a interface parar de chamá-las.

Os módulos de rota já existem, registrados em `ROTEADORES`
(`gateway/src/gateway/rotas/`): `despensa.py`, `perfil.py`, `conversa.py`,
`receitas.py` (lista, detalhe, custo, avaliação, notas e descoberta),
`imagens.py`, `estimativa.py` (estimativa e parâmetros), `visao_geral.py`,
`cardapio.py`, `atividades.py` e `dados.py` (exportação e restauração).

## Restaurar os dados (`restauracao.json`)

"Restaurar os dados da planilha", nas Preferências, com confirmação.
`POST /api/dados/restaurar {confirmar: true}` guarda antes uma cópia do
dossiê, das conversas e da trilha do agente em
`<pasta do dossiê>/copias/<quando>/`, e então volta tudo ao que estava na
planilha: a despensa e os preços, os itens acrescentados e tirados, as compras e
os R$ 80,00, a cozinha, os gostos, as estrelas e as notas, as decisões e o
cardápio, as premissas do preço, as respostas sobre as receitas, as receitas
que ela ditou e as conversas. Ficam as receitas das páginas lidas (como a página
veio) e as fotos. Os arquivos não saem do lugar: o agente, que mantém o
dossiê aberto, vê o recomeço na leitura seguinte. Sem `confirmar`, recusa com
categoria `uso` e não mexe em nada.

A resposta: `texto` (a frase para ela, com 37 ingredientes, R$ 663,39 e os
R$ 80,00), `mudou` (`false` quando já estava tudo como na planilha),
`conciliacao{ingredientes, total_pago, orcamento_inicial, orcamento_restante,
cozinha_texto, texto}`, `apagado` (quantas linhas saíram de cada coisa, dita
para ela), `mantido{receitas, texto}`, `copia` (o nome da pasta da cópia, que
não vai para a tela), `recursos` (todas as telas: é o `estado.alterado` de cada
domínio) e `repetida` (a mesma chave de clique já tinha restaurado, e nada foi
feito de novo). `make conciliar` confere, item por item, que a plataforma
restaurada mostra a planilha crua. Rota nova entra no módulo da área, sem mexer no registro.

## Despensa

Os exemplos são respostas da API de verdade, com a planilha da Dona Maria e
duas mudanças dela: o creme de leite comprado com os R$ 80,00 (para o arroz
com frango) e a farinha de rosca que ela já tinha, sem o preço. As fotos de
três itens mostram a forma da `imagem`; enquanto a busca de fotos não chega, a
API manda `null`.

### A lista (`despensa.json`)

`{itens, total_investido, total_itens, encontrados, categorias,
categorias_para_escolher, pendencias, orcamento}`. `q` procura no nome sem
ligar para acento e caixa, `categoria` filtra pelo id, e `ordem` é `valor` (o
que mais custou primeiro, o padrão), `nome`, `custo` (custo por unidade, o
desconhecido por último) ou `categoria`. `total_itens` e `categorias` contam a
despensa inteira, com ou sem filtro; `encontrados` conta o que o filtro deixou.
`categorias` são as que têm item (`{id, rotulo, quantidade}`);
`categorias_para_escolher` são todas (`{id, rotulo}`, com `outros`), para o
formulário de um item novo.

Cada item: `id`, `nome`, `categoria`, `categoria_rotulo`, `estoque` e
`unidade` (na unidade-base: `kg`, `L` ou `un`), `estoque_texto`, `pago`
(`null` quando ela não disse o preço), `custo_unitario` (`null` quando não dá
para saber), `derivacao`, `confianca` (`alta`, `media`, `desconhecida`) e
`confianca_rotulo`, `fracao_do_total` e `fracao_texto`, `origem` (`planilha`,
`ja_tinha`, `orcamento`) e `origem_rotulo`, `imagem`, `receitas_que_usam` e
`receitas_que_usam_texto`, `pendente` e `rota`. Os campos da tela antiga
(`custo_texto`, `custo_ingenuo`, `normalizacao_importou`, `rotulo_original`)
ainda saem da API e não fazem parte do contrato.

`pendencias` vem sempre vazia nesta versão. O peso da embalagem e o preço que
a planilha não diz não viram pergunta a ela; saem com a fonte, ditos como
estimativa, e ela corrige quando quiser pelo `PATCH` do item
(`{conteudo_da_embalagem: "1 kg"}` ou `{preco_pago, quantidade_comprada}`). Os
exemplos desta pasta ainda trazem as pendências da versão anterior.

`orcamento{inicial, restante, gasto, fracao_gasta, texto, compras}`: as
compras ativas com os R$ 80,00, cada uma `{id, descricao, ingrediente,
item_id, valor, quando_texto, canal, estornada, estorno, pode_estornar,
rota_estorno}`. `estornada` diz que ela já voltou; `estorno`, que a linha é a
própria devolução.

### O item (`despensa-item.json`, `despensa-item-comprado.json`)

O item da lista mais `comprado_texto` ("2 kg por R$ 28,00"),
`unidade_compra_rotulo` (a unidade em que ela comprou, como a API guarda:
`kg`, `un 200g`), `pendencia` (sempre `null` nesta versão), `receitas[{slug, nome, veredito, veredito_rotulo, imagem, usa_texto,
rota}]`, `historico[]` (a forma de um evento, abaixo, com a linha da planilha
primeiro), `compras[]` (a forma das compras do orçamento) e `rascunho_chat`.
Item que não existe (ou que saiu) responde `ausente` (404).

### As mudanças (`despensa-eventos.json`)

`GET /api/despensa/eventos?limite=&cursor=` devolve `{eventos, proximo_cursor,
total, versao}`, do mais novo para o mais antigo; `proximo_cursor` é o `id` do
último da página, ou `null` na última. Cada evento: `id` (`planilha` na linha
da planilha, depois `ev-NNNN`), `tipo` (`planilha`, `adicionar`, `corrigir`,
`remover`, `restaurar`), `acao` (o que ela fez: `adicionar`, `corrigir`,
`acabou`, `informar_embalagem`, `remover`, `estorno`, `desfazer`), `texto`,
`quando_texto`, `canal` (`planilha`, `tela`, `conversa`), `pode_desfazer` (só a
última mudança de cada item), `desfaz` (o evento que este desfez, ou `null`),
`item_id`, `item_nome`, `motivo` e `rota`.

### As escritas (`despensa-escrita.json`)

`POST /api/despensa/itens {nome, estoque, unidade, quantidade_comprada?,
preco_pago?, origem, categoria?, receita?, id_cliente}`. `origem` é `ja_tinha`
(não mexe nos R$ 80,00) ou `orcamento` (debita na hora, e pede `preco_pago`).
`unidade` é uma das que a conta lê: `kg`, `g`, `L`, `ml`, `un`, ou a
embalagem com o peso (`un 200g`, `pacote 500 g`); `estoque` e
`quantidade_comprada` vão nessa unidade (em `un 200g`, o número de
embalagens). `PATCH /api/despensa/itens/{id}` recebe só o que mudou
(`estoque`, `unidade`, `quantidade_comprada`, `preco_pago`, `categoria`,
`conteudo_da_embalagem`). A `unidade` nova vale também para o `estoque` e a
`quantidade_comprada` que ficaram: quem troca a unidade manda os dois nela. O
nome não muda (categoria `uso`).
`{estoque: 0}` é "acabou". `DELETE /api/despensa/itens/{id}` tira o item e,
se ele veio dos R$ 80,00, devolve. `POST /api/despensa/eventos/{id}/desfazer`
desfaz a última mudança de um item (e debita de novo, se ela devolver uma
compra). A chave de idempotência vai em `Idempotency-Key` ou `id_cliente`: o
mesmo clique reenviado responde `repetida: true` e não grava de novo.

A resposta de todas: `item` (a forma da lista, ou `null` quando o item saiu),
`id`, `ingrediente`, `repetida`, `evento` (o `id` do evento, para o
Desfazer), `removido`, `estorno` e `compra` (dinheiro, ou `null`),
`pendencias_resolvidas` (sempre `[]` nesta versão), `pendencia` (sempre
`null`),
`receitas_afetadas{liberadas, bloqueadas, mudaram[{receita, antes, depois}],
texto}`, `orcamento` e `texto` (a frase do aviso). A API também manda `mudou`,
`antes`, `depois` e `orcamento_mudou`, fora do contrato.

`POST /api/compras/{id}/estorno` devolve a compra aos R$ 80,00 (o item que ela
acrescentou sai junto) e responde `{compra_id, estorno_id, estorno, removido,
receitas_afetadas, orcamento, texto}`. Devolver de novo não devolve duas vezes.

## Cozinha

### O perfil (`perfil.json`)

`{completude, respondidos, supostos, em_aberto, fracao_respondida, resumo,
progresso_texto, equipamentos, tecnicas, restricoes}`. `respondidos` é o que
ela mesma respondeu com "tem" ou "não tem"; `supostos`, o que está como "tem"
só porque qualquer cozinha tem; `em_aberto`, o resto (inclusive o que ela
respondeu "não sei"). `progresso_texto` ("3 de 63 respondidos pela senhora") é
a conta de `fracao_respondida` em texto, e `resumo` separa o que ela disse que
não sabe do que ainda não foi perguntado. `completude` conta também o suposto,
e não vai para a tela.

Cada equipamento e técnica: `id`, `nome`, `categoria` (a do vocabulário:
`cocção`, `preparo`, `frio`, `medição`, `utensílio`; `básica`, `massas`,
`molhos`, `carnes`, `confeitaria`, `avançada`), `estado` (`tem`, `nao_tem`,
`desconhecido`), `pressuposto` (técnica: `pressuposta`) e `suposto`,
`dificuldade` (só técnica), `pergunta`, `imagem` (a miniatura do Commons,
`{url, credito}`, ou `null` quando não há foto livre que mostre o item: a
tela mostra o ícone), `receitas_afetadas` e
`receitas_afetadas_texto` (quantas receitas em avaliação pedem o item),
`atualizado_por` (`tela`, `conversa` ou `null`), `atualizado_texto` e
`nao_sei`. `estado: desconhecido` com `nao_sei: true` é "a senhora disse que
não sabe", nunca "ainda não perguntei".

Cada restrição (`bocas_fogao`, `tempo_max_por_fornada_min`,
`porcoes_por_fornada`, `espaco_geladeira_litros`,
`energia_aparelhos_simultaneos`, `tem_gas_sobrando`): `valor` (número, sim ou
não, ou `null`), `tipo` (`inteiro`, `horas` ou `sim_nao`), `unidade`, `min` e
`max` (no inteiro e nas horas), `pergunta`, `atualizado_por`,
`atualizado_texto` e `nao_sei`. O tempo por cozinhada
(`tempo_max_por_fornada_min`) é `tipo: horas`: o motor guarda minutos, e a
tela lê e escreve em horas (`valor` 1.5 é uma hora e meia), com `passo` (o + e
o −, de meia em meia hora), `casas` (até duas) e `valor_texto` ("1,5 hora",
"2 horas", ou `null`). A pergunta de uma receita sobre esse limite traz a
mesma `entrada` (`receita.json#perguntas[].entrada`, com `tipo: horas`).

`toda_cozinha{titulo, texto, a_confirmar, a_confirmar_texto, tudo_confirmado,
itens[{tipo, id, nome, imagem, estado, status, status_texto}]}` é o bloco "O que
toda cozinha tem": os equipamentos e as técnicas que a plataforma supõe de
qualquer cozinha, na ordem da taxonomia, com a foto. `status` é `suposto`
("suposto: confirme", ninguém perguntou), `confirmado` ("a senhora tem", "a
senhora faz"), `nao_da` ("a senhora não tem") ou `falta_saber` ("a senhora não
sabe", "falta saber"); `a_confirmar` conta os supostos, e com zero
`tudo_confirmado` é `true` e o `texto` diz que ela já respondeu tudo.

### O que toda cozinha tem (`perfil-supostos.json`)

`POST /api/perfil/supostos/confirmar` grava o sim dela, pelo mesmo caminho de
uma resposta (o histórico da cozinha com o canal): `{}` confirma tudo o que
ainda está como suposto (o "Tenho tudo isso"), `{receita: slug}` o que a
receita usa disso (a pergunta do aceite) e `{itens: [{tipo, id}]}` só esses
itens (`tipo` é `equipamento` ou `tecnica`). O "Não tenho" de um item é o `PUT`
de sempre, com `nao_tem`. Responde `{confirmados[{tipo, id, nome}], texto,
perfil, toda_cozinha}`: `texto` é a frase para ela ("Anotei: a senhora tem
fogão e sabe refogar."), `perfil` as contagens de `perfil-escrita.json` e
`toda_cozinha` o bloco como ficou. Confirmar de novo não grava nada.
Receita ou item que não existe é `ausente` (404); `receita` e `itens` juntos é
`uso`.

### As escritas (`perfil-escrita.json`)

`PUT /api/perfil/{equipamentos|tecnicas}/{id} {estado: tem|nao_tem|nao_sei}`
e `PUT /api/perfil/restricoes/{campo} {valor}` (`null` é "não sei"; a faixa é
conferida pela API, que recusa com a frase para ela; o tempo por cozinhada vai
em horas, `{valor: 1.5}`). Respondem `{item,
impacto{liberadas, bloqueadas, pendentes, texto}, perfil}`: `item` com a forma
do GET (a restrição com o `id`), o impacto nas receitas em avaliação pela
mesma conferência das receitas, e `perfil` com as contagens, `resumo` e
`progresso_texto`.

## Receitas

Há dois conjuntos, e não se misturam. O **catálogo** é tudo o que o servidor leu
de uma página (pela descoberta, pela conversa ou pelo endereço que ela trouxe) e
as receitas que ela ditou; só código do servidor escreve nele. As receitas **em
avaliação** são as que ela escolheu conversar (as que passaram por
`avaliar_receita` ou `calcular_cmv`): é só sobre elas que o agente pergunta
(`proxima_pergunta`, `comparar_candidatas`, o impacto de uma mudança na
despensa). A grade lê o catálogo e passa cada receita pela conferência de agora,
sem gravar nada: abrir a tela não põe receita em avaliação.

Cada receita tem um `slug` (o `receita_id` das ferramentas) e um nome único no
dossiê, sem ligar para caixa e acento: é pelo nome que o gosto, a decisão e o
cardápio se referem ao prato. A receita da internet que chega com o nome de
outra ganha o site entre parênteses ("Bolo de fubá (Panelinha)"); a que ela dita
com o nome de uma receita da internet é recusada com o `receita_id` da outra.

### A lista (`receitas.json`)

`{aba, contagens, itens, descoberta, perguntas_que_liberam, esperando_resposta,
sem_preco_na_internet}`. A grade só mostra o que ela consegue
fazer; o que a cozinha dela não permite nunca aparece, em aba nenhuma. A aba sai
da conferência **sem o gosto** (`receita.json#veredito_da_cozinha`): senão toda
receita ficaria em "falta saber" até ela dizer se gosta de cada uma.

| `aba` | O que entra |
|---|---|
| `pode_fazer` | dá com o que ela tem, ou comprando o que falta dentro do que resta dos R$ 80,00 |
| `falta_resposta` | falta uma resposta dela; cada item traz a `pergunta`, respondida ali mesmo |
| `ranking` | as que ela avaliou com estrelas, entre as que dá para fazer, pela pontuação; as que ela não quer vão por último |
| `nao_quer` | as que ela disse que não gosta de fazer, ou em que viu um impedimento, para ela poder mudar de ideia |

`contagens` tem o total de cada aba, com os mesmos filtros. Filtros: `q` (no
nome, no site e nos ingredientes, sem ligar para caixa e acento), `usa` (o id de
um item da despensa), `tempo_max` (minutos; receita sem tempo dito não entra),
`so_com_o_que_tenho` (sem nada a comprar), `nota_min` (pontuação mínima; sem
avaliação não entra). `ordem`: `aproveitamento` (a que usa mais do que ela tem,
depois a que pede menos compra; padrão de `pode_fazer` e `falta_resposta`),
`pontuacao` (a do ranking; padrão de `ranking`), `compra`, `tempo` e `recentes`
(padrão de `nao_quer`). Aba ou ordem que não existe responde 422, categoria
`uso`.

Cada item de `itens`: `slug`, `nome`, `imagem`, `site` (`null` na receita que
ela ditou), `tempo_texto`, `selo{codigo, texto}`, `usa_texto`, `falta_texto`,
`pontuacao{valor, texto}` ou `null`, `gosta` (`true`, `false` ou `null` quando
ela ainda não disse), `pergunta` (a forma de `receita.json#perguntas[]`; só em
`falta_resposta`, senão `null`), `referencias[]` (o que falta comprar cotado por
preço de referência, a forma de `custo.json#ingrediente_com_preco_de_referencia_exemplo.referencia`;
vazio quando o preço é dela ou não há o que comprar), `nota_da_cozinha` e `rota`.
A tela mostra o `texto` de cada referência com o link da fonte e um "Corrigir o
preço", que manda o preço dela para `POST /api/preco-mercado`: o dela sempre vale mais.
`nota_da_cozinha` é "Confirme a cozinha" na receita que dá para fazer apoiada no
que toda cozinha tem e ela ainda não confirmou (o aceite vai pedir), senão
`null`; o selo continua o da conferência.
`selo.codigo` é `com_o_que_tem`, `comprando` ou `falta_resposta`; o texto é o que
a tela mostra ("Com o que a senhora tem", "Comprando R$ 6,00, cabe nos R$ 80,00").

`descoberta{estado, lidas, encontradas, texto}`: `estado` é `parada`,
`procurando` ou `erro`; `lidas` são as páginas lidas e `encontradas`, as
receitas que entraram no catálogo. Durante uma rodada, `procurando` com os
números dela; depois, o resultado da última rodada (`parada` ou `erro`, com o
texto do que aconteceu na língua dela). Sem rodada desde que a API subiu, o
estado é `parada` e as contagens são as receitas que a descoberta trouxe para
o catálogo. Os mesmos itens chegam pelo fluxo da descoberta
(`receitas-descoberta.jsonl`, evento `receita.encontrada` com a `aba` onde a
receita entra). `visao-geral.json#receitas_recomendadas` usa a mesma forma de
item.

`perguntas_que_liberam[{pergunta, receitas, liberadas, sem_compra,
sem_compra_texto, nomes[], slugs[], rota, texto}]`: as perguntas da cozinha
(equipamento, técnica, rotina) das receitas de `falta_resposta` (com os mesmos
filtros), uma só para todas as receitas que a fazem, as que mexem em mais
receitas primeiro, no máximo 5. Preço, peso, medida, rendimento, tempo no fogo
e item parecido nunca entram aqui, porque não são pergunta; saem com a fonte,
como estimativa, e ela corrige pelo `editar` da receita. `pergunta` tem a forma
de `receita.json#perguntas[]` (com mais de uma receita, `motivo` vazio, e os
`nomes` dizem quais). `receitas` são as que esperam por ela; `liberadas`, as
que não esperam por mais nada; `texto` diz isso sem exagero ("libera 3
receitas", "ajuda a liberar 2 receitas", "libera 1 receita e ajuda outra").
`sem_compra` são as que esperam por ela e usam só o que ela tem (a forma de
`esperando_resposta`), com `sem_compra_texto` ("7 delas usam só o que a
senhora tem", "todas usam só o que a senhora tem") ou `null` quando nenhuma usa.
`slugs` acompanham `nomes`, na mesma ordem; `rota` é a da receita, quando é
uma só, ou `/receitas?aba=falta_resposta`. Só entra o que ela responde ali
mesmo; o modo de preparo da receita que ela ditou, que só a conversa resolve,
segura a receita, mas não vem aqui. A tela mostra o
painel quando a aba `pode_fazer` está vazia e há receita esperando resposta.

`esperando_resposta{receitas, so_com_o_que_tem, precisa_comprar,
linha_sem_leitura, nomes[], slugs[], falta_dizer[], texto}`, ou `null` quando
nenhuma receita de `falta_resposta` passa nos filtros: em que pé estão as
receitas que esperam uma resposta, pela despensa. Com a cozinha nova toda
receita espera uma resposta e "Dá para fazer" fica vazia; a verdade não é
"nada dá", é "ainda não confirmei". `so_com_o_que_tem` são as que não pedem
compra nenhuma (ela tem cada linha, a linha vai a gosto, ou é o opcional que
fica de fora) e esperam só o que ela responder, com os `nomes` e os `slugs`;
`precisa_comprar`, as que pedem alguma compra; `linha_sem_leitura` fica em 0
nesta versão, porque a receita com uma linha sem fonte fica de fora com o
motivo, sem esperar resposta. `falta_dizer` são as perguntas da cozinha
(equipamento, técnica, rotina) que seguram as primeiras, das que seguram mais
para as que seguram menos, como se dizem no meio da frase ("quanto tempo
consegue ficar cozinhando de uma vez", "se tem panela de pressão"). `texto` é a
frase pronta, a mesma que o agente recebe em `comparar_candidatas`: "7
receitas usam só o que a senhora tem; falta só a senhora me dizer quanto tempo
consegue ficar cozinhando de uma vez e se tem panela de pressão. 4 receitas
pedem alguma compra." ou, sem nenhuma, "Nenhuma das 11 receitas que esperam
resposta usa só o que a senhora tem: todas pedem alguma compra.". A tela mostra
o `texto` no alto de "Falta uma resposta sua" e no lugar do "nada dá" quando
`pode_fazer` está vazia.

`sem_preco_na_internet{receitas, nomes[], slugs[], texto}`, ou `null` quando
nenhuma: as receitas (com os mesmos filtros) que a cozinha dela faz e que
ficaram de fora só porque o preço de algum ingrediente não se achou em página
de supermercado. O preço não se pergunta: sem ele, não dá para confirmar que a
compra cabe nos R$ 80,00, e a receita não aparece em aba nenhuma. `texto` é a
frase pronta ("4 receitas ficaram de fora porque não achei em página de
supermercado o preço de algum ingrediente; se a senhora souber o preço, eu
confiro de novo."); o preço que ela disser vale, por `POST /api/preco-mercado`.

### A descoberta (`descoberta-inicio.json`, `receitas-descoberta.jsonl`)

`POST /api/receitas/descoberta` começa uma rodada em segundo plano e responde
202 na hora, com `{execucao_id, estado, texto, eventos}` (`eventos` é o fluxo
desta rodada). A rodada é do agente rodando como serviço: um pedido fixo
(`hermes/prompts/descoberta.md`) numa sessão nova do Hermes, que chama
`pauta_de_descoberta`, faz até 8 pesquisas e traz até 20 páginas por
`buscar_receita_na_web`; só o servidor escreve no catálogo, e só receita de
página com receita estruturada. Uma rodada por vez: com uma em andamento, a
resposta é 409, categoria `ocupado`, com a que está rodando em `dados` (a tela
se anexa a ela). Com o agente no meio de uma conversa, a rodada espera o
turno terminar (o `texto` diz isso) e começa sozinha. A busca automática custa
dinheiro a cada rodada e só roda com `SABOR_DESCOBERTA=ligada` (o `make dev`
liga; os testes e o CI, não): desligada, a resposta é 501, categoria `regra`,
com o motivo, e a tela abre a conversa com o pedido escrito. Ler a grade nunca
começa uma rodada: quem começa é a tela, pelo botão e na primeira visita com o
catálogo vazio.

`GET /api/receitas/descoberta/eventos` é SSE, como o do turno: `id: <seq>` e
`data:` com `{seq, tipo, ...}`, retomada por `Last-Event-ID` ou `?desde=`,
`: keepalive` a cada 10 s e 204 quando não há mais nada a mandar. Sem
`execucao`, é a rodada de agora ou a última. Os eventos: `progresso` (`etapa`
`esperando`, `pesquisando` ou `lendo`, com o `texto` e os números),
`receita.encontrada` (a receita que entrou nesta rodada, na forma do item da
grade, com a `aba`; a que a cozinha dela não permite entra no catálogo, conta
em `encontradas` e não vira evento) e `fim` (`estado` `parada` ou `erro`).

### O que a plataforma estabelece sem perguntar

À Dona Maria só se pergunta o que é dela: se gosta de fazer o prato e se vê
impedimento, equipamento, técnica e os limites da rotina (bocas, gás,
geladeira, energia, e o tempo por cozinhada quando é apertado), e o modo de
preparo da receita que ela mesma ditou. Peso, medida, quantidade, preço e "é o
seu X?" nunca viram pergunta, em lugar nenhum (grade, detalhe, checklist,
Início, Despensa, ferramentas): saem com a fonte, ditos como estimativa quando
são, e ela corrige quando quiser (o `editar` do checklist, na forma de
`perguntas[]`, pelas mesmas rotas de resposta). Quando fonte nenhuma diz o
número, a receita fica de fora, com o motivo, e ninguém pergunta.

- **preço médio em São Paulo** (`dados/precos_de_referencia.json`): o preço do
  que falta comprar e ela não cotou, pela média de vários supermercados de São
  Paulo (Mambo, Coop, Oba Hortifruti, Atacadão, Swift, Savegnago, Covabra e
  Casa Santa Luzia). Cada fonte é um produto lido pelo servidor no catálogo do
  mercado (a busca VTEX com a região de um CEP de São Paulo), com o conteúdo
  da embalagem, o preço, o endereço, a data e o trecho literal da resposta. A
  média é a do preço do quilo (do litro, da unidade); com 3 fontes ou mais, a
  que fica mais de 50% longe da mediana sai da conta. Ela compra a menor
  embalagem que cobre o que falta, pelo preço médio; a compra continua tendo de
  caber nos R$ 80,00. O objeto `referencia` traz `titulo` ("Preço médio em São
  Paulo"), `preco_medio_texto` ("R$ 16,60 o quilo"), `media_texto` ("média de
  6 mercados de São Paulo: R$ 14,95, R$ 16,45, ... o quilo, em 27/09/2026") e
  `fontes[]`, um por mercado: `site`, `produto`, `preco_texto` ("R$ 2,99 por
  200 g"), `por_unidade_texto` ("R$ 14,95 o quilo"), `url`, `data_texto` e
  `na_media` (`false` para a que ficou fora da média). Os campos de antes
  continuam: `texto`, `preco_texto`, `produto`, `site`, `url`, `data_texto`.
  O item da despensa sem o preço que ela pagou também custa pela referência.
  Sem preço nenhum, a receita fica de fora e conta em
  `receitas.json#sem_preco_na_internet`;
- **medidas** (`mise.unidades.MEDIDAS_DE_REFERENCIA`): o peso de uma unidade e
  das medidas caseiras, pela Tabela de Medidas Referidas do IBGE (POF
  2008-2009) e, no que ela não diz, pela tabela de porções do USDA (FoodData
  Central, SR Legacy): a pitada de pimenta-do-reino, a colher de chá de
  páprica, a xícara de extrato de tomate, de damasco, de farinha de amêndoa e
  de coco ralado, a colher de sopa de alcaparras e de salsinha. Sem linha para
  o próprio ingrediente, vale a de uma classe, com a base citada e dita como
  estimativa: a folha de erva (louro), o ramo de erva (alecrim), a pimenta
  ardida, o bacon em cubinhos, o maço de verdura de folha (couve), o tempero em
  pó (cominho) e o pedaço de toucinho (couro do bacon). "1 pacote de feijão
  preto", de um item que ela tem, é o pacote da planilha dela;
- **quantidade que a receita não diz** ("Milho", sem número): a unidade de
  venda do ingrediente, a embalagem que ela comprou (pela planilha) ou a da
  página do produto de referência ("a receita não diz quanto; considerei 1 lata
  de 170 g (Milho Verde Quero Lata 170g, no Savegnago, 27/09/2026)"), no
  checklist como `pre_determinado` (`tipo: quantidade`). Tempero sem quantidade
  vai a gosto;
- **o item parecido** ("mandioca" e a farinha de mandioca dela, "canela" e a
  canela em pó): a marca sai antes de comparar ("Queijo Parmesão TIROLEZ
  ralado" é o parmesão dela), e a forma do produto decide (farinha, fubá,
  polvilho, extrato, caldo, molho, creme, leite, óleo, suco e o que é em pó são
  outro produto). Na dúvida, não é o dela: vira compra, e a decisão vem dita
  ("Considerei que mandioca não é a sua farinha de mandioca: farinha é outro
  produto..."), no checklist como `pre_determinado` (`tipo:
  mesmo_ingrediente`), com o `editar` "É, sim / Não é". O sinônimo que é uma
  decisão ("couro do bacon" é o bacon dela) também vem dito;
- **o peso da embalagem que a planilha não diz** (`mise.embalagens`): a
  cobertura de chocolate de R$ 79,90 vale cerca de 1 kg, a embalagem de preço
  mais perto na página do supermercado, dito como estimativa e com a fonte; o
  peso que ela informar (`PATCH {conteudo_da_embalagem}`) vale mais;
- **rendimento**: o da receita, ou a estimativa pelo peso dos ingredientes ÷ o
  peso de uma porção (`porcao_padrao_g`, 350 g, premissa da plataforma que ela
  muda em `PUT /api/parametros/porcao_padrao_g`), nunca perguntado. Ela muda o
  de uma receita em `POST /api/receitas/{slug}/resposta` (`rendimento_porcoes`);
- **tempo**: com 4 horas ou mais por cozinhada, o tempo que a receita não diz
  não é perguntado, e o aviso (`avisos[]`, tipo `tempo`) diz isso. Com o
  limite apertado, sem o tempo da receita não dá para confirmar que cabe: a
  receita fica de fora, com o motivo, e ela diz o tempo na receita se quiser
  (o `editar` do item de rotina).

`make conferir-referencias` busca cada página e cada linha de novo; os testes
conferem com a prova gravada (`scripts/tests/fixtures/referencias_paginas.json`).

### O detalhe (`receita.json`)

- `fonte{site, url, autor}` (tudo `null` na receita que ela ditou, com
  `origem: dita`), `imagem`, `tempos{preparo_min, cozimento_min, total_min,
  ativo_min}` (`ativo_min` é o tempo de fogo e de trabalho por cozinhada, sem as
  esperas).
- `veredito` e `veredito_rotulo`: a conferência inteira, com o gosto dela; é
  ela que libera pôr preço (`pode_precificar`).
- `veredito_da_cozinha{codigo, rotulo, motivo}`: só a cozinha e a despensa, sem
  o gosto; é o que decide a aba da grade. `codigo` é `com_o_que_tem`,
  `comprando`, `falta_resposta` ou `nao_da`.
- `ingredientes[{nome, item_id, precisa{texto}, tem{texto}, sobra{texto},
  situacao, compra{texto, cabe}}]`: quanto a receita precisa ("2 xícaras (cerca
  de 408 g)"), quanto ela tem (o estoque e o que ela comprou com os R$ 80) e
  quanto sobra. `situacao` é `tem`, `tem_parte`, `falta`, `a_gosto`, `opcional`
  ou `nao_entendi`; o valor `confirmar`, da versão anterior, não sai mais,
  porque o item parecido agora é decidido e dito, e na dúvida a linha vira
  compra. `item_id`, `tem`, `sobra` e `compra` podem vir `null`. A água da
  torneira é `tem`, com `tem.texto` "da torneira", e não se compra nem entra no
  custo. `compra.cabe` diz se essa compra sozinha cabe no que resta; `null` sem
  preço.
  `medida_de_referencia{texto, gramas, fonte, url, pergunta}` (ou `null`) é a
  medida da tabela do IBGE que fez a conta da linha ("Um peito de frango pesa
  cerca de 180 g, pela referência de medidas do IBGE; a senhora pode
  corrigir"), com `pergunta` na forma de `perguntas[]` (assunto `medida`,
  `entrada` de peso). Ela é o `editar` dessa estimativa, e não uma pergunta a
  ela; a correção vai para `POST /api/receitas/{slug}/resposta` e vale mais.
- `rendimento{porcoes, estimado, texto, derivacao, pergunta}`: quantas porções
  a receita rende. Com `estimado`, o `texto` diz que é estimativa ("cerca de 3
  porções (estimativa: porções de 350 g; a senhora pode mudar)"), a
  `derivacao` diz a conta e `pergunta` é o campo `rendimento_porcoes` para ela
  mudar; sem estimativa, `pergunta` é `null`. `rendimento_texto` é o mesmo texto.
- `linhas_nao_entendidas[{texto, pergunta}]` fica vazia nesta versão. A
  quantidade que a receita não diz sai da embalagem de venda, dita como
  estimativa, e a linha sem fonte deixa a receita de fora com o motivo, sem
  pergunta e nunca como "a gosto" em silêncio. A linha que traz só o nome de
  um tempero, sem número ("Sal", "Sal e pimenta-do-reino", "Azeite",
  "Cheiro-verde", "Orégano"), é a convenção da receita brasileira para o que
  vai a gosto: entra como `a_gosto`, e não segura a receita. `opcionais[{nome, texto}]`: o
  que a receita diz que é opcional; o opcional que ela não tem fica fora da
  conta e da compra, e aparece aqui. `avisos[{tipo, texto}]`: o que não impede
  mas ela precisa saber (uma boca só para duas panelas, por exemplo).
- `falta_comprar{itens, custo, cabe_no_orcamento, texto}`: cada item com a
  forma de `custo.json#ingrediente_que_falta_exemplo`, com `referencia`
  (`null`, ou o preço de referência com `texto`, `preco_texto`, `produto`,
  `site`, `url` e `data_texto`, como em
  `custo.json#ingrediente_com_preco_de_referencia_exemplo`; a `origem_preco` é
  "preço de referência" e a `derivacao` termina com o texto da referência); sem nada a comprar,
  `custo` é R$ 0,00 e `cabe_no_orcamento` é `true`; com um preço desconhecido,
  os dois são `null`.
- `passos[]` na ordem e com o texto da página, com `secao` (a parte da receita
  em que o passo está, com o nome que a página mostra, "Massa" ou "Cobertura";
  `null` quando a página não dá nome à parte, e a tela põe o nome antes do
  primeiro passo de cada parte), `requisitos[]` (inclui `trecho`, `substituto`
  e `conferido`) e `limites[]` (inclui `graus`, `trecho` e `equipamento`);
  `requisitos_da_receita[]`
  (o que nenhum passo diz, com a `origem`); `perguntas[]` com `tipo` (a quem a
  resposta pertence: `equipamento`, `tecnica`, `operacional`, `gosto` ou
  `ingrediente`), `assunto` (o que falta, para a tela não ler o texto:
  `linha_nao_lida`, `preco_de_compra`, `preco_da_despensa`,
  `peso_da_embalagem`, `medida`, `mesmo_ingrediente`, `ingrediente`,
  `rendimento`, `tempo_cozimento`, `modo_preparo`, `equipamento`, `tecnica`,
  `rotina` ou `gosto`), `compras` (no `preco_de_compra`, cada ingrediente e quanto falta
  dele, com o mesmo texto de `falta_comprar`:
  `[{"ingrediente": "coco ralado", "quantidade_texto": "240 ml"}]`; nas
  outras, `[]`), `opcoes`, `entrada` e `passos`. Só `equipamento`, `tecnica`, `rotina`,
  `gosto` e o `modo_preparo` da receita que ela ditou são perguntas a ela. Os
  outros assuntos são a forma do `editar` de um valor que a plataforma
  estabeleceu com fonte (o tempo no fogo, o rendimento, a quantidade que a
  receita não diz, o peso de uma medida, o item parecido que ficou como
  compra), para ela corrigir quando quiser; a correção vai para
  `POST /api/receitas/{slug}/resposta`, e não para `/api/resposta`, com
  `campo` igual ao texto da linha quando é de uma linha. No item parecido
  (`mesmo_ingrediente`, com `opcoes` "É, sim" e "Não é"), `resposta` é `sim` ou
  `nao` e fica lembrada naquela receita; "sim" usa o item dela, e "não" põe a
  linha na compra. Na medida, o texto fala como ela ("Quanto pesa uma colher de
  sopa na sua cozinha? Em gramas, eu refaço a conta."), e `entrada` é
  `{"tipo": "peso", "unidade": "g", "peso_de": {"cada": "1 colher de sopa",
  "tudo": "2 colheres de sopa"}}`, com `peso_de` `null` quando a linha pede uma
  unidade só; o peso dito fica na linha, como dito por ela, e a conta do custo
  passa a usá-lo. A medida que nenhuma fonte diz deixa a receita de fora, com
  o motivo.
- `respostas[{campo, texto, quando_texto}]`: o que ela respondeu sobre a
  receita e a página não dizia, anotado como dito por ela ("A senhora disse que
  rende 4 porções.", "A senhora disse que um peito de frango pesa 300 g.").
- `avaliacao{gosta, estrelas{sabor, facilidade, tempo, entrega, apelo},
  notas, pontuacao{valor, texto, derivacao}}`: estrelas de 1 a 5, ou `null`
  quando ela não deu. Pesos: sabor 0,30, apelo de venda 0,25, aguenta a entrega
  0,20, facilidade 0,15, tempo 0,10. nota = Σw·(n−1)/4 ÷ Σw das avaliadas;
  g = 1 (gosta), 0,5 (não disse) ou 0 (não gosta); pontuação =
  100 × (0,75 × nota + 0,25 × g), com uma casa. Sem estrela nenhuma,
  `pontuacao` é `null`. Na tela: "Sabor", "Facilidade de preparo", "Tempo de
  preparo", "Aguenta a entrega", "Apelo de venda".
- `posicao_no_ranking` (`null` fora do ranking), `rascunho_chat` e `rota`.
- `checklist{titulo, pode_aceitar, resumo, falta_para_aceitar, confirmar_a_cozinha,
  grupos}`: o checklist de produção, feito pelo motor (a tela não decide nada
  dele). `grupos[{id, titulo, status, itens, vazio_texto}]` na ordem
  `equipamentos`, `tecnicas`, `rotina` (tempo por cozinhada, gás, geladeira,
  energia e bocas), `ingredientes` (o que tem, cada compra e se cabe nos
  R$ 80,00) e `pre_determinados` (porções, pesos e preços de referência), com
  `vazio_texto` para o grupo sem item. Cada item: `id`, `tipo`, `nome`,
  `detalhe`, `status` (`confirmado`, `pre_determinado`, `suposto`,
  `falta_saber` ou `nao_da`), `status_texto` (o estado dito para ela:
  "confirmado pela senhora", "suposto: confirme", "falta saber", "não dá",
  "pré-determinado", ou o do item, como "tem", "não precisa", "cabe"), `origem`
  (`a_senhora_disse`, `suposto`, `referencia` ou `receita`) e `origem_texto`
  ("a senhora disse", "suposto", "referência de medidas do IBGE", "receita"),
  `pergunta` (o que ela responde ali mesmo, na forma de `perguntas[]`) e
  `editar` (a mesma forma, para mudar um valor pré-determinado). O `status`
  do grupo é o do pior item. `pode_aceitar` é a conferência liberada, com o
  gosto, e nada suposto que a receita use; `falta_para_aceitar` diz cada coisa
  que falta, em frases para ela; `confirmar_a_cozinha{pergunta, itens[{tipo,
  id, nome}]}` é a pergunta, uma só ("Antes de aceitar, a senhora confirma que
  tem fogão e que sabe refogar?"), ou `null`.

### A receita trazida e a resposta sobre a receita

`POST /api/receitas {url}`: o servidor busca a página (só endereço público),
lê a receita estruturada (JSON-LD ou microdata) e guarda no catálogo com
`origem: url_dela`; responde 201 com o detalhe. Endereço que já está no
catálogo (a mesma URL canônica) não é buscado de novo: responde 200 com o
detalhe dele.

`POST /api/receitas/{slug}/resposta {campo, resposta}`: a correção dela a um
valor da própria receita, ou a resposta ao modo de preparo da receita que ela
ditou. `campo` é `rendimento_porcoes` (um número),
`tempo_cozimento_min` ("40", "40 minutos", "1 hora e 10 minutos"),
`modo_preparo` (um passo por linha) ou o texto de uma linha que a leitura não
entendeu ("2 colheres de sopa", "a gosto"). Na pergunta de medida com
`entrada` de peso, `campo` é o texto da linha, `resposta` é o peso ("300 g",
"0,3 kg") e `por_unidade` diz de quanto é: `true`, de uma unidade (o que a
pergunta pede: um peito, uma colher); `false`, da linha inteira (as duas
colheres juntas). Sem `por_unidade`, vale o que o texto diz ("cada", "as
duas"), senão uma unidade. Só entra o que a receita não dizia: resposta que
muda o que a página diz, e peso para a linha que se converte sozinha, são
recusados (categoria `uso`). Devolve o detalhe, conferido de novo, com a
resposta em `respostas`.

### Avaliação e notas

`PUT /api/receitas/{slug}/avaliacao` recebe só o que mudou (`gosta`, e em
`estrelas` o valor novo de cada categoria; `null` apaga) e devolve
`{slug, nome, avaliacao, posicao_no_ranking, atualizado_texto, texto}`; o
`GET` da mesma rota devolve o mesmo, e é a rota do card
`avaliacao_da_receita`. `gosta: null` volta a "ainda não disse". O gosto é o
mesmo que a conferência usa (e o mesmo de `/api/gosto` e de `registrar_gosto`):
avaliar grava lá. O impedimento que ela tinha apontado continua quando ela diz
que não gosta ou volta a "ainda não disse"; quando ela diz que gosta de novo
("Mudei de ideia"), ele deixa de valer, e o `texto` diz isso ("O impedimento
que a senhora tinha apontado (...) não segura mais a receita.").
`PUT /api/receitas/{slug}/notas` recebe `{texto}` e devolve `{slug, notas,
atualizado_texto, texto}`; texto vazio apaga.

### Custo e preço preliminar

`GET /api/receitas/{slug}/custo` tem a forma de `custo.json`. A receita que a
conferência inteira (com o gosto) não liberou é recusada com HTTP 409,
categoria `regra`, e o porquê na língua dela ("Ainda não calculo o custo de
bolo de fubá: antes preciso saber uma coisa. ...").

`GET /api/receitas/{slug}/estimativa` (`estimativa.json`) é sempre rotulada
"preliminar" e nunca grava nada: nem decisão, nem preço. As linhas (`id`):

- `ingredientes`: o custo de ingrediente da porção, a mesma conta de
  `custo.json`, sem exigir a receita conferida;
- `mao_de_obra` (rótulo "Mão de obra sugerida", o mesmo na tela e no card da
  conversa): minutos ÷ 60 × `valor_hora` ÷ porções. Os minutos são os do
  fogo e do trabalho nos passos; sem tempo nos passos, o que a receita declara,
  dito como premissa na derivação e em `sinais.falta_confirmar`;
- `gas`: minutos no fogão e no forno a gás × o custo do minuto de fogo
  (`botijao_preco` ÷ (`botijao_horas` × 60), em centavos) ÷ porções;
- `energia`: a potência de cada aparelho elétrico (`potencia_air_fryer`,
  `potencia_forno_eletrico`, `potencia_microondas`, `potencia_liquidificador`,
  `potencia_batedeira`, `potencia_mixer`, `potencia_processador`) × os minutos ×
  `kwh_preco` ÷ porções. Sem forno, o tempo de forno vai para o aparelho que ela
  tem e faz o papel dele, e a derivação diz isso;
- `embalagem`: `embalagem_por_porcao`.

`gas` e `energia` só aparecem quando a receita usa fogo ou aparelho. Cada linha
de custo é arredondada para cima no centavo. `custo_producao` é a soma das
linhas com valor; `piso` é o custo de produção ÷ 0,90 e `minimo_so_ingrediente`
é o ingrediente ÷ 0,90, os dois arredondados para cima; os três `pontos` são o
maior entre o piso e o ingrediente ÷ 0,40, ÷ 0,35 e ÷ 0,30 (meio para cima), com
o que chega para ela (0,90 × preço, meio para cima), a taxa de 10% (o resto do
preço, para as duas somarem o preço), o lucro sobre o ingrediente e a sobra
depois de todo o custo.

`premissas[]` traz só as que as linhas usaram. `origem` é `dela` (o valor que ela
informou), `padrao` (um número público, com `fonte`, `fonte_url` e
`atualizado_texto` "conferido em 26/09/2026") ou `falta`. Os padrões e as páginas:
o valor horário do salário mínimo de 2026 (Decreto nº 12.797/2025, planalto.gov.br),
o preço médio do botijão de 13 kg no Brasil (pesquisa semanal da ANP), a duração
do botijão (Sindigás), a tarifa residencial média de 2026 sem impostos (boletim
InfoTarifas da ANEEL) e as potências típicas dos aparelhos. Cada trecho citado é
conferido por `make conferir-conhecimento`. Linha que precisa de premissa que
falta vem com `valor: null`, fica de fora da conta, e a premissa entra em
`sinais.faltam_parametros`. `sinais.falta_confirmar` lista, em frases, o que
ainda falta confirmar da receita (uma pergunta da cozinha, o tempo que a
receita não diz): isso não impede a estimativa. Quando falta o custo de um
ingrediente ou o rendimento, a linha dos ingredientes vem `null`,
`custo_producao`, `piso` e `minimo_so_ingrediente` vêm `null`, `pontos` vem
vazio e `texto` diz o que falta saber. `referencias_de_mercado` vem sempre `[]`
nesta versão, e `referencias_texto` diz que não há preço de mercado conferido.
Receita que ela não consegue fazer recusa a estimativa, com o motivo (categoria
`regra`); receita que não existe é 404 (`ausente`).

`GET /api/parametros/{nome}` devolve a premissa na forma de
`estimativa.json#premissas[]`. `PUT /api/parametros/{nome}` recebe `{valor}`: um
número grava o valor dela (fora da faixa do parâmetro é recusado, categoria
`uso`); `null` apaga o dela, e a premissa volta ao padrão com fonte, ou a
`falta` quando não há padrão. Nome desconhecido é 404. O detalhe da receita
muda `valor_hora` e `embalagem_por_porcao` por esta rota e pede a estimativa de
novo: os números que aparecem depois são os da API, e a premissa gravada volta
com `origem: "dela"`, que a tela diz como "a senhora disse".

### As rotas de hoje seguem as mesmas regras

`POST /api/avaliar` e `POST /api/cmv` recebem a receita digitada: ela vale como
a receita que ela ditou, e um endereço só vale se o servidor já leu a página
(senão é recusado). `/api/avaliar` traz também `pode_aceitar`,
`falta_para_aceitar` e `confirmar_a_cozinha`, os do `checklist`: o Pôr preço
pede a confirmação antes do "Vou cobrar". `/api/cmv` só calcula a receita igual à que passou pela
conferência. `POST /api/receita-da-web` guarda no catálogo e põe em avaliação,
que é o que a tela antiga mostra; a fonte é a que a página diz de si.

## Início, cardápio e histórico

### A tela inicial (`visao-geral.json`)

`{kpis, proximo_passo, pendencias, perguntas_da_cozinha, dinheiro_parado,
receitas_recomendadas, cardapio_previa}`. Cada indicador traz o `texto`
pronto (com o plural certo) e a `rota` que o cartão abre (o orçamento abre
`/despensa#orcamento`). `proximo_passo.acao` é `{tipo: "link", rota}` ou
`{tipo: "perguntar", rascunho}`: com `pendencias` sempre vazia nesta versão, o
próximo passo começa pela pergunta da cozinha, depois as receitas e o
cardápio. `pendencias`, vazia, tem a forma de `despensa.json#pendencias[]`;
`perguntas_da_cozinha`
junta, uma por pergunta, as perguntas de equipamento, técnica e rotina que
seguram receitas: `{id, pergunta (a forma de receita.json#perguntas[], com o
motivo dizendo quantas receitas ela segura), receita, receitas, rascunho_chat,
rota}`. `dinheiro_parado.itens` traz todos os itens com preço, do que mais
custou ao que menos custou (a tela mostra cinco e abre o resto), com
`sem_receita` quando nenhuma receita que ela consegue fazer usa o item.
`receitas_recomendadas` são os itens da aba `pode_fazer` (até 8).

### O cardápio (`cardapio.json`)

Cada prato traz o preço que ela escolheu ao aceitar e a conta de agora: o que
chega para ela depois da taxa (`recebe`), o custo da porção com a despensa de
hoje, o lucro, a `derivacao` escrita e um `aviso` quando o custo mudou desde o
aceite, quando o preço dá prejuízo, ou quando a conta não fecha hoje (valem os
números do aceite). `resumo` soma no servidor (`preco_medio`,
`margem_media_texto`) e traz a linha dos R$ 80,00 (`orcamento_texto`,
`orcamento_rota`). `historico` é o registro inteiro, do mais novo para o mais
antigo, em frases dela: `tipo` é `aceito`, `preco` (aceitou de novo com outro
preço), `retirado` (recusou o que estava no cardápio), `recusado`, `adiado` ou
`desfeito`; só a decisão que vale hoje de cada prato tem `pode_desfazer`.

`POST /api/cardapio/{prato}/desfazer` grava uma decisão nova que volta ao estado
de antes da última (sem decisão antes, o prato fica para decidir depois) e
devolve o cardápio com a frase (`texto`). `PUT /api/cardapio/{prato}/notas
{texto}` grava as notas da receita do prato. `{prato}` é o nome (sem ligar para
caixa e acento) ou o id da receita. `POST /api/decisao` devolve em `texto` a
frase da decisão e aceita a chave do clique em `id_cliente`.

### O histórico (`atividades.json`)

`{grupos[{dia, rotulo, itens}], total, texto, proximo_cursor, categorias, quem,
dias}`, do mais novo para o mais antigo: as decisões, as mudanças da despensa e
as compras para um prato, as respostas da cozinha, o gosto, as estrelas e as
respostas sobre as receitas, os preços do que falta, as receitas que entraram
na grade e as consultas do agente (só as de leitura, sem repetir a mesma em
seguida). `quem` é `senhora`, `consultora` (o agente) ou `tela` (a própria plataforma);
cada item tem `categoria_rotulo`, `hora_texto`, `dia`, `canal_texto` e o `link`
para a coisa de que fala. Nenhum texto traz nome de ferramenta, identidade,
milissegundos ou caminho de arquivo. `cursor` é o id do último item da página;
`dias` são os dias com atividade para os outros filtros. Categoria ou quem que
não existe é `uso`.

### Os limites do controle de preço

`GET /api/precos` traz `controle{min, max, passo}`: do mínimo sem prejuízo
(arredondado para cima, pelo menos R$ 0,50) a seis vezes o custo (inteiro, pelo
menos R$ 1,00 acima do mínimo), de 50 em 50 centavos. A tela só passa esses
números para o controle e pergunta `/api/preco-em` a cada parada.

## Conhecimento (`conhecimento.json`)

A saída da ferramenta `consultar_conhecimento(pergunta, tipos?, k?)` na busca
pelo corpus inteiro: `{trechos[{id, tipo, rota, fonte, texto, pontuacao}],
nada_relevante, texto}`. `tipo` é a parte da plataforma de onde o trecho veio
(`despensa`, `cozinha`, `receita`, `avaliacao`, `cardapio`, `orcamento`,
`conhecimento`), e é também o filtro `tipos` (tipo desconhecido é erro de uso);
`k` vai de 1 a 12, e o padrão é 6. `rota` é a tela que mostra o trecho, ou
`null` para a base de conhecimento culinário. `texto` começa pelo cabeçalho do
trecho ("Receita Bolo de fubá, TudoGostoso, passo 2 de 2:"); o passo de uma
receita volta com o cabeçalho da receita antes. `pontuacao` vai de 0 a 1. O
trecho da base de cozinha traz o fato, o site e a data da conferência e o
trecho literal da página, entre aspas. Os ids: `despensa:<id do item>`,
`despensa:resumo`, `cozinha:equipamento:<id>`, `cozinha:tecnica:<id>`,
`cozinha:restricao:<campo>`, `receita:<slug>`, `receita:<slug>:ingredientes`,
`receita:<slug>:passo-<n>`, `avaliacao:<slug>`, `cardapio:<prato>`,
`cardapio:resumo`, `orcamento`, `orcamento:compra-<id>`,
`orcamento:preco-<ingrediente>` e `conhecimento:<id do fato>`.

Sem nada acima do limiar, `trechos` vem vazio, `nada_relevante` é `true` e
`texto` diz que não sabe e oferece procurar na internet. As rotas viram o card
`fontes`: como o fim da chamada não traz a resposta da ferramenta, o backend
refaz a mesma busca (determinística para o mesmo estado da plataforma) e monta
um chip por registro (`{rotulo, rota}`); fato da base de cozinha vira chip com
o nome da fonte e `rota: null`. Sem trecho, não há card.

## Exportação (`exportacao.json`)

`GET /api/exportacao` devolve um arquivo JSON, fora do envelope, com
`Content-Disposition: attachment; filename="sabor-da-maria-dados.json"`: a
despensa (a forma de `despensa.json`) e as mudanças dela, a cozinha (a forma
de `perfil.json`, com `toda_cozinha`) e as mudanças dela, o orçamento e todas as compras, as
decisões, o cardápio, os gostos, os preços que ela informou e as receitas em
avaliação. Tudo sai do que já está gravado; nada é recalculado para o arquivo.

## Conversa: protocolo do turno

`POST /api/conversas/{id}/turnos {texto, contexto?, acao?, id_cliente}` responde
`202 {turno_id}`; se já houver turno rodando naquela conversa, `409 {turno_id}`
(o cliente se anexa a ele). O turno é do backend: fechar a aba não o cancela.

`GET .../turnos/{t}/eventos` é SSE. Cada evento tem `id: <seq>` e `data:` JSON
com `{seq, turno_id, tipo, ...}`. O cliente retoma com `Last-Event-ID` ou
`?desde=<seq>`. Keepalive (`: keepalive`) a cada 10 s no máximo. Cabeçalhos:
`Cache-Control: no-cache, no-transform`, `X-Accel-Buffering: no`.

| `tipo` | Campos | Observação |
|---|---|---|
| `turno.iniciado` | `conversa_id`, `mensagem_id`, `id_cliente` | |
| `acao.resultado` | `ok, texto, cartao?` | resultado de uma `acao` de card, executada pelo backend antes do agente |
| `atividade.iniciada` | `atividade_id, ferramenta, rotulo, rotulo_feito` | rótulos em pt-BR, sem jargão; o rascunho recomeça, porque o texto de antes da ferramenta era bastidor |
| `atividade.concluida` | `atividade_id, ok` | |
| `cartao` | `cartao_id, tipo_cartao, dados, ref, gerado_texto` | dados do motor, nunca do texto do modelo |
| `texto.parcial` | `delta` | já mascarado: todo valor em R$ vira o caractere sentinela `` |
| `texto.comentario` | `texto` | mascarado; o backend não emite mais (o texto do meio do turno é bastidor), e a tela ainda o entende |
| `texto.final` | `texto, retirados` | depois do guard-rail; substitui o rascunho; é só o texto depois da última ferramenta (sem ele, o último comentário) |
| `estado.alterado` | `recursos[]` | ex.: `["despensa","orcamento","receitas"]` → a tela faz refresh |
| `sugestoes` | `opcoes[{rotulo, texto, acao?}]` | chips de resposta rápida |
| `turno.concluido` / `turno.cancelado` | | |
| `turno.falhou` | `categoria (rede|tempo|consultora), mensagem` | mensagem em pt-BR |

A máscara do rascunho tem exemplos em `mascara.json`: o backend e o navegador
conferem os mesmos casos nos testes deles.

`acao` (enviada por um botão de card): `{"tipo": "responder", "tipo_pergunta",
"campo", "resposta", "receita_id"?}` (com `receita_id`, a resposta é de uma
pergunta da própria receita, como a do item parecido, e fica gravada nela), `{"tipo": "decidir", "prato", "decisao", "preco"}`,
`{"tipo": "avaliar", "receita_id", "gosta"?, "estrelas"?, "notas"?}`. O backend
executa pelo portão, emite `acao.resultado` e só então conta ao agente o que já
ficou registrado.

Cards (`tipo_cartao`): `despensa_resumo`, `ingrediente`, `receita`,
`viabilidade`, `comparacao`, `pergunta`, `cozinha_atualizada`, `orcamento`,
`custo_porcao`, `cenarios`, `ponto_de_preco`, `preco_preliminar`, `decisao`,
`avaliacao_da_receita`, `fontes`. `dados` de cada um tem a mesma forma da rota
indicada em `ref.rota`; um exemplo de cada tipo está em `cartoes/<tipo>.json`.

### Como o card aponta para os dados

A chave `tipo_cartao` é a mesma no evento SSE e no card guardado em
`conversa.json`.

`gateway.cartoes.cartao_para(ferramenta, args)` devolve um modelo de rota
(`/api/receitas/{slug}`, `/api/despensa/itens/{id}`) e os argumentos crus. O
backend do chat resolve o id ou o slug e emite `ref.rota` já concreta
(`/api/receitas/arroz-com-frango`). A receita se acha pelo `receita_id` ou
pelo nome, na precedência da ferramenta. Quando os dados do card são a
própria resposta da ferramenta (`pergunta`, de `proxima_pergunta`, e
`fontes`, de `consultar_conhecimento`), `ref.rota` é `null` e `dados` basta.

| Card | Ferramenta | `ref.rota` | `dados` |
|---|---|---|---|
| `despensa_resumo` | `diagnostico_despensa` | `/api/visao-geral` | `visao-geral.json` |
| `ingrediente` | `custo_unitario`, `atualizar_despensa` | `/api/despensa/itens/{id}` | `despensa-item.json` |
| `receita` | `buscar_receita_na_web` | `/api/receitas/{slug}` | `receita.json` |
| `viabilidade` | `avaliar_receita` | `/api/receitas/{slug}` | `receita.json` |
| `comparacao` | `comparar_candidatas` | `/api/receitas?aba=pode_fazer` | `receitas.json` |
| `pergunta` | `proxima_pergunta` | `null` | `cartoes/pergunta.json` |
| `cozinha_atualizada` | `registrar_resposta` | `/api/perfil` | `perfil.json` |
| `orcamento` | `consultar_orcamento`, `registrar_compra`, `registrar_preco_mercado` | `/api/orcamento` | `cartoes/orcamento.json` |
| `custo_porcao` | `calcular_cmv` | `/api/receitas/{slug}/custo` | `custo.json` |
| `cenarios` | `cenarios_preco` | `/api/precos` | `cartoes/cenarios.json` |
| `ponto_de_preco` | `testar_sensibilidade` | `/api/preco-em` | `cartoes/ponto_de_preco.json` |
| `preco_preliminar` | `estimar_preco_preliminar` | `/api/receitas/{slug}/estimativa` | `estimativa.json` |
| `decisao` | `registrar_decisao` | `/api/cardapio` | `cardapio.json` |
| `avaliacao_da_receita` | `registrar_avaliacao_da_receita` | `/api/receitas/{slug}/avaliacao` | `avaliacao-escrita.json#resposta` |
| `fontes` | `consultar_conhecimento` | `null` | `{texto, chips[{rotulo, rota}]}` |

## Ferramentas do agente

O registro final, igual nos quatro lugares que conhecem cada ferramenta (o
servidor, `politica.ESCOPOS`, `frases.FRASES_DO_MOTOR` e `cartoes.CARTOES`).
Leitura não muda nada que é dela; as de leitura marcadas com † gravam um
registro do próprio servidor (`politica.REGISTRAM_ARTEFATO`).

| Ferramenta | Escopo |
|---|---|
| `diagnostico_despensa`, `custo_unitario`, `converter_medida_culinaria`, `consultar_perfil`, `proxima_pergunta`, `comparar_candidatas`, `cenarios_preco`, `testar_sensibilidade`, `consultar_orcamento`, `consultar_cardapio`, `consultar_precos_de_mercado`, `consultar_gostos`, `consultar_conhecimento`, `estimar_preco_preliminar`, `pauta_de_descoberta` | leitura |
| `avaliar_receita` †, `calcular_cmv` †, `buscar_receita_na_web` †, `consultar_planilha` † | leitura |
| `registrar_resposta`, `registrar_preco_mercado`, `registrar_gosto`, `registrar_decisao`, `registrar_compra`, `atualizar_despensa`, `registrar_avaliacao_da_receita` | escrita |

`avaliar_receita`, `calcular_cmv`, `cenarios_preco` e `testar_sensibilidade`
aceitam `receita_id` no lugar da receita ou do nome do prato;
`buscar_receita_na_web` e `avaliar_receita` devolvem o `receita_id`.
`buscar_receita_na_web` guarda no catálogo e não põe em avaliação; o endereço
já lido volta com `ja_conhecida`, sem buscar de novo. A receita digitada em
`avaliar_receita` é a que ela dita (um endereço digitado não faz dela receita
da internet, e o que o servidor não leu é recusado); com o `receita_id` junto,
a receita digitada só traz o que ela respondeu (o rendimento, o modo de preparo
ou o tempo no fogo que faltavam, quanto vai de uma linha que a leitura não
entendeu, ou, na pergunta do item parecido, a linha com `item_da_despensa`: o
nome do item que ela confirmou, ou `""` quando ela diz que não é; só vale o
item que a conferência perguntou). `calcular_cmv` só aceita a receita digitada igual à que passou pela
conferência: diferente, recusa dizendo o que mudou, e o recado é usar o
`receita_id`. `registrar_avaliacao_da_receita(receita_id, gosta?, estrelas?,
notas?)` grava a avaliação e devolve a forma de `avaliacao-escrita.json#resposta`.
`estimar_preco_preliminar(receita_id | prato)` devolve a forma de
`estimativa.json`, com `receita_id` e uma orientação para o agente dizer que
é preliminar. `pauta_de_descoberta()` devolve `{disponivel,
pratos_para_procurar[{prato, busca, itens_da_despensa[], motivo_texto}],
itens_para_procurar[{item_id, ingrediente, termo, pago, receitas_que_usam,
motivo, motivo_texto}], buscas, urls_conhecidas, sites_que_ja_funcionaram,
sites_populares, limites{buscas, paginas, paginas_por_busca}, texto,
orientacao}`, tudo do motor: primeiro até 4 pratos clássicos cuja base inteira
está na despensa dela, com estoque ("receita de feijão tropeiro", de um mapa
curado da despensa para os pratos, e o prato que já tem receita no catálogo
sai), depois os itens em que mais dinheiro está parado sem receita (e, se não
bastam cinco buscas, os maiores gastos), "receita com <item>", até 8 buscas;
os endereços que já estão no catálogo e `sites_populares`, a lista curada dos
sites brasileiros de receita que publicam a receita em JSON-LD, para a busca
preferir essas páginas. Quem decide se a receita achada dá para fazer é a
conferência, na página de verdade. `comparar_candidatas()` devolve, além das
candidatas, o `catalogo{da_para_fazer[{receita_id, prato, como}],
usa_so_o_que_tem[{receita_id, prato, falta_responder[]}],
precisa_comprar[{receita_id, prato, falta_comprar[], falta_responder[]}],
linha_sem_leitura[{receita_id, prato, falta_responder[]}], texto}`, com as
contas da grade (`receitas.json#esperando_resposta`).
Nenhuma ferramenta recebe o HTML de uma página: receita da internet só entra
pela página que o servidor buscou.

### Campos que a fundação acrescentou

- `POST /api/decisao` e `POST /api/compra` aceitam o cabeçalho
  `Idempotency-Key` (ou `chave` no corpo). A mesma chave nunca registra duas
  vezes e devolve o que ela registrou; chave nova é registro novo.
- Aceitar um preço abaixo do mínimo não é mais recusado: a resposta traz
  `da_prejuizo: true` e `aviso` (quanto ela perde por porção e qual é o
  mínimo). Só a conta que não bate segura o preço.
- Erro `ausente` responde HTTP 404 com o mesmo envelope.

### Envelope em toda resposta, inclusive 202 e 409

`POST /api/conversas/{id}/turnos` responde HTTP 202 com
`{"ok": true, "dados": {"turno_id": "t-…"}}`. Se já houver um turno rodando
naquela conversa, HTTP 409 com `{"ok": false, "categoria": "ocupado",
"erro": "Ainda estou respondendo a mensagem anterior.", "dados": {"turno_id":
"t-…"}}`: o cliente se anexa a esse turno. Todo evento SSE traz `seq`,
`turno_id` e `tipo`.

### Exemplos acrescentados

- `custo.json`: `GET /api/receitas/{slug}/custo` (e o card `custo_porcao`),
  com um exemplo de ingrediente que falta comprar
  (`ingrediente_que_falta_exemplo`, a forma de cada item de
  `receita.json#falta_comprar.itens`).
- `descoberta-inicio.json`: resposta de `POST /api/receitas/descoberta`.
- `despensa-eventos.json`: `GET /api/despensa/eventos` (lista com cursor).
- `parametro-escrita.json`: `PUT /api/parametros/{nome}` (pedido e resposta, a
  resposta com a forma de `estimativa.json#premissas[]`).
- `despensa-item-comprado.json`: um item comprado com os complementos, com a
  forma de cada item de `compras[]`.
- Cada item de `visao-geral.json#cardapio_previa` tem a forma de
  `cardapio.json#pratos[]`.
- `atividades.json` ganhou `quem_rotulo`; o histórico de `cardapio.json`
  ganhou `tipo_rotulo`.
- `avaliacao-escrita.json`, `notas-escrita.json`, `conhecimento.json`,
  `exportacao.json` e a pasta `cartoes/`.

## Interfaces do motor que as rotas usam

Não são rotas, mas as rotas e os cards da conversa dependem delas:

- `mise.catalogo`: `url_canonica`, `id_da_url`, `id_da_receita` (a regra do
  `receita_id`), `chave_da_imagem` e `rota_da_imagem` (a regra da foto), a
  forma `ReceitaDoCatalogo` e a leitura `Catalogo(dossie).listar(q=, origem=,
  limite=)`, `obter(slug)` e `por_url(url)`.
- `mise.tempo.MinutosAtivos` (`ativos`, `passivos`, `origem`, `derivacao`): o
  resultado de `mise.passos.minutos_ativos(receita)`, que a conferência usa;
  `MinutosAtivos.pelo_tempo_declarado(minutos)` e
  `MinutosAtivos.desconhecido()` são os casos sem tempo nos passos.
