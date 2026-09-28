"""Custo de Mercadoria Vendida, e o ponto onde o portão vira lei.

O enunciado define o CMV como o somatório de `quantidade usada × custo unitário`
de cada ingrediente. A conta é simples; o que não é simples é **recusar-se a
fazê-la** quando ela produziria um número bonito e mentiroso.

Este módulo recusa em três situações:

1. **Viabilidade não confirmada.** Se o portão não disse que ela consegue
   produzir, não existe preço a calcular. É aqui que a garantia do §2.2 do
   desafio deixa de ser uma instrução de prompt e passa a ser uma assinatura
   de função: `calcular` exige uma `Avaliacao` apta, e não há outro caminho.

2. **Custo indeterminado.** Se algum ingrediente tem custo desconhecido (a
   cobertura de chocolate sem peso na embalagem), o CMV sairia parcial. Um
   CMV parcial apresentado como total é pior que nenhum CMV.

3. **Incerteza alta.** Quando a conversão de medida acumula incerteza (densidade
   de farinha varia, peso de ovo varia), devolvemos **faixa**, não ponto. Fingir
   precisão de centavo sobre uma estimativa de xícara é desonestidade numérica.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from typing import TYPE_CHECKING

from mise.dinheiro import CENTAVO, Dinheiro
from mise.erros import CustoIndeterminado, ViabilidadeNaoConfirmada
from mise.viabilidade import Avaliacao, ItemFaltante, UsoDeIngrediente

if TYPE_CHECKING:
    from mise.receita import Receita

#: Acima desta incerteza relativa agregada, o CMV é apresentado como faixa.
LIMIAR_FAIXA: Decimal = Decimal("0.08")


@dataclass(frozen=True, slots=True)
class LinhaCMV:
    """Uma linha da composição de custo, como aparece para a Dona Maria."""

    ingrediente: str
    quantidade: str
    custo: Dinheiro
    derivacao: str
    incerteza: Decimal

    @property
    def participacao_texto(self) -> str:
        return self.derivacao


@dataclass(frozen=True, slots=True)
class CMV:
    """O custo de ingrediente de uma porção, com a conta inteira aberta."""

    receita: str
    linhas: tuple[LinhaCMV, ...]
    total: Dinheiro
    incerteza_relativa: Decimal
    itens_a_gosto: tuple[str, ...] = ()
    rendimento_original: int = 1
    #: Os opcionais que ela não tem: ficam de fora da conta, e a explicação diz isso.
    opcionais_de_fora: tuple[str, ...] = ()
    #: Quando a receita não dizia o rendimento: a estimativa, dita como estimativa.
    rendimento_estimado: str = ""

    @property
    def e_faixa(self) -> bool:
        """A incerteza acumulada exige apresentar intervalo em vez de ponto."""
        return self.incerteza_relativa > LIMIAR_FAIXA

    @property
    def minimo(self) -> Dinheiro:
        return (self.total * (Decimal("1") - self.incerteza_relativa)).arredondado()

    @property
    def maximo(self) -> Dinheiro:
        return (self.total * (Decimal("1") + self.incerteza_relativa)).arredondado_para_cima()

    @property
    def para_precificar(self) -> Dinheiro:
        """O valor que vai para a precificação.

        Quando há faixa, usamos o **topo**. Errar o preço para cima custa uma
        venda; errar para baixo custa dinheiro em toda venda. Pelo mesmo motivo
        o centavo é arredondado para cima: é daqui que o preço mínimo sai.
        """
        return self.maximo if self.e_faixa else self.total.arredondado_para_cima()

    def custos_exibidos(self) -> tuple[Dinheiro, ...]:
        """O custo de cada linha em centavos, somando exatamente o total exibido.

        Arredondar linha a linha faz a soma da tela divergir do total por um ou
        dois centavos, e quem confere a conta acha um erro onde não há. Aqui cada
        linha desce para o centavo e os centavos que faltam para o total vão para
        as linhas com maior resto (método do maior resto). Nenhuma linha se
        afasta mais de um centavo do valor exato.

        O alvo é o custo usado no preço; numa faixa, o total arredondado para
        cima, já que o topo da faixa inclui a incerteza e não é soma de linhas.
        """
        alvo = self.total.arredondado_para_cima() if self.e_faixa else self.para_precificar
        exatos = [linha.custo.valor for linha in self.linhas]
        pisos = [v.quantize(CENTAVO, rounding=ROUND_FLOOR) for v in exatos]
        faltam = int((alvo.valor - sum(pisos, Decimal(0))) / CENTAVO)
        por_resto = sorted(range(len(exatos)), key=lambda i: exatos[i] - pisos[i], reverse=True)
        for i in por_resto[:faltam]:
            pisos[i] += CENTAVO
        return tuple(Dinheiro(v) for v in pisos)

    def maiores_custos(self, n: int = 3) -> tuple[LinhaCMV, ...]:
        """Os ingredientes que mais pesam: é onde mexer muda o preço."""
        return tuple(sorted(self.linhas, key=lambda linha: linha.custo.valor, reverse=True)[:n])

    def explicacao(self) -> str:
        """A conta escrita para ser lida em voz alta.

        Com os mesmos centavos da tela (`custos_exibidos` e `para_precificar`):
        somando as linhas que ela ouve, chega-se ao total que ela ouve.
        """
        partes = [f"Custo de ingrediente de 1 porção de {self.receita}:"]
        partes.extend(
            f"  · {linha.ingrediente}: {linha.quantidade} = {exibido}"
            for linha, exibido in zip(self.linhas, self.custos_exibidos(), strict=True)
        )
        if self.itens_a_gosto:
            partes.append(
                f"  · {', '.join(self.itens_a_gosto)}: a gosto, custo desprezível "
                "(mas contado, não esquecido)"
            )
        if self.opcionais_de_fora:
            partes.append(
                f"  · {', '.join(self.opcionais_de_fora)}: opcional, e a senhora não tem; "
                "ficou de fora da conta"
            )
        if self.e_faixa:
            partes.append(
                f"  Total: entre {self.minimo} e {self.maximo}. A variação vem de medidas "
                "caseiras como xícara, que mudam de uma pessoa para outra."
            )
            partes.append(f"  Vou usar {self.para_precificar} para o preço, pra não faltar.")
        else:
            partes.append(f"  Total: {self.para_precificar}")
        if self.rendimento_estimado:
            partes.append(
                f"  (a receita não diz o rendimento: {self.rendimento_estimado}; "
                "os valores acima já são de uma só)"
            )
        elif self.rendimento_original > 1:
            partes.append(
                f"  (a receita original rende {self.rendimento_original} porções; "
                "os valores acima já são de uma só)"
            )
        return "\n".join(partes)


def calcular(receita: Receita, avaliacao: Avaliacao) -> CMV:
    """Calcula o CMV de **uma porção**, exigindo viabilidade confirmada.

    O parâmetro `avaliacao` não é opcional e não tem valor padrão. É deliberado:
    torna impossível chamar esta função sem antes passar pelo portão.
    """
    if not avaliacao.permite_precificar:
        raise ViabilidadeNaoConfirmada(
            receita.nome,
            avaliacao.veredito.rotulo,
            tuple(p.texto for p in avaliacao.perguntas)
            or tuple(str(i) for i in avaliacao.impedimentos),
        )

    indeterminados = tuple(f.nome for f in avaliacao.faltantes if not f.custo_conhecido)
    if indeterminados:
        raise CustoIndeterminado(receita.nome, indeterminados)

    # O rendimento da receita, ou a estimativa pelo peso (nunca perguntado).
    rendimento = avaliacao.rendimento
    porcoes = rendimento.porcoes if rendimento is not None else receita.rendimento_porcoes
    divisor = Decimal(porcoes)

    # Compras complementares entram no CMV, conforme o §2.4 do enunciado, e
    # entram como **linha**, e não somadas por fora.
    #
    # Somar direto no total deixaria a conta impossível de conferir: quem
    # somasse as linhas na tela chegaria a um número diferente do total
    # exibido, e não teria como descobrir de onde veio a diferença. Numa
    # ferramenta cujo argumento inteiro é "a conta está aberta", um total que
    # não fecha com as próprias parcelas custa mais do que o erro que esconde.
    #
    # Cada ingrediente aparece pela parte que ela tem, pela parte que já comprou
    # e pela parte que falta comprar; as três somam a quantidade da receita.
    linhas = tuple(_linha(uso, divisor) for uso in avaliacao.usos) + tuple(
        _linha_de_compra(faltante, divisor) for faltante in avaliacao.faltantes
    )
    total = Dinheiro.zero()
    for linha in linhas:
        total = total + linha.custo

    return CMV(
        receita=receita.nome,
        linhas=linhas,
        total=total,
        incerteza_relativa=_incerteza_agregada(linhas, total),
        itens_a_gosto=avaliacao.a_gosto,
        rendimento_original=porcoes,
        opcionais_de_fora=avaliacao.opcionais_de_fora,
        rendimento_estimado=rendimento.texto if rendimento and rendimento.estimado else "",
    )


def _linha_de_compra(faltante: ItemFaltante, divisor: Decimal) -> LinhaCMV:
    """A compra complementar como linha da composição.

    `calcular` já recusou antes de chegar aqui se algum faltante estivesse sem
    cotação (`CustoIndeterminado`), então o `custo_estimado` existe. A asserção
    é para o verificador de tipos, não uma dúvida sobre o fluxo.
    """
    consumo = faltante.custo_no_prato
    assert consumo is not None
    por_porcao = consumo / divisor
    origem = faltante.derivacao or f"{consumo} da compra"
    premissa = f" ({faltante.premissa})" if faltante.premissa else ""
    return LinhaCMV(
        ingrediente=f"{faltante.nome} (comprar)",
        quantidade=faltante.quantidade_texto,
        custo=por_porcao,
        derivacao=f"{_por_porcao(origem, divisor)}{premissa}",
        # A cotação é um valor informado, não derivado da planilha: não há
        # normalização de unidade por trás dele para introduzir erro.
        incerteza=Decimal(0),
    )


def _linha(uso: UsoDeIngrediente, divisor: Decimal) -> LinhaCMV:
    """Converte um uso avaliado em linha de custo já escalada por porção."""
    nome = uso.rotulo or (
        uso.casamento.item.nome if uso.casamento.item else uso.casamento.texto_receita
    )
    return LinhaCMV(
        ingrediente=nome,
        quantidade=f"{_limpa(uso.quantidade.valor / divisor)} {uso.quantidade.dimensao.value}",
        custo=uso.custo / divisor,
        derivacao=_por_porcao(uso.derivacao, divisor),
        incerteza=uso.incerteza,
    )


def _por_porcao(conta: str, divisor: Decimal) -> str:
    """A conta da receita inteira, dividida pelas porções que ela rende.

    Sem a divisão, a tela mostrava "500 g × R$ 14,00/kg = R$ 7,00" ao lado de
    uma linha de R$ 1,75. O valor da porção não é repetido aqui: ele vai ao
    lado, já no centavo que fecha a soma com o total (`custos_exibidos`), e
    repeti-lo arriscaria um centavo de diferença entre a conta e a linha.
    """
    return conta if divisor == 1 else f"{conta} ÷ {_limpa(divisor)} porções"


def _incerteza_agregada(linhas: tuple[LinhaCMV, ...], total: Dinheiro) -> Decimal:
    """Média das incertezas ponderada pela participação de cada item no custo.

    Uma pitada de sal com ±15% de incerteza não deve contaminar o CMV de um
    prato dominado por carne medida em quilo.
    """
    if not linhas or total.valor == 0:
        return Decimal("0")
    acumulado = Decimal("0")
    for linha in linhas:
        peso = linha.custo.valor / total.valor
        acumulado += peso * linha.incerteza
    return acumulado


def _limpa(valor: Decimal) -> str:
    """Como se escreve no Brasil, com até quatro casas: "0,125", nunca "0.125"."""
    n = valor.normalize()
    if n == n.to_integral_value():
        return str(n.quantize(Decimal("1")))
    return f"{n.quantize(Decimal('0.0001')).normalize():f}".replace(".", ",")


__all__ = ["CMV", "LIMIAR_FAIXA", "LinhaCMV", "calcular"]
