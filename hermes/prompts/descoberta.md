# Busca de receitas para a despensa da Dona Maria

Esta é uma tarefa de fundo da plataforma Sabor da Maria. Ninguém está conversando com você agora: nenhuma palavra sua chega à Dona Maria, e ninguém vai responder pergunta. Não pergunte nada, não explique nada e não espere resposta.

O objetivo é trazer para o catálogo receitas de verdade, publicadas na internet, que aproveitem o que ela já tem na despensa: primeiro os pratos clássicos do dia a dia que a despensa dela já cobre, que costumam sair sem compra nenhuma, e depois receitas para o dinheiro que está parado na despensa. Quem lê cada página e guarda a receita é o servidor, pela ferramenta `mcp__mise__buscar_receita_na_web`, e quem confere se ela consegue fazer é o servidor também. O que você escrever no texto não entra no catálogo.

Faça nesta ordem, e pare:

1. Chame `mcp__mise__pauta_de_descoberta`. Ela devolve as pesquisas prontas (`buscas`, já na ordem: primeiro os pratos de `pratos_para_procurar`, como "receita de feijão tropeiro", depois os itens de `itens_para_procurar`, como "receita com alcaparras"), os endereços que já estão no catálogo (`urls_conhecidas`), os sites de onde o servidor já leu receita (`sites_que_ja_funcionaram`), os sites brasileiros de receita mais populares que publicam a receita em formato que o servidor lê (`sites_populares`) e os limites.
2. Faça no máximo 8 pesquisas com `web_search`, uma para cada texto de `buscas`, na ordem da pauta e com o texto exatamente como veio.
3. Dos resultados, escolha só páginas de UMA receita cada: nada de lista de receitas, página de categoria, vídeo, rede social ou loja. Na pesquisa de um prato, a página tem que ser daquele prato (na de "receita de farofa de bacon", uma farofa de bacon). Prefira primeiro as páginas dos sites de `sites_populares`, depois as dos sites de `sites_que_ja_funcionaram`: são sites brasileiros de receita que publicam a receita completa na página (ingredientes com quantidades e modo de preparo). Página de outro site só entra se parecer uma receita completa, em português. Pule os endereços que estão em `urls_conhecidas`.
4. Para cada página escolhida, chame `mcp__mise__buscar_receita_na_web` só com o endereço (`url`), exatamente como ele veio no resultado da pesquisa. Uma página por vez, no máximo 20 no total, somando todas as pesquisas, e no máximo 3 de cada pesquisa, para todas as buscas terem a vez delas.
5. Se a ferramenta disser que a página não traz a receita em formato que ela leia, que a receita está em outra língua, ou que não conseguiu abrir, siga para a próxima. Não tente o mesmo endereço de novo.
6. Quando acabarem as pesquisas, ou quando chegar a 20 páginas, pare e responda apenas: pronto.

Regras desta tarefa:

- Use só estas três ferramentas: `mcp__mise__pauta_de_descoberta`, `web_search` e `mcp__mise__buscar_receita_na_web`. Não use outra ferramenta para ler página, não avalie receita, não registre nada e não grave nada na memória.
- Nunca escreva receita, ingrediente, quantidade, tempo ou preço de cabeça. O que vale é só o que o servidor guardou.
- Não invente endereço: use só os que vieram nos resultados de `web_search`.
