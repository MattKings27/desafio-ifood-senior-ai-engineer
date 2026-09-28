"""Preço: custo por porção, cenários, sensibilidade e o preço do que falta comprar."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from mise.cmv import calcular
from mise.dinheiro import Dinheiro

# Import de verdade, não só para tipagem: o `MCPServer` monta o schema da
# ferramenta lendo esta anotação no módulo dela.
from mise.mcp_server import ReceitaEntrada
from mise.preco import RETENCAO, TAXA_PLATAFORMA, lucro_em, montar_cenarios, sensibilidade
from mise.serializacao import _reais, _resposta, prato_para_auditoria, protegido

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

    from mise.mcp_server import Sessao


def _parecer_conjunto(pareceres: list[dict[str, Any] | None]) -> dict[str, Any] | None:
    """Um parecer para os três cenários: confere se todos conferiram."""
    validos = [p for p in pareceres if p is not None]
    if not validos:
        return None
    estados = [p.get("confere") for p in validos]
    return {
        "confere": None if None in estados else all(estados),
        "por": validos[0].get("por"),
        "observacao": "; ".join(str(p.get("observacao", "")) for p in validos),
    }


def registrar(servidor: MCPServer, sessao: Sessao) -> None:
    """Custo por porção, cenários de preço, sensibilidade e cotações do que falta."""

    @servidor.tool()
    @protegido
    async def buscar_preco_na_web(ingrediente: str) -> str:
        """Procura o preço médio em São Paulo de um ingrediente que falta e não tem preço.

        Chame quando `avaliar_receita` disser que falta comprar um ingrediente
        sem preço. Nunca pergunte o preço à Dona Maria: o servidor procura o
        ingrediente pelo nome nos supermercados de São Paulo, escolhe o produto
        com as palavras do nome e sem as que dizem que é outro produto, e faz a
        média do quilo (do litro, da unidade), com o mercado, o produto, o preço
        e o link de cada fonte. O preço fica guardado e entra na conta da
        receita na próxima avaliação. Sem achar, volta `achou: false`, e o item
        fica sem preço, sem pergunta a ela.
        """
        return _resposta(await asyncio.to_thread(sessao.buscar_preco_na_web, ingrediente))

    @servidor.tool()
    @protegido
    async def calcular_cmv(
        receita_id: str | None = None, receita: ReceitaEntrada | None = None
    ) -> str:
        """Custo de ingrediente de UMA porção, linha a linha.

        Informe o `receita_id` (o id que `buscar_receita_na_web` e
        `avaliar_receita` devolvem): o custo sai da receita guardada, a mesma
        que passou pela conferência. A `receita` digitada só vale para a
        receita que ela ditou, e tem de ser igual à que foi avaliada: receita
        redigitada com outra quantidade é recusada, com o que mudou, e o recado
        é usar o `receita_id`.

        Recusa receita cuja viabilidade não foi confirmada: chame
        `avaliar_receita` antes. Também recusa quando algum custo é
        desconhecido, em vez de devolver um total parcial.
        """
        dominio = sessao.receita_para_custear(receita_id, receita)
        sessao.guardar(dominio)
        avaliacao = sessao.avaliar(dominio)
        cmv = calcular(dominio, avaliacao)
        parecer = sessao.auditar(prato_para_auditoria(cmv))

        return _resposta(
            {
                "prato": cmv.receita,
                "cmv_por_porcao": _reais(cmv.para_precificar),
                "auditoria_independente": parecer,
                "e_faixa": cmv.e_faixa,
                "faixa": (
                    {"minimo": _reais(cmv.minimo), "maximo": _reais(cmv.maximo)}
                    if cmv.e_faixa
                    else None
                ),
                "incerteza": f"±{cmv.incerteza_relativa:.1%}",
                "rendimento_original": cmv.rendimento_original,
                "linhas": [
                    {
                        "ingrediente": linha.ingrediente,
                        "quantidade": linha.quantidade,
                        "custo": _reais(exibido),
                        "derivacao": linha.derivacao,
                    }
                    for linha, exibido in zip(cmv.linhas, cmv.custos_exibidos(), strict=True)
                ],
                "itens_a_gosto": list(cmv.itens_a_gosto),
                "maiores_custos": [
                    {"ingrediente": linha.ingrediente, "custo": _reais(linha.custo)}
                    for linha in cmv.maiores_custos()
                ],
                "explicacao": cmv.explicacao(),
            }
        )

    # --- preço -------------------------------------------------------------- #

    @servidor.tool()
    @protegido
    async def cenarios_preco(
        receita_id: str | None = None,
        prato: str | None = None,
        cmv_por_porcao: float | None = None,
    ) -> str:
        """Três cenários de preço para um prato aprovado no portão, com a taxa de 10% aberta.

        Informe `receita_id` (o id da receita avaliada) ou o nome do `prato`; o
        id vale mais que o nome.

        O custo é recalculado aqui a partir da receita avaliada; o número não vem
        de quem chama. Se `cmv_por_porcao` vier, tem que bater com o calculado.
        Apresente os três e deixe a Dona Maria escolher. Não recomende um:
        o posicionamento do negócio é decisão dela.
        """
        prato = sessao.prato_pedido(receita_id, prato)
        composicao = sessao.cmv_conferido(prato)
        cmv = sessao.custo_conferido(prato, cmv_por_porcao)
        tabela = montar_cenarios(cmv)
        pareceres = [
            sessao.auditar(prato_para_auditoria(composicao, c.preco, c.lucro)) for c in tabela
        ]
        return _resposta(
            {
                "prato": prato,
                "cmv": _reais(cmv),
                "preco_minimo_sem_prejuizo": _reais(tabela.preco_minimo),
                "explicacao_da_taxa": tabela.explicacao_da_taxa(),
                "cenarios": [
                    {
                        "nome": c.nome,
                        "descricao": c.descricao,
                        "preco": _reais(c.preco),
                        "taxa_ifood": _reais(c.valor_da_taxa),
                        "ela_recebe": _reais(c.recebe),
                        "lucro": _reais(c.lucro),
                        "food_cost": f"{c.food_cost:.0%}",
                        "margem_sobre_preco": f"{c.margem_sobre_preco:.0%}",
                        "explicacao": c.explicacao(),
                    }
                    for c in tabela
                ],
                "orientacao": "Mostre os três e pergunte qual ela prefere. A escolha é dela.",
                "auditoria_independente": _parecer_conjunto(pareceres),
            }
        )

    @servidor.tool()
    @protegido
    async def testar_sensibilidade(
        preco: float, receita_id: str | None = None, prato: str | None = None
    ) -> str:
        """A conta de um preço que ela propôs, e quanto de alta no insumo ele aguenta.

        Informe `receita_id` (o id da receita avaliada) ou o nome do `prato`; o
        id vale mais que o nome.

        Use quando ela disser um preço: `no_preco` traz a taxa, o que chega para
        ela e o lucro daquele preço exato. Só registre o aceite depois que ela
        confirmar, vendo essa conta.
        """
        custo = sessao.custo_conferido(sessao.prato_pedido(receita_id, prato))
        cobrado = Dinheiro.de(preco)
        resultado = sensibilidade(custo, cobrado)
        folga = resultado["folga_ate_zerar"]
        lucro = lucro_em(cobrado, custo)
        return _resposta(
            {
                "no_preco": {
                    "preco": _reais(cobrado),
                    "taxa_ifood": _reais((cobrado * TAXA_PLATAFORMA).arredondado()),
                    "ela_recebe": _reais((cobrado * RETENCAO).arredondado()),
                    "custo_de_ingrediente": _reais(custo),
                    "lucro": _reais(lucro.arredondado()),
                    "da_prejuizo": lucro.valor < 0,
                    "preco_minimo_sem_prejuizo": _reais(montar_cenarios(custo).preco_minimo),
                },
                "cmv_atual": str(resultado["cmv_original"]),
                "se_subir_20_porcento": {
                    "novo_cmv": str(resultado["cmv_com_alta"]),
                    "novo_lucro": str(resultado["lucro_com_alta"]),
                    "continua_lucrativo": resultado["ainda_lucrativo"],
                },
                "aguenta_alta_de": f"{float(folga):.0%}" if isinstance(folga, Decimal) else "0%",
            }
        )

    # --- o preço do que falta comprar -------------------------------------- #

    @servidor.tool()
    @protegido
    async def registrar_preco_mercado(
        ingrediente: str,
        valor: float,
        quantidade: float | None = None,
        unidade: str = "",
        origem: str = "informado_por_ela",
    ) -> str:
        """Guarda quanto custa comprar um ingrediente que falta na despensa, quando ela diz.

        A plataforma não pergunta preço: o que falta sai cotado pelo preço de
        referência de supermercado, com a fonte. Quando ela mesma disser quanto
        paga, o preço dela vale mais, e é aqui que ele fica.

        `origem` distingue o que ela mesma informou do que foi pesquisado ou
        estimado: confianças diferentes, e é ela quem decide se aceita as duas
        últimas.

        Informe `quantidade` e `unidade` sempre que ela disser por quanto é o
        preço ("R$ 6 a lata": quantidade=1, unidade="lata"; "R$ 50 o quilo":
        quantidade=1, unidade="kg"). Sem isso a conta assume que o valor é o de
        comprar exatamente o que a receita pede, e a conta sai com essa premissa.
        """
        preco, faltando = sessao.cotar(ingrediente, valor, quantidade, unidade, origem)
        restante = sessao.dossie.orcamento().restante
        return _resposta(
            {
                "registrado": str(preco),
                "casou_com_o_que_falta": preco.ingrediente in faltando,
                "o_que_falta_nos_pratos": faltando,
                "orcamento_restante": _reais(restante),
                "observacao": (
                    "reavalie o prato: com o preço conhecido a avaliação já consegue "
                    "dizer se a compra cabe no orçamento"
                ),
            }
        )

    @servidor.tool()
    @protegido
    async def consultar_precos_de_mercado() -> str:
        """As cotações já registradas para o que falta comprar."""
        return _resposta({"precos": [str(p) for p in sessao.dossie.precos()]})


__all__ = ["registrar"]
