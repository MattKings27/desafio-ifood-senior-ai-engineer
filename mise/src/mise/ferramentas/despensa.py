"""Despensa, custo unitário, conversão de medidas e as mudanças que ela conta."""

from __future__ import annotations

from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from mise.casamento import casar
from mise.despensa import Despensa, Ingrediente, OrigemDoItem
from mise.despensa_json import custo_texto, mudanca_json
from mise.dinheiro import Dinheiro
from mise.erros import Ausente, ErroDeUso
from mise.serializacao import _reais, _resposta, protegido
from mise.unidades import converter_medida

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

    from mise.despensa_editavel import DespensaEditavel, Mudanca
    from mise.mcp_server import Sessao


class AcaoNaDespensa(StrEnum):
    """O que ela contou que mudou, como o agente pede em `atualizar_despensa`."""

    ADICIONAR = "adicionar"
    CORRIGIR = "corrigir"
    ACABOU = "acabou"
    REMOVER = "remover"
    INFORMAR_EMBALAGEM = "informar_embalagem"


def _decimal(valor: float | None) -> Decimal | None:
    return Decimal(str(valor)) if valor is not None else None


def item_da_conversa(despensa: Despensa, ingrediente: str) -> Ingrediente:
    """O item de que ela fala: pelo id ou pelo nome, com o casamento confiável do portão.

    "o bacon" acha "Bacon"; "frango" acha "Peito de frango". Sem casamento
    confiável não há chute: é `Ausente`, com os nomes parecidos para o agente
    confirmar com ela.
    """
    direto = despensa.por_id(ingrediente.strip())
    if direto is not None:
        return direto
    casamento = casar(ingrediente, despensa)
    if casamento.confiavel and casamento.item is not None:
        return casamento.item
    parecido = casamento.item.nome if casamento.item is not None else None
    raise Ausente(
        f"não encontrei {ingrediente!r} na despensa",
        parecido=parecido or "nenhum",
        orientacao="confirme com ela o nome do item, ou use a acao 'adicionar'",
    )


def _operacao(
    sessao: Sessao,
    acao: AcaoNaDespensa,
    ingrediente: str,
    *,
    estoque: float | None,
    unidade: str,
    quantidade_comprada: float | None,
    preco_pago: float | None,
    conteudo_da_embalagem: str,
    motivo: str,
) -> Callable[[DespensaEditavel], Mudanca]:
    """A mudança que o agente pediu, pronta para `Sessao.mudar_despensa`."""
    canal = sessao.canal
    if acao is AcaoNaDespensa.ADICIONAR:
        if estoque is None or not unidade.strip():
            raise ErroDeUso(
                "para acrescentar, diga quanto ela tem (estoque) e em que unidade",
                exemplo="estoque=0.5, unidade='kg'",
            )
        return lambda e: e.adicionar(
            nome=ingrediente,
            estoque=Decimal(str(estoque)),
            unidade=unidade,
            quantidade_comprada=_decimal(quantidade_comprada),
            preco_pago=_decimal(preco_pago),
            origem=OrigemDoItem.JA_TINHA,
            motivo=motivo,
            canal=canal,
        )
    item = item_da_conversa(sessao.despensa, ingrediente)
    item_id = item.id
    if acao is AcaoNaDespensa.ACABOU:
        return lambda e: e.acabou(item_id, motivo=motivo, canal=canal)
    if acao is AcaoNaDespensa.REMOVER:
        return lambda e: e.remover(item_id, motivo=motivo, canal=canal)
    if acao is AcaoNaDespensa.INFORMAR_EMBALAGEM:
        if not conteudo_da_embalagem.strip():
            raise ErroDeUso(
                "diga quanto vem na embalagem, como '1 kg' ou '400 g'",
                campo="conteudo_da_embalagem",
            )
        return lambda e: e.informar_embalagem(
            item_id, conteudo_da_embalagem, motivo=motivo, canal=canal
        )
    if (
        preco_pago is not None
        and item.origem is OrigemDoItem.ORCAMENTO
        and Decimal(str(preco_pago)) != item.preco_pago.valor
    ):
        # Mudar o valor de uma compra com os complementos mexe nos R$ 80,00, e
        # dinheiro dela o agente só gasta pelo portão do prato.
        raise ErroDeUso(
            f"{item.nome} foi comprado com os complementos: o valor pago se corrige na tela, "
            "onde ela vê o orçamento mudar",
            ingrediente=item.nome,
        )
    return lambda e: e.corrigir(
        item_id,
        estoque=_decimal(estoque),
        unidade=unidade or None,
        quantidade_comprada=_decimal(quantidade_comprada),
        preco_pago=_decimal(preco_pago),
        conteudo_da_embalagem=conteudo_da_embalagem or None,
        motivo=motivo,
        canal=canal,
    )


def _parte_de_tudo(parte: Dinheiro, investido: Decimal) -> dict[str, Any]:
    """Quanto `parte` é de tudo o que ela pagou, em Decimal e já escrito.

    A proporção vem pronta pelo mesmo motivo que a soma: "quase um quarto" ou
    "mais de 20%" feito de cabeça é número sem conta por trás.
    """
    if not investido:
        return {"fracao": 0.0, "texto": "nada pago na despensa ainda"}
    fracao = parte.valor / investido
    pct = (fracao * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    escrito = "menos de 0,1%" if fracao > 0 and not pct else f"{pct}%".replace(".", ",")
    return {
        "fracao": round(float(fracao), 4),
        "texto": f"{escrito} de tudo o que a senhora pagou",
    }


def _capital_sem_prato(sessao: Sessao) -> dict[str, Any]:
    """O dinheiro da despensa que nenhuma receita avaliada usa ainda.

    É a pergunta do §2.1 em número: o que ela já comprou e ainda não virou
    prato. Sem receita avaliada, é a despensa inteira; a cada receita avaliada,
    o que ela usa sai da conta. Não é opinião sobre o que "combina" com o
    cardápio: é quais itens nenhum prato em avaliação pede.
    """
    usados = {
        uso.casamento.item.nome
        for receita in sessao.candidatas.values()
        for uso in sessao.avaliar(receita).usos
        if uso.casamento.item is not None and not uso.rotulo
    }
    despensa = sessao.despensa
    parados = [i for i in despensa.por_valor() if i.nome not in usados]
    total = sum((i.preco_pago for i in parados), Dinheiro.zero())
    investido = despensa.total_investido.valor
    # A soma dos dois maiores vem pronta, e a parte que ela é de tudo o que a
    # Dona Maria pagou também: sem elas, o agente somava de cabeça ("mais de
    # R$ 161") e o guard-rail tinha de apagar o número.
    dois = parados[:2]
    soma_dos_dois = sum((i.preco_pago for i in dois), Dinheiro.zero())
    return {
        "total": _reais(total),
        "fracao_da_despensa": round(float(total.valor / investido), 4) if investido else 0.0,
        "receitas_avaliadas": len(sessao.candidatas),
        "maiores": [{"ingrediente": i.nome, "pago": _reais(i.preco_pago)} for i in parados[:8]],
        "dois_maiores": {
            "ingredientes": [i.nome for i in dois],
            "somam": _reais(soma_dos_dois),
            "parte_de_tudo": _parte_de_tudo(soma_dos_dois, investido),
        },
    }


def registrar(servidor: MCPServer, sessao: Sessao) -> None:
    """Despensa, custo unitário, conversão de medidas e as mudanças que ela conta."""

    # --- despensa e custos ------------------------------------------------ #

    @servidor.tool()
    @protegido
    async def diagnostico_despensa() -> str:
        """Panorama da despensa: o que ela tem, quanto investiu e onde o dinheiro está parado.

        Comece por aqui. O custo que a planilha não permite deduzir (a embalagem
        sem peso) vem estimado com a fonte, dito como estimativa: nunca pergunte
        o peso nem o preço a ela; ela corrige quando quiser.
        """
        d = sessao.despensa
        total = d.total_investido
        por_valor = d.por_valor()
        return _resposta(
            {
                "itens": len(d),
                "total_investido": _reais(total),
                "maiores_investimentos": [
                    {
                        "ingrediente": i.nome,
                        "pago": _reais(i.preco_pago),
                        "fracao_do_total": round(float(d.fracao_de(i)), 4),
                        "custo_unitario": str(i.custo),
                    }
                    for i in por_valor[:8]
                ],
                "itens_com_normalizacao_relevante": [
                    {
                        "ingrediente": i.nome,
                        "conta_ingenua": _reais(i.custo_ingenuo),
                        "conta_correta": str(i.custo),
                        "porque": i.custo.derivacao,
                    }
                    for i in d
                    if i.normalizacao_importou
                ],
                "pendencias": [
                    {
                        "ingrediente": p.ingrediente,
                        "motivo": p.motivo,
                        "pergunta": p.pergunta,
                        "dinheiro_envolvido": _reais(p.impacto),
                    }
                    for p in d.pendencias
                ],
                "orcamento": {
                    "estado": str(sessao.dossie.orcamento()),
                    "restante": _reais(sessao.dossie.orcamento().restante),
                },
                "capital_sem_prato": _capital_sem_prato(sessao),
            }
        )

    @servidor.tool()
    @protegido
    async def custo_unitario(ingrediente: str) -> str:
        """Custo por quilo, litro ou unidade de um item da despensa, com a derivação."""
        casamento = casar(ingrediente, sessao.despensa)
        if casamento.item is None:
            return _resposta(
                {
                    "encontrado": False,
                    "texto_buscado": ingrediente,
                    "orientacao": "Não está na despensa. Se a receita pede, vira compra "
                    "complementar, cotada pelo preço de referência de supermercado; não "
                    "pergunte o preço a ela.",
                }
            )
        item = casamento.item
        pendencia = sessao.despensa.pendencia_de(item.nome)
        return _resposta(
            {
                "encontrado": True,
                "ingrediente": item.nome,
                "como_encontrei": casamento.explicacao(),
                # Sem o preço, não há custo: "R$ 0,00/kg" seria um número inventado.
                "custo_unitario": str(item.custo) if item.preco_informado else custo_texto(item),
                "derivacao": item.custo.derivacao,
                "confianca": item.custo.confianca.value,
                "estoque": f"{item.estoque}",
                "pago_na_compra": _reais(item.preco_pago) if item.preco_informado else None,
                **({"pergunta": pendencia.pergunta} if pendencia is not None else {}),
            }
        )

    @servidor.tool()
    @protegido
    async def consultar_planilha() -> str:
        """A planilha dela em texto: as duas abas célula a célula, as mudanças dela,
        os itens de hoje com o custo unitário e a conta, o que falta saber e o
        extrato dos complementos.

        Use quando ela perguntar o que está na planilha ou o que mudou. Os valores
        em reais daqui podem ser repetidos a ela como estão.
        """
        versao, texto = sessao.atualizar_planilha_txt()
        arquivo = sessao.arquivo_txt
        return _resposta(
            {"versao": versao, "arquivo": str(arquivo) if arquivo else None, "texto": texto}
        )

    @servidor.tool()
    @protegido
    async def atualizar_despensa(
        acao: str,
        ingrediente: str,
        *,
        estoque: float | None = None,
        unidade: str = "",
        quantidade_comprada: float | None = None,
        preco_pago: float | None = None,
        conteudo_da_embalagem: str = "",
        motivo: str = "",
    ) -> str:
        """Anota uma mudança na despensa que ela contou, e refaz a conta do item.

        acao: "adicionar" (algo que ela já tinha em casa: estoque e unidade, e o
        preço se ela souber), "corrigir" (estoque, unidade, quantidade comprada ou
        preço), "acabou", "remover" ou "informar_embalagem" (conteudo_da_embalagem,
        como "1 kg" ou "400 g": o peso que ela disser vale mais que o estimado).
        O nome do item não muda. Nada aqui gasta dos complementos: tirar um item
        que ela comprou com eles devolve o valor, e o que ela for comprar vai por
        registrar_compra, pelo prato confirmado.
        Devolve o antes e o depois, o custo novo com a conta e as receitas
        afetadas.
        """
        try:
            escolha = AcaoNaDespensa(acao.strip().lower())
        except ValueError:
            validas = ", ".join(a.value for a in AcaoNaDespensa)
            raise ErroDeUso(f"acao desconhecida: {acao}", validas=validas) from None
        operacao = _operacao(
            sessao,
            escolha,
            ingrediente,
            estoque=estoque,
            unidade=unidade,
            quantidade_comprada=quantidade_comprada,
            preco_pago=preco_pago,
            conteudo_da_embalagem=conteudo_da_embalagem,
            motivo=motivo,
        )
        mudanca, afetadas = sessao.mudar_despensa(operacao)
        return _resposta(mudanca_json(sessao, mudanca, afetadas))

    @servidor.tool()
    @protegido
    async def converter_medida_culinaria(quantidade: float, medida: str, ingrediente: str) -> str:
        """Converte medida de receita ("1 xícara") para quilo/litro, usando densidade.

        Tratar mililitro como grama erra +89% em farinha de trigo. Use sempre
        esta ferramenta em vez de converter de cabeça.
        """
        convertida = converter_medida(Decimal(str(quantidade)), medida, ingrediente)
        return _resposta(
            {
                "entrada": f"{quantidade} {medida} de {ingrediente}",
                "resultado": f"{convertida.quantidade}",
                "derivacao": convertida.derivacao,
                "incerteza": f"±{convertida.incerteza_relativa:.0%}",
                "confiavel": convertida.confiavel,
            }
        )


__all__ = ["AcaoNaDespensa", "item_da_conversa", "registrar"]
