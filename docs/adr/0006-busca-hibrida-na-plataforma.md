# ADR 0006: busca híbrida sobre a plataforma inteira, com "não sei" calibrado

## Contexto

O agente responde sobre tudo o que a Dona Maria vê no site, a despensa, a
cozinha, as receitas e os passos, as avaliações, o cardápio, o orçamento, e
também dúvidas de cozinha ("quanto tempo a comida pronta aguenta na
geladeira?"). Resposta sem fonte é chute, e chute sobre segurança de alimento
ou sobre o dinheiro dela é pior do que "não sei".

O vocabulário dela não é o da fonte. Ela pergunta "por quanto tempo a comida pode
ficar quentinha esperando o cliente?", e o fato conferido fala em manter acima
de 60 graus. O corpus é pequeno e muda a cada conversa.

## Decisão

Um índice próprio, em `retrieval/src/retrieval/corpus/`, montado a partir do
dossiê por `mise/src/mise/corpus.py` e consultado pela ferramenta
`consultar_conhecimento`.

- **Trechos pela estrutura, não por tamanho.** Um trecho por registro (item da
  despensa, equipamento, técnica, restrição, avaliação, prato do cardápio,
  compra, fato da base de cozinha). A receita vira pai e filhos, um trecho de
  ingredientes e um por passo, e o achado de um passo volta com o texto do pai.
  Cada registro já é curto, então não há corte por número de tokens.
- **Cabeçalho contextual escrito por código.** Todo trecho começa dizendo de
  onde é, como "Receita Bolo de fubá, TudoGostoso, passo 2 de 2:",
  "Alcaparras, na despensa da senhora:". É a ideia de contextual retrieval, sem
  modelo, e portanto sem custo e sem risco de o cabeçalho inventar.
- **Duas buscas fundidas.** BM25 (k1 1,5, b 0,75) com um analisador de
  português (caixa, acento, 259 palavras vazias, radical leve, unidades por
  extenso, sinônimos só na pergunta) e vetores densos multilíngues
  (`paraphrase-multilingual-MiniLM-L12-v2` pelo FastEmbed, opcional). Sem o
  modelo instalado, o lado denso usa trigramas de caractere com hash, e o CI
  roda assim. As listas se fundem por RRF (k = 60), e o MMR (λ = 0,7) tira
  repetição, contando os passos de uma receita como a receita.
- **Abstenção calibrada.** Abaixo de uma evidência mínima (a cobertura da
  pergunta ponderada pela raridade de cada palavra), a resposta é a frase fixa
  "Não achei nada sobre isso na plataforma nem na base de cozinha. Não sei, e
  prefiro não chutar. Se a senhora quiser, posso procurar na internet." Os
  limiares saem de uma busca em grade no conjunto dourado, com custo 3 para
  resposta que devia ter sido "não sei" e 1 para "não sei" que devia ter
  respondido (`evals/src/evals/recuperacao.py`).
- **Cada trecho volta com a rota da tela e a fonte.** Na conversa, as rotas
  viram o card "De onde eu tirei isso", que abre a tela certa.
- **Base de cozinha só com prova.** Os 60 fatos em
  `retrieval/src/retrieval/conhecimento/*.yaml` têm URL, data de conferência e o
  trecho literal da página; `make conferir-conhecimento` busca cada página e
  prova que o trecho continua lá.
- **Sempre fresco.** O índice se reconstrói quando o carimbo do dossiê muda, e
  os vetores ficam em cache pelo hash do texto.

## Consequências

- No conjunto dourado de 57 perguntas (11 fora do corpus), a coluna de
  trigramas dá revocação em 5 de 0,902, MRR em 10 de 0,845 e acerto de
  abstenção de 0,965; a coluna neural, 0,924, 0,802 e 0,965
  (`evals/resultados/recuperacao.json`, detalhes em `docs/rag.md`).
- O vetor neural melhora a revocação e piora a ordem do primeiro acerto neste
  conjunto; por isso ele é opcional, e o piso do CI vale para a coluna que roda
  sem download.
- Há um erro conhecido e anotado no conjunto. "Como está o tempo lá fora hoje?"
  passa pela abstenção, porque "tempo" aparece em toda receita e a busca por
  palavra não separa o clima do tempo de preparo. Quem lê que aqueles trechos
  não falam de clima é o agente (`evals/casos/recuperacao.yaml`).

## Alternativas consideradas

- **Só BM25.** Perde paráfrase, e a pergunta da comida quentinha não tem nenhuma
  palavra do trecho dos 60 graus, e só o modelo multilíngue a acha.
- **Só vetores.** Perde nome próprio e número exato, e responde qualquer coisa
  com alguma similaridade.
- **Banco vetorial externo.** Um serviço a mais para um corpus de centenas de
  trechos (197 no estado de referência da avaliação), sem ganho de qualidade e
  com um ponto de falha novo.
- **Cabeçalho gerado por LLM.** Custo por trecho, e um texto que pode afirmar o
  que o registro não diz.
- **Cortar por tamanho com sobreposição.** Faz sentido para documento longo; aqui
  quebraria registros curtos no meio e perderia a estrutura.
