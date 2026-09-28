"""Modelo canônico de receita.

Uma receita da internet chega como texto solto. Para virar CMV ela precisa
carregar três coisas que os sites quase sempre escondem:

**Rendimento.** "Lasanha que serve 6" e "lasanha" são a mesma página, mas o
delivery vende *uma* porção. Sem dividir pelo rendimento, o CMV sai 6 vezes
maior e o preço fica impraticável. É o erro silencioso mais caro da precificação
de cardápio.

**Exigência de equipamento e técnica.** Nunca declarada; sempre inferida do
modo de preparo. Aqui ela já chega como id do vocabulário controlado.

**Quantidade em medida culinária.** "1 xícara" não é uma unidade de compra.
A conversão para kg/L acontece no `mise.unidades`, com densidade e incerteza.

**Os três tempos que a receita declara**, separados como o schema.org os
publica: preparo (`prepTime`), cozimento (`cookTime`) e total (`totalTime`).
Juntar os três num número só fazia o portão comparar o tempo total, com as
esperas de geladeira e de descanso, com o tempo que ela tem por cozinhada. O
tempo que o portão compara é o dos passos (`mise.tempo`), e o de cozimento
declarado só vale quando os passos não dizem.

A fonte (`url`) é obrigatória quando a receita veio da web: o enunciado pede
pesquisa de receitas **reais**, e uma receita sem procedência não é verificável.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from mise.erros import QuantidadeInvalida, SemProcedencia
from mise.taxonomia import detectar, equipamento, tecnica

if TYPE_CHECKING:
    from collections.abc import Iterable

#: Termos que indicam quantidade não especificada.
A_GOSTO = ("a gosto", "q.b.", "quanto baste", "a olho", "o quanto precisar")


def _entendida_ao_guardar(linha: dict[str, Any]) -> bool:
    """Se a linha guardada foi entendida, com as regras de leitura de hoje.

    A receita guardada antes da distinção não tem o campo: a linha sem
    quantidade era "a gosto". A guardada antes da regra do tempero ("Sal",
    "Azeite" sem número) tem a linha marcada como não lida: com a regra, ela
    vale a gosto, sem precisar buscar a página de novo.
    """
    entendida = bool(linha.get("entendida", True))
    if entendida or linha.get("quantidade") is not None:
        return entendida
    from mise.temperos import so_tempero  # noqa: PLC0415

    return so_tempero(str(linha.get("texto_original") or linha.get("nome") or ""))


@dataclass(frozen=True, slots=True)
class IngredienteReceita:
    """Uma linha da lista de ingredientes, já interpretada.

    Sem quantidade há dois casos, e confundir os dois era um furo: a receita
    que diz "sal a gosto" escolheu não dar número (`a_gosto`), e a linha que a
    leitura não entendeu ("temperos de sua preferência") simplesmente não diz
    quanto (`nao_entendida`). A primeira entra na conta como "a gosto"; a
    segunda vira pergunta para ela, porque sumir com a linha seria fingir que
    a receita não pede aquilo.
    """

    texto_original: str
    """O que a receita escreveu, preservado para auditoria e para a Dona Maria conferir."""

    nome: str
    """O ingrediente isolado do texto, ainda não casado com a despensa."""

    quantidade: Decimal | None = None
    medida: str = ""
    observacao: str = ""
    opcional: bool = False
    #: A leitura entendeu a linha? Só faz diferença sem quantidade: `True` é o
    #: "a gosto" que a receita escreveu, `False` é a linha que não deu para ler.
    #: O padrão é `True` porque quem monta o ingrediente à mão diz a quantidade
    #: ou diz que é a gosto; a leitura da linha é que sabe quando não entendeu.
    entendida: bool = True
    #: O que ela respondeu a "A receita pede alcatra. É o seu miolo de alcatra?":
    #: o nome do item da despensa que ela confirmou, `""` quando ela disse que
    #: não é, e `None` enquanto ninguém perguntou. Vale só para esta receita.
    item_da_despensa: str | None = None
    #: Quanto a linha inteira pesa, em gramas, como ela disse: responde a "Não
    #: sei quanto pesa um peito de frango". Só vale quando a medida da linha não
    #: se converte sozinha (a peça sem peso conhecido, a colher sem densidade);
    #: a conta nunca troca por ele uma conversão que existe.
    peso_g: Decimal | None = None

    @property
    def a_gosto(self) -> bool:
        """Sem quantidade porque a receita diz que é a gosto: sal, pimenta, cheiro-verde.

        Custo desprezível, mas **declarado**: aparece na conta como "a gosto",
        em vez de sumir dela.
        """
        return self.quantidade is None and self.entendida

    @property
    def nao_entendida(self) -> bool:
        """Sem quantidade porque a leitura não entendeu a linha: vira pergunta, nunca "a gosto"."""
        return self.quantidade is None and not self.entendida

    def __post_init__(self) -> None:
        if self.quantidade is not None and self.quantidade < 0:
            raise QuantidadeInvalida(self.quantidade, f"ingrediente {self.nome!r}")
        if self.peso_g is not None and self.peso_g <= 0:
            raise QuantidadeInvalida(self.peso_g, f"peso de {self.nome!r} (em gramas)")

    def __str__(self) -> str:
        if self.nao_entendida:
            return self.texto_original or self.nome
        if self.a_gosto:
            return f"{self.nome} (a gosto)"
        return f"{_limpa(self.quantidade)} {self.medida} de {self.nome}".strip()


class Origem(StrEnum):
    """De onde a receita veio.

    Existe para tornar a procedência uma regra e não uma convenção. O §2.1 manda
    pesquisar receitas reais na internet, e uma receita apresentada como
    pesquisada sem endereço não é verificável: a Dona Maria não tem como conferir,
    e nós não temos como mostrar de onde tiramos as quantidades.
    """

    WEB = "web"
    INFORMADA_POR_ELA = "informada_por_ela"
    AUTORAL = "autoral"


@dataclass(frozen=True, slots=True)
class Receita:
    """Uma receita pronta para ser avaliada e custeada."""

    nome: str
    ingredientes: tuple[IngredienteReceita, ...]
    rendimento_porcoes: int = 1
    modo_preparo: tuple[str, ...] = ()
    equipamentos: frozenset[str] = field(default_factory=frozenset)
    tecnicas: frozenset[str] = field(default_factory=frozenset)
    #: Tempo de preparo declarado (o `prepTime`): a mão na massa antes do fogo.
    tempo_preparo_min: int | None = None
    url: str | None = None
    fonte: str | None = None
    origem: Origem = Origem.INFORMADA_POR_ELA
    #: Alguém disse quantas porções a receita rende? Falso quando o site não diz
    #: ou diz em grama, litro ou minuto: aí o portão pergunta em vez de dividir
    #: o custo por um número que ninguém informou.
    rendimento_informado: bool = True
    #: Tempo de cozimento declarado (o `cookTime`): fogo ou forno ligado. O portão
    #: usa quando os passos não dizem tempo nenhum.
    tempo_cozimento_min: int | None = None
    #: Tempo total declarado (o `totalTime`), com as esperas. Não é tempo de
    #: fogo: só serve para mostrar e para dizer que uma receita curta cabe.
    tempo_total_min: int | None = None
    #: A seção da página de cada passo do `modo_preparo`, na mesma ordem
    #: ("Massa", "Cobertura"), ou `None` no passo que a página não põe numa
    #: seção com nome. Vazio quando a página não divide o preparo em seções, e
    #: em toda receita guardada antes deste campo: aí a tela mostra a lista corrida.
    secoes_do_preparo: tuple[str | None, ...] = ()

    def __post_init__(self) -> None:
        if self.rendimento_porcoes < 1:
            raise QuantidadeInvalida(
                self.rendimento_porcoes, f"rendimento de {self.nome!r} (mínimo 1 porção)"
            )
        if not self.ingredientes:
            raise QuantidadeInvalida(0, f"receita {self.nome!r} sem ingredientes")
        for rotulo, minutos in (
            ("tempo de preparo", self.tempo_preparo_min),
            ("tempo de cozimento", self.tempo_cozimento_min),
            ("tempo total", self.tempo_total_min),
        ):
            if minutos is not None and minutos < 0:
                raise QuantidadeInvalida(minutos, f"{rotulo} de {self.nome!r} (em minutos)")
        # O vocabulário controlado é validado na fronteira, não no uso.
        for id_ in self.equipamentos:
            equipamento(id_)
        for id_ in self.tecnicas:
            tecnica(id_)
        # Procedência é invariante do tipo, não disciplina de quem constrói. Uma
        # receita da web sem endereço não chega a existir.
        if self.origem is Origem.WEB and not (self.url or "").strip():
            raise SemProcedencia(self.nome)

    def para_dict(self) -> dict[str, Any]:
        """A receita como JSON, para o dossiê guardar entre um turno e outro."""
        return {
            "nome": self.nome,
            "ingredientes": [
                {
                    "texto_original": i.texto_original,
                    "nome": i.nome,
                    "quantidade": str(i.quantidade) if i.quantidade is not None else None,
                    "medida": i.medida,
                    "observacao": i.observacao,
                    "opcional": i.opcional,
                    "entendida": i.entendida,
                    **(
                        {"item_da_despensa": i.item_da_despensa}
                        if i.item_da_despensa is not None
                        else {}
                    ),
                    **({"peso_g": str(i.peso_g)} if i.peso_g is not None else {}),
                }
                for i in self.ingredientes
            ],
            "rendimento_porcoes": self.rendimento_porcoes,
            "modo_preparo": list(self.modo_preparo),
            "equipamentos": sorted(self.equipamentos),
            "tecnicas": sorted(self.tecnicas),
            "tempo_preparo_min": self.tempo_preparo_min,
            "tempo_cozimento_min": self.tempo_cozimento_min,
            "tempo_total_min": self.tempo_total_min,
            "url": self.url,
            "fonte": self.fonte,
            "origem": self.origem.value,
            "rendimento_informado": self.rendimento_informado,
            # Só quando a página tem seções: a receita sem elas fica gravada igual.
            **(
                {"secoes_do_preparo": list(self.secoes_do_preparo)}
                if self.secoes_do_preparo
                else {}
            ),
        }

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> Receita:
        return cls(
            nome=dados["nome"],
            ingredientes=tuple(
                IngredienteReceita(
                    texto_original=i["texto_original"],
                    nome=i["nome"],
                    quantidade=Decimal(i["quantidade"]) if i["quantidade"] is not None else None,
                    medida=i["medida"],
                    observacao=i["observacao"],
                    opcional=i["opcional"],
                    entendida=_entendida_ao_guardar(i),
                    item_da_despensa=i.get("item_da_despensa"),
                    peso_g=Decimal(i["peso_g"]) if i.get("peso_g") is not None else None,
                )
                for i in dados["ingredientes"]
            ),
            rendimento_porcoes=dados["rendimento_porcoes"],
            modo_preparo=tuple(dados["modo_preparo"]),
            equipamentos=frozenset(dados["equipamentos"]),
            tecnicas=frozenset(dados["tecnicas"]),
            tempo_preparo_min=dados["tempo_preparo_min"],
            url=dados["url"],
            fonte=dados["fonte"],
            origem=Origem(dados["origem"]),
            rendimento_informado=dados.get("rendimento_informado", True),
            # Receita guardada antes dos tempos separados não tem estes campos.
            tempo_cozimento_min=dados.get("tempo_cozimento_min"),
            tempo_total_min=dados.get("tempo_total_min"),
            # Receita guardada antes das seções: a lista corrida, como era.
            secoes_do_preparo=tuple(dados.get("secoes_do_preparo", ())),
        )

    @property
    def secao_de_cada_passo(self) -> tuple[str | None, ...]:
        """A seção de cada passo, um por passo; `None` em todos quando não há seções.

        Seções que não batem com os passos (uma a mais ou a menos) não valem:
        título em cima do passo errado é pior do que título nenhum.
        """
        if len(self.secoes_do_preparo) != len(self.modo_preparo):
            return (None,) * len(self.modo_preparo)
        return self.secoes_do_preparo

    @property
    def tempo_declarado_min(self) -> int | None:
        """O tempo que a receita diz levar, para mostrar a ela: o total, se ela diz.

        Sem o total, preparo mais cozimento quando os dois vêm, senão o que vier.
        É o número do cartão ("leva 1 h"), nunca o que o portão compara.
        """
        if self.tempo_total_min is not None:
            return self.tempo_total_min
        if self.tempo_preparo_min is not None and self.tempo_cozimento_min is not None:
            return self.tempo_preparo_min + self.tempo_cozimento_min
        if self.tempo_cozimento_min is not None:
            return self.tempo_cozimento_min
        return self.tempo_preparo_min

    @property
    def tem_procedencia(self) -> bool:
        """Receita da web precisa de URL, senão não é verificável."""
        return bool(self.url)

    @property
    def citacao(self) -> str:
        """Como citar esta receita para a Dona Maria, em uma linha."""
        if self.origem is Origem.WEB:
            de_onde = self.fonte or (self.url or "").split("/")[2] if self.url else ""
            return f"{self.nome}, de {de_onde}" if de_onde else self.nome
        if self.origem is Origem.INFORMADA_POR_ELA:
            return f"{self.nome}, como a senhora me passou"
        return self.nome

    @property
    def ingredientes_quantificados(self) -> tuple[IngredienteReceita, ...]:
        return tuple(i for i in self.ingredientes if i.quantidade is not None)

    @property
    def ingredientes_a_gosto(self) -> tuple[IngredienteReceita, ...]:
        return tuple(i for i in self.ingredientes if i.a_gosto)

    @property
    def ingredientes_nao_entendidos(self) -> tuple[IngredienteReceita, ...]:
        """As linhas em que a leitura não achou quanto vai: cada uma vira pergunta."""
        return tuple(i for i in self.ingredientes if i.nao_entendida)

    def por_porcao(self) -> Receita:
        """Reescala a receita para **uma** porção.

        Divide toda quantidade pelo rendimento. Itens "a gosto" continuam a
        gosto. O rendimento resultante é 1, e reescalar de novo é inofensivo.
        """
        if self.rendimento_porcoes == 1:
            return self

        divisor = Decimal(self.rendimento_porcoes)
        return Receita(
            nome=self.nome,
            ingredientes=tuple(
                IngredienteReceita(
                    texto_original=i.texto_original,
                    nome=i.nome,
                    quantidade=None if i.quantidade is None else i.quantidade / divisor,
                    medida=i.medida,
                    observacao=i.observacao,
                    opcional=i.opcional,
                    entendida=i.entendida,
                    item_da_despensa=i.item_da_despensa,
                    peso_g=None if i.peso_g is None else i.peso_g / divisor,
                )
                for i in self.ingredientes
            ),
            rendimento_porcoes=1,
            modo_preparo=self.modo_preparo,
            equipamentos=self.equipamentos,
            tecnicas=self.tecnicas,
            tempo_preparo_min=self.tempo_preparo_min,
            url=self.url,
            fonte=self.fonte,
            tempo_cozimento_min=self.tempo_cozimento_min,
            tempo_total_min=self.tempo_total_min,
            secoes_do_preparo=self.secoes_do_preparo,
        )

    def com_exigencias_detectadas(self) -> Receita:
        """Completa equipamentos e técnicas varrendo o modo de preparo.

        A camada determinística pega o óbvio ("leve ao forno" → `forno`) de
        graça. O que escapar é trabalho do extrator estruturado, e o resultado
        dele passa pelo mesmo vocabulário.
        """
        texto = " ".join(
            (self.nome, *self.modo_preparo, *(i.texto_original for i in self.ingredientes))
        )
        achado = detectar(texto)
        # `replace` e não reconstrução campo a campo: listar os campos à mão faz
        # com que todo campo novo seja silenciosamente descartado aqui. Foi o que
        # aconteceu com `origem`: a receita saía da web e voltava marcada como
        # informada por ela, perdendo a procedência sem nenhum erro.
        return replace(
            self,
            equipamentos=self.equipamentos | achado.ids_equipamentos,
            tecnicas=self.tecnicas | achado.ids_tecnicas,
        )

    def __str__(self) -> str:
        origem = f" ({self.fonte})" if self.fonte else ""
        porcoes = "porção" if self.rendimento_porcoes == 1 else "porções"
        return f"{self.nome}{origem}, rende {self.rendimento_porcoes} {porcoes}"


def ingrediente(
    texto: str,
    nome: str,
    quantidade: Decimal | float | int | None = None,
    medida: str = "",
    *,
    observacao: str = "",
    opcional: bool = False,
    entendida: bool = True,
) -> IngredienteReceita:
    """Atalho de construção que normaliza o tipo da quantidade."""
    return IngredienteReceita(
        texto_original=texto,
        nome=nome,
        quantidade=None if quantidade is None else Decimal(str(quantidade)),
        medida=medida,
        observacao=observacao,
        opcional=opcional,
        entendida=entendida,
    )


def receita(
    nome: str,
    ingredientes: Iterable[IngredienteReceita],
    *,
    rendimento_porcoes: int = 1,
    modo_preparo: Iterable[str] = (),
    equipamentos: Iterable[str] = (),
    tecnicas: Iterable[str] = (),
    tempo_preparo_min: int | None = None,
    url: str | None = None,
    fonte: str | None = None,
    tempo_cozimento_min: int | None = None,
    tempo_total_min: int | None = None,
    secoes_do_preparo: Iterable[str | None] = (),
) -> Receita:
    """Constrói uma `Receita` e já infere exigências do modo de preparo."""
    return Receita(
        nome=nome,
        ingredientes=tuple(ingredientes),
        rendimento_porcoes=rendimento_porcoes,
        modo_preparo=tuple(modo_preparo),
        equipamentos=frozenset(equipamentos),
        tecnicas=frozenset(tecnicas),
        tempo_preparo_min=tempo_preparo_min,
        url=url,
        fonte=fonte,
        tempo_cozimento_min=tempo_cozimento_min,
        tempo_total_min=tempo_total_min,
        secoes_do_preparo=tuple(secoes_do_preparo),
    ).com_exigencias_detectadas()


def _limpa(valor: Decimal | None) -> str:
    if valor is None:
        return ""
    n = valor.normalize()
    return str(n.quantize(Decimal("1"))) if n == n.to_integral_value() else f"{n:f}"


__all__ = ["A_GOSTO", "IngredienteReceita", "Receita", "ingrediente", "receita"]
