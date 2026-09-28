"""Hierarquia de erros do `mise`.

Regra do projeto: nada de `except Exception` mudo. Todo modo de falha previsível
tem um tipo próprio, carrega o contexto necessário para a correção e sabe dizer
se é uma pergunta para a Dona Maria ou um defeito nosso.

A distinção que importa:

- `ErroDeDados`  -> a planilha não permite deduzir algo. A saída é **perguntar**.
- `ErroDeRegra`  -> alguém tentou violar uma regra de negócio. A saída é **recusar**.
- `ErroDeUso`    -> chamada malformada. A saída é **corrigir o chamador**.
"""

from __future__ import annotations

import re

from mise.genero import falar


def _reais(valor: float) -> str:
    """ "R$ 1.234,56": o dinheiro de uma mensagem, como ela lê (e como o guard-rail reconhece).

    Este módulo não importa `Dinheiro` (que importa daqui); a formatação é a mesma.
    """
    return "R$ " + f"{valor:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


class ErroMise(Exception):
    """Raiz de todos os erros do motor."""

    def __init__(self, mensagem: str, /, **contexto: object) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.contexto = contexto

    def __str__(self) -> str:
        if not self.contexto:
            return self.mensagem
        detalhes = " ".join(f"{k}={v!r}" for k, v in sorted(self.contexto.items()))
        return f"{self.mensagem} ({detalhes})"


# --------------------------------------------------------------------------- #
# Dados: a planilha não permite deduzir. Vira pergunta, nunca chute.
# --------------------------------------------------------------------------- #


class ErroDeDados(ErroMise):
    """A entrada é insuficiente para derivar a resposta com segurança."""

    #: Pergunta a ser feita à Dona Maria para destravar. Subclasses devem preencher.
    pergunta: str = ""


class MassaDesconhecida(ErroDeDados):
    """Item vendido por embalagem opaca ("1 un"), sem o peso ou o volume no rótulo.

    O caso real da planilha: `Cobertura de chocolate, 1 un, R$ 79,90`. Não há
    como derivar R$/kg. Dividir 79,90 por 1 e tratar como "1 kg" seria inventar.
    """

    def __init__(self, ingrediente: str, preco_total: float, unidade: str) -> None:
        nome = falar(ingrediente)
        super().__init__(
            f"a embalagem {nome.de()} não diz o peso nem o volume, então não dá para saber o "
            "custo por quilo ou por litro",
            ingrediente=ingrediente,
            preco_total=preco_total,
            unidade=unidade,
        )
        self.ingrediente = ingrediente
        self.preco_total = preco_total
        self.pergunta = (
            f"Dona Maria, quanto vem na embalagem {nome.de()} que a senhora comprou por "
            f"{_reais(preco_total)}? "
            "Se estiver escrito no rótulo (em gramas ou ml), me diz que eu calculo certinho."
        )


class PrecoDesconhecido(ErroDeDados):
    """Item que ela acrescentou sem dizer quanto pagou (o que já tinha em casa).

    Custo zero faria todo prato com ele parecer mais barato do que é. O custo
    fica desconhecido até ela dizer o preço, e a conta do prato pergunta.
    """

    def __init__(self, ingrediente: str) -> None:
        nome = falar(ingrediente)
        super().__init__(
            f"falta o preço {nome.de()}: sem ele, não dá para saber o custo",
            ingrediente=ingrediente,
        )
        self.ingrediente = ingrediente
        # Sem o gênero do nome, a frase vai sem artigo: "sobre trufa" seria capenga.
        assunto = f"sobre {nome.com_artigo()}" if nome.conhecido else f"falta o preço {nome.de()}"
        self.pergunta = (
            f"Dona Maria, {assunto}: quanto a senhora pagou, e por qual quantidade? "
            "Se não lembrar, o preço de hoje no mercado serve."
        )


#: O fim de toda pergunta de peso: ela diz em gramas, e a conta é do motor.
SE_SOUBER_EM_GRAMAS = "Se a senhora souber, em gramas, eu calculo."


def _falado(ingrediente: str) -> str:
    """O nome no meio da frase, sem o que está entre parênteses: "caldo de carne"."""
    sem_parenteses = re.sub(r"\s*\([^)]*\)", "", ingrediente)
    return falar(sem_parenteses.strip() or ingrediente).minusculo


def _cada_um(ingrediente: str) -> str:
    """ "um peito de frango", "uma cebola", "cada unidade de tahine": uma peça do ingrediente."""
    genero = falar(ingrediente).genero
    if genero is None or genero.plural:
        return f"cada unidade de {_falado(ingrediente)}"
    return f"{'uma' if genero.feminino else 'um'} {_falado(ingrediente)}"


class UnidadeNaoNormalizavel(ErroDeDados):
    """A unidade não casa com nenhum padrão conhecido nem pôde ser interpretada.

    A mensagem e a pergunta falam como ela fala: "não sei quanto pesa um peito
    de frango", e não "unidade '' de 'Peito de frango' não foi reconhecida".
    """

    def __init__(self, unidade: str, ingrediente: str | None = None) -> None:
        medida = " ".join(unidade.split())
        #: Uma peça do que se pesa, falada ("um peito de frango", "1 maço de
        #: salsinha"): é o que a pergunta pede em gramas. `None` quando nem o
        #: ingrediente se sabe, e aí um peso não resolve.
        self.o_que_pesa: str | None = None
        if ingrediente and not medida:
            self.o_que_pesa = _cada_um(ingrediente)
            mensagem = f"não sei quanto pesa {self.o_que_pesa}"
            pergunta = f"Não sei quanto pesa {self.o_que_pesa}. {SE_SOUBER_EM_GRAMAS}"
        elif ingrediente:
            self.o_que_pesa = f"1 {medida} de {_falado(ingrediente)}"
            mensagem = f"não sei quanto pesa {self.o_que_pesa}"
            pergunta = f"Não sei quanto pesa {self.o_que_pesa}. {SE_SOUBER_EM_GRAMAS}"
        else:
            mensagem = f"não entendi a medida “{medida}”" if medida else "não entendi a medida"
            pergunta = (
                f"{mensagem[:1].upper()}{mensagem[1:]}. "
                "Pode me dizer em gramas, quilos, litros ou unidades?"
            )
        super().__init__(mensagem, unidade=unidade, ingrediente=ingrediente)
        self.unidade = unidade
        self.ingrediente = ingrediente
        self.pergunta = pergunta


class DensidadeDesconhecida(ErroDeDados):
    """Medida de volume ("1 xícara") sem densidade conhecida para o ingrediente.

    Converter ml como se fosse g erra +89% em farinha de trigo. Preferimos
    perguntar a errar silenciosamente. E perguntar como gente: "Não sei quanto
    pesa uma colher de sopa de alcaparras", nunca "densidade" nem aspas de código.
    """

    def __init__(self, ingrediente: str, medida: str) -> None:
        from mise.unidades import medida_com_artigo  # noqa: PLC0415

        quanto = f"{medida_com_artigo(medida)} de {_falado(ingrediente)}"
        super().__init__(
            f"não sei quanto pesa {quanto}",
            ingrediente=ingrediente,
            medida=medida,
        )
        self.ingrediente = ingrediente
        self.medida = medida
        #: Uma medida do que se pesa, falada: "uma colher de sopa de alcaparras".
        self.o_que_pesa = quanto
        self.pergunta = f"Não sei quanto pesa {quanto}. {SE_SOUBER_EM_GRAMAS}"


class IngredienteDesconhecido(ErroDeDados):
    """O texto da receita não casou com nenhum item da despensa com confiança."""

    def __init__(self, texto: str, melhor_palpite: str | None = None, score: float = 0.0) -> None:
        super().__init__(
            f"ingrediente {texto!r} não foi encontrado na despensa com confiança suficiente",
            texto=texto,
            melhor_palpite=melhor_palpite,
            score=score,
        )
        self.texto = texto
        self.melhor_palpite = melhor_palpite
        self.score = score


# --------------------------------------------------------------------------- #
# Regra: tentativa de violar uma invariante de negócio. Recusa.
# --------------------------------------------------------------------------- #


class ErroDeRegra(ErroMise):
    """Uma regra de negócio inegociável foi violada."""


class ContaNaoConfere(ErroDeRegra):
    """O auditor independente refez a conta e chegou a outro número.

    O preço não segue para a Dona Maria: dois códigos que não compartilham
    nada discordaram, e mostrar qualquer um dos dois seria apostar.
    """

    def __init__(self, prato: str, parecer: dict[str, object]) -> None:
        super().__init__(
            f"a conta de {prato!r} não confere com a auditoria independente",
            divergencias=parecer.get("divergencias"),
            observacao=parecer.get("observacao"),
        )


class SemProcedencia(ErroDeRegra):
    """Receita declarada como vinda da web, sem endereço que a sustente.

    É recusa de regra, não pedido de dado: quem construiu a receita disse de onde
    ela veio e não disse onde. O conserto é de quem chamou: ou informa a URL, ou
    declara outra origem.
    """

    def __init__(self, nome: str) -> None:
        super().__init__(
            f"a receita {nome!r} foi declarada como pesquisada na web, mas não trouxe "
            "o endereço. Sem ele a senhora não tem como conferir de onde vieram as "
            "quantidades.",
            receita=nome,
        )
        self.receita_nome = nome


class ViabilidadeNaoConfirmada(ErroDeRegra):
    """Tentativa de precificar um prato cuja viabilidade não foi confirmada.

    Esta é a garantia central do desafio: *"o agente não pode deixar ela comprar
    ingredientes e descobrir depois que não consegue cozinhar"*. Por isso o
    bloqueio é código, não instrução de prompt.
    """

    def __init__(self, receita: str, veredito: str, pendencias: tuple[str, ...] = ()) -> None:
        super().__init__(
            f"não é possível calcular o CMV de {receita!r}: a viabilidade está {veredito!r}, "
            "e só calculamos custo de prato confirmado como APTO",
            receita=receita,
            veredito=veredito,
            pendencias=pendencias,
        )
        self.receita = receita
        self.veredito = veredito
        self.pendencias = pendencias


class CozinhaNaoConfirmada(ErroDeRegra):
    """Aceite ou compra de um prato que se apoia no que toda cozinha tem, sem ela confirmar.

    O portão deixa passar como suposto o que qualquer cozinha tem (fogão, panela
    funda, refogar): perguntar item por item gastaria a paciência dela. Mas
    suposto não é certeza, e o §2.2 pede certeza antes do aceite e da compra.
    A recusa traz a pergunta, uma só, com tudo o que falta confirmar, e ela
    responde num toque. `itens` são os ids, na ordem da pergunta.
    """

    def __init__(
        self, receita: str, pergunta: str, itens: tuple[str, ...], receita_id: str = ""
    ) -> None:
        super().__init__(
            f"antes de seguir com {receita}, falta a senhora confirmar o que toda cozinha "
            "tem e esta receita usa",
            receita=receita,
            receita_id=receita_id,
            confirmar=", ".join(itens),
        )
        self.receita = receita
        self.receita_id = receita_id
        self.itens = itens
        self.pergunta = pergunta
        self.orientacao = (
            "Faça esta pergunta a ela, numa pergunta só. Se ela confirmar, grave com "
            "registrar_resposta(tipo='cozinha', campo=<receita_id>, resposta='tem') e tente "
            "de novo; o item que ela não tiver vai com registrar_resposta(tipo='equipamento' "
            "ou 'tecnica', campo=<id>, resposta='nao_tem')."
        )


class CustoIndeterminado(ErroDeRegra):
    """Um ou mais ingredientes não têm custo confiável; o CMV seria ficção."""

    def __init__(self, receita: str, ingredientes: tuple[str, ...]) -> None:
        quantos = "1 ingrediente" if len(ingredientes) == 1 else f"{len(ingredientes)} ingredientes"
        super().__init__(
            f"o CMV de {receita!r} depende de {quantos} sem custo "
            "confiável; um número aproximado aqui vira decisão de preço errada",
            receita=receita,
            ingredientes=ingredientes,
        )
        self.receita = receita
        self.ingredientes = ingredientes


class OrcamentoExcedido(ErroDeRegra):
    """A compra complementar não cabe no orçamento restante."""

    def __init__(self, necessario: float, disponivel: float) -> None:
        super().__init__(
            f"a compra exige {_reais(necessario)} e restam {_reais(disponivel)} do orçamento",
            necessario=necessario,
            disponivel=disponivel,
        )
        self.necessario = necessario
        self.disponivel = disponivel
        self.faltam = necessario - disponivel


# --------------------------------------------------------------------------- #
# Uso: o chamador errou. Corrigir o código.
# --------------------------------------------------------------------------- #


class ErroDeUso(ErroMise):
    """Chamada malformada: defeito de programação, não de dado."""


class Ausente(ErroDeUso):
    """Pediram algo que não existe: um item da despensa, uma receita, uma conversa.

    Na API da tela vira a categoria `ausente`, com HTTP 404, e a tela mostra
    "não encontrado" em vez de um erro. Na conversa continua sendo erro de uso:
    quem chamou apontou para uma coisa que não está lá.
    """


class PlanilhaInvalida(ErroDeUso):
    """O arquivo não tem a estrutura esperada (abas/colunas)."""

    def __init__(self, motivo: str, caminho: str | None = None) -> None:
        super().__init__(f"planilha inválida: {motivo}", motivo=motivo, caminho=caminho)
        self.motivo = motivo
        self.caminho = caminho


class VocabularioDesconhecido(ErroDeUso):
    """Id fora do vocabulário controlado de equipamentos ou técnicas.

    Acontece na prática: o modelo inventa `"forno_eletrico_grande"` ou
    `"fazer_bechamel"`. Estourar `KeyError` aqui derruba a ferramenta e o
    agente não descobre o que fazer. Devolvemos o erro com os ids parecidos,
    para ele se corrigir sozinho na próxima tentativa.
    """

    def __init__(self, especie: str, id_: str, conhecidos: tuple[str, ...] = ()) -> None:
        proximos = _parecidos(id_, conhecidos)
        dica = f"; você quis dizer {' ou '.join(repr(p) for p in proximos)}?" if proximos else ""
        super().__init__(
            f"{especie} {id_!r} não existe no vocabulário controlado "
            f"({len(conhecidos)} conhecidos){dica}",
            especie=especie,
            id=id_,
            sugestoes=proximos,
        )
        self.especie = especie
        self.id = id_
        self.sugestoes = proximos


def _parecidos(alvo: str, candidatos: tuple[str, ...], limite: int = 3) -> tuple[str, ...]:
    """Ids que compartilham prefixo ou palavra com o alvo."""
    partes = set(alvo.lower().split("_"))
    pontuados = [
        (len(partes & set(c.split("_"))), c)
        for c in candidatos
        if partes & set(c.split("_")) or c.startswith(alvo[:4])
    ]
    return tuple(c for _, c in sorted(pontuados, reverse=True)[:limite])


class QuantidadeInvalida(ErroDeUso):
    """Quantidade negativa, nula onde não pode ser, ou não-finita."""

    def __init__(self, valor: object, contexto: str = "") -> None:
        sufixo = f" em {contexto}" if contexto else ""
        super().__init__(f"quantidade inválida {valor!r}{sufixo}", valor=valor, contexto=contexto)
        self.valor = valor


class UnidadesIncompativeis(ErroDeUso):
    """Tentativa de somar ou comparar grandezas de dimensões diferentes."""

    def __init__(self, esquerda: str, direita: str) -> None:
        super().__init__(
            f"não é possível combinar {esquerda} com {direita}: dimensões diferentes",
            esquerda=esquerda,
            direita=direita,
        )
        self.esquerda = esquerda
        self.direita = direita
