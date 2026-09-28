"""Receitas: o portão de viabilidade, a comparação e a pesquisa na internet.

A pesquisa depende de mundo externo (rede e HTML de terceiro) e falha por
razões que nenhuma outra ferramenta do motor conhece; por isso a rede fica toda
aqui, e não no cálculo.

A receita da internet só entra pela página que o próprio servidor buscou
(`buscar_receita_na_web`): não há ferramenta que receba o HTML de quem chama,
porque o modelo poderia mandar uma página que ninguém buscou.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from mise.despensa_json import slug_da_receita

# Import de verdade, não só para tipagem: o `MCPServer` monta o schema da
# ferramenta lendo esta anotação no módulo dela.
from mise.mcp_server import ReceitaEntrada
from mise.passos import detalhar
from mise.receitas_json import ajuste_para_a_consultora
from mise.serializacao import _avaliacao_json, _resposta, protegido

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

    from mise.mcp_server import Sessao


def registrar(servidor: MCPServer, sessao: Sessao) -> None:
    """O portão de viabilidade, a comparação das candidatas e a pesquisa na web."""

    # --- receitas e portão ------------------------------------------------- #

    @servidor.tool()
    @protegido
    async def avaliar_receita(
        receita_id: str | None = None, receita: ReceitaEntrada | None = None
    ) -> str:
        """O PORTÃO: ela consegue produzir este prato?

        Chame com o `receita_id` que `buscar_receita_na_web` devolve: a receita é
        a que o servidor leu da página, e não se redigita. A `receita` inteira é
        para a receita que ELA dita, sem endereço (um endereço digitado não faz
        a receita ser da internet). Com o `receita_id` e a `receita` juntos, a
        `receita` leva só o que ela corrigiu sobre a receita guardada: o
        rendimento, o modo de preparo, ou quanto vai de uma linha (a linha com
        o mesmo texto e a quantidade dela). Mudar o que a página diz é recusado.

        Checa ingredientes, equipamentos, técnicas e rotina. Devolve APTO,
        APTO COM COMPRA, FALTA INFO (com as perguntas) ou BLOQUEADO (com o
        motivo). Guarda a receita como candidata (em avaliação) para
        `proxima_pergunta`, e devolve o `receita_id` dela.

        À Dona Maria só se pergunta gosto, equipamento, técnica e limite da
        rotina: as `perguntas` são só dessas. Peso, medida, quantidade, preço e
        "é o seu X?" nunca se perguntam: chegam pré-determinados, com a fonte,
        e ditos como estimativa quando são. Nunca pergunte isso a ela; diga o
        valor e de onde veio, e que ela corrige se quiser.

        `ingredientes` é o §2.3 linha por linha: quanto a receita pede, quanto
        ela tem, quanto sobra, e o que falta comprar com o custo e se cabe no
        orçamento. A linha que não diz quanto vai ("Milho") vem com a unidade de
        venda e a fonte ("a receita não diz quanto; considerei 1 lata de 170
        g"); o tempero escrito só pelo nome ("Sal", "Azeite") vale a gosto. O
        que a receita diz ser opcional vem em `opcionais`: diga a ela que ficou
        de fora, nunca omita.

        O item parecido da despensa ("mandioca" e a farinha de mandioca dela)
        fica como compra, e a decisão vem dita ("considerei que mandioca não é
        a sua farinha de mandioca"): nunca conte como se ela tivesse. Se ela
        corrigir, a linha volta com o `receita_id`, o mesmo texto e
        `item_da_despensa` (o nome do item, ou "" quando não é). O peso de uma
        medida caseira vem de uma tabela com fonte (IBGE, USDA); o peso que ela
        disser vale mais, e volta na linha com `peso` ("300 g"). Preço que não
        se acha em página de supermercado não se pergunta: a receita fica de
        fora, com o motivo.

        Cada pergunta vem com as `opcoes` de resposta (inclusive "não sei"), e
        `por_passo` mostra onde cada exigência aparece: o passo, o trecho que a
        denunciou e o estado na cozinha dela; o tempo, a temperatura e o frio de
        cada passo; e, à parte, o que vem do nome ou dos ingredientes.

        `avisos` é o que não impede o prato, mas ela precisa saber antes de
        decidir (com uma boca só, uma panela espera a outra e leva mais tempo):
        conte a ela junto com o veredito.

        `pode_aceitar` diz se ela já pode aceitar o prato (ou comprar para ele);
        `falta_para_aceitar` diz o que falta, em frases para ela. O que toda
        cozinha tem (fogão, panela funda, refogar) passa como suposto e não se
        pergunta item por item: quando a receita usa algo disso que ela não
        confirmou, `confirmar_a_cozinha` traz a `pergunta`, uma só, para a hora
        do aceite ou da compra, e o sim dela vai em
        registrar_resposta(tipo="cozinha", campo=<receita_id>, resposta="tem").

        `orcamento` traz o orçamento dela (`inicial`), o que já foi gasto e o
        que resta: é com o `restante` que a compra foi comparada. Falar em
        "cabe nos R$ 80,00" só com esse número à vista.
        """
        dominio, recado = sessao.receita_para_avaliar(receita_id, receita)
        sessao.guardar(dominio)
        # O que falta sem preço é procurado nos mercados de São Paulo, com prazo.
        await asyncio.to_thread(sessao.precificar_o_que_falta, dominio)
        perfil = sessao.perfil
        avaliacao = sessao.avaliar(dominio, perfil=perfil)
        resultado = {"receita_id": slug_da_receita(dominio), **_avaliacao_json(avaliacao)}
        resultado.update(detalhar(dominio, perfil, avaliacao))
        orcamento = sessao.dossie.orcamento()
        resultado.update(ajuste_para_a_consultora(avaliacao, orcamento.restante))
        # O orçamento com que a compra foi comparada, para o "cabe nos R$ 80,00" ter origem.
        resultado["orcamento"] = {
            "inicial": str(orcamento.inicial),
            "gasto": str(orcamento.gasto),
            "restante": str(orcamento.restante),
        }
        if recado is not None:
            resultado["recado"] = recado
        if not avaliacao.permite_precificar:
            resultado["orientacao"] = (
                "NÃO calcule preço nem sugira que ela compre ingrediente para este prato "
                "enquanto a viabilidade não for confirmada."
            )
        return _resposta(resultado)

    @servidor.tool()
    @protegido
    async def comparar_candidatas() -> str:
        """As receitas em avaliação lado a lado, e o catálogo inteiro separado como na tela.

        É o "aproveitar o que ela já tem" do §2.1. Para cada receita avaliada:
        o `receita_id`, quantos ingredientes ela já tem, quanto do estoque dela
        o prato usa, quanto sai do bolso para completar e o que o portão diz.
        Ordena pelas que mais aproveitam a despensa e menos pedem compra. Não
        escolhe por ela.

        `catalogo` é a grade de receitas dela, com as mesmas contas da tela:
        `da_para_fazer` (liberadas, com `como`: com o que ela tem ou comprando
        quanto), `usa_so_o_que_tem` (nada a comprar; `falta_responder` diz o que
        segura), `precisa_comprar` (com `falta_comprar`) e `linha_sem_leitura`,
        mais o `texto` pronto do que falta. É daqui que sai a resposta a "o que
        eu consigo fazer?".
        """
        return _resposta(sessao.comparar())

    # --- pesquisa na internet --------------------------------------------- #

    @servidor.tool()
    @protegido
    async def buscar_receita_na_web(url: str, fonte: str = "") -> str:
        """Traz uma página de receita da internet para o catálogo e devolve o `receita_id`.

        Complementa a busca do Hermes: ele acha os endereços, este traz a página,
        lê a receita estruturada (JSON-LD ou microdata) e guarda no catálogo com
        a procedência (site, autor, foto e tempos da página). Devolve o
        `receita_id` que as outras ferramentas aceitam no lugar da receita. O
        endereço que já está no catálogo não é buscado de novo e volta com
        `ja_conhecida`. O nome do site vem da página, não de `fonte`.

        Trazer não põe a receita em avaliação: para conferir se ela consegue
        fazer, chame `avaliar_receita` com o `receita_id`.

        Tudo que é rede está aqui, e não no cálculo: timeout, três tentativas com
        backoff exponencial e jitter, e circuit breaker por domínio. Um site fora
        do ar não impede a busca nos outros, e martelar um que já se sabe quebrado
        só atrasa a recuperação dele.

        Quando falha, falha **dizendo o que fazer**: sem internet a consultoria
        continua, com a senhora ditando a receita.
        """
        return _resposta(await asyncio.to_thread(sessao.receita_da_web, url, fonte))


__all__ = ["registrar"]
