"""O portão de viabilidade: a garantia central do desafio.

O enunciado é explícito: *"o agente não pode deixar ela comprar ingredientes e
descobrir depois que não consegue cozinhar"*. Isso não é uma sugestão de
comportamento, é uma **propriedade de segurança**. E propriedade de segurança
que depende de o modelo lembrar de verificar não é propriedade nenhuma.

Por isso o portão é código. `mise.cmv.calcular` recusa qualquer receita cujo
veredito aqui não seja apto. Não existe caminho no sistema que precifique um
prato não verificado, porque o caminho não foi escrito.

Cinco checagens independentes, cada uma produzindo evidência:

    ingredientes · equipamentos · técnicas · operação · gosto

As quatro primeiras dizem se ela consegue fazer; a do gosto diz se ela quer.

E quatro vereditos possíveis:

    APTO             ela consegue produzir hoje, com o que tem
    APTO_COM_COMPRA  consegue, se comprar o que falta, e cabe no orçamento
    FALTA_INFO       ainda não dá para dizer; estas são as perguntas
    BLOQUEADO        não consegue, e nenhuma informação nova muda isso

A combinação é **monótona**: `BLOQUEADO` vence `FALTA_INFO`, porque quando já
se sabe que é impossível, continuar perguntando é desrespeito com o tempo dela.
E informação nova nunca converte `BLOQUEADO` em `APTO` sem mudança de perfil.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING, Final

from mise.casamento import Casamento, Estrategia, casar, casar_confirmado, motivo_do_sinonimo
from mise.compras import (
    Comprado,
    Cotacao,
    Medida,
    buscar,
    e_liquido,
    medida,
    precificar_falta,
)
from mise.dinheiro import Dinheiro
from mise.erros import (
    DensidadeDesconhecida,
    ErroDeDados,
    MassaDesconhecida,
    PrecoDesconhecido,
    UnidadeNaoNormalizavel,
)
from mise.genero import falar
from mise.passos import (
    minimo_pelos_passos,
    minutos_ativos,
    minutos_com_panelas_juntas,
    minutos_no_fogo,
    onde_corre,
    passos_com_frio,
    passos_com_outra_panela,
    quais_passos,
)
from mise.perfil import (
    PERGUNTAS_OPERACIONAIS,
    Gosto,
    PerfilCozinha,
    Posse,
    RestricoesOperacionais,
    horas_texto,
)
from mise.receita import Origem
from mise.taxonomia import detectar, equipamento, tecnica
from mise.tempo import MinutosAtivos, OrigemDoTempo
from mise.unidades import (
    Dimensao,
    Quantidade,
    _medida_escrita,
    classificar_medida,
    converter_medida,
    converter_medida_para_volume,
    medida_de_referencia,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mise.despensa import Despensa, Ingrediente
    from mise.receita import IngredienteReceita, Receita
    from mise.referencias import PrecoDeReferencia, PrecosDeReferencia
    from mise.unidades import MedidaDeReferencia


class Veredito(IntEnum):
    """Ordenado por severidade: o pior dos quatro é o que vale no fim."""

    APTO = 0
    APTO_COM_COMPRA = 1
    FALTA_INFO = 2
    BLOQUEADO = 3

    @property
    def permite_precificar(self) -> bool:
        """Só prato verificado vira preço."""
        return self in (Veredito.APTO, Veredito.APTO_COM_COMPRA)

    @property
    def rotulo(self) -> str:
        return {
            Veredito.APTO: "APTO",
            Veredito.APTO_COM_COMPRA: "APTO COM COMPRA",
            Veredito.FALTA_INFO: "FALTA INFO",
            Veredito.BLOQUEADO: "BLOQUEADO",
        }[self]

    @property
    def rotulo_para_ela(self) -> str:
        """O que a tela mostra: o `rotulo` é valor técnico e não chega a ela."""
        return {
            Veredito.APTO: "Dá pra fazer",
            Veredito.APTO_COM_COMPRA: "Dá, comprando",
            Veredito.FALTA_INFO: "Falta saber",
            Veredito.BLOQUEADO: "Não dá",
        }[self]


class TipoRestricao(IntEnum):
    INGREDIENTE = 1
    EQUIPAMENTO = 2
    TECNICA = 3
    OPERACIONAL = 4
    GOSTO = 5


@dataclass(frozen=True, slots=True)
class Impedimento:
    """Algo que impede a produção, com a evidência que o sustenta."""

    tipo: TipoRestricao
    id: str
    descricao: str
    evidencia: str = ""

    def __str__(self) -> str:
        return self.descricao


class AssuntoDaPergunta(StrEnum):
    """Do que a pergunta trata, para a tela saber para onde a resposta vai sem ler o texto.

    `tipo` continua dizendo a quem a resposta pertence (a cozinha, o gosto, o
    ingrediente); o assunto diz qual informação falta.

    À Dona Maria só se pergunta gosto, equipamento, técnica e limite da rotina
    (`EQUIPAMENTO`, `TECNICA`, `ROTINA`, `GOSTO`, e o `MODO_PREPARO` da receita
    que ela mesma ditou). Os outros assuntos nunca viram pergunta: são a forma
    do `editar` de um valor que a plataforma estabeleceu com fonte (a quantidade
    que a receita não diz, o preço de referência, o peso de uma medida, o item
    parecido que ficou como compra, o tempo no fogo), para ela corrigir quando
    quiser, pelo mesmo caminho de resposta.
    """

    LINHA_NAO_LIDA = "linha_nao_lida"
    """Uma linha de ingrediente que a leitura não entendeu: quanto vai."""
    PRECO_DE_COMPRA = "preco_de_compra"
    """O preço do que falta comprar, e por qual quantidade."""
    PRECO_DA_DESPENSA = "preco_da_despensa"
    """Quanto ela pagou num item da despensa."""
    PESO_DA_EMBALAGEM = "peso_da_embalagem"
    """Quanto vem na embalagem de um item da despensa."""
    MEDIDA = "medida"
    """Quanto dá em gramas uma medida da receita que não se converte sozinha."""
    MESMO_INGREDIENTE = "mesmo_ingrediente"
    """Se o que a receita pede é o item parecido da despensa dela ("É o seu miolo de alcatra?")."""
    INGREDIENTE = "ingrediente"
    """Outra dúvida sobre um ingrediente."""
    RENDIMENTO = "rendimento"
    """Quantas porções a receita rende."""
    TEMPO_COZIMENTO = "tempo_cozimento"
    """Quantos minutos a receita fica no fogo, no forno ou num aparelho."""
    MODO_PREPARO = "modo_preparo"
    """Como ela faz a receita, que chegou sem o modo de preparo."""
    EQUIPAMENTO = "equipamento"
    TECNICA = "tecnica"
    ROTINA = "rotina"
    """Um limite da rotina da cozinha: bocas, tempo por cozinhada, gás, geladeira."""
    GOSTO = "gosto"


@dataclass(frozen=True, slots=True)
class PesoPedido:
    """O que a pergunta de medida pede quando um peso em gramas a responde.

    A despensa conta o item em quilo e a medida da linha não se converte
    sozinha: "1 peito" (a peça sem peso conhecido), "2 colheres de sopa de
    alcaparras" (a colher sem densidade). A pergunta pede o peso de uma
    unidade; ela pode dizer o da linha inteira.
    """

    quantidade: Decimal
    """Quanto a linha pede, na medida dela: 1 (peito), 2 (colheres de sopa)."""
    medida: str
    """A medida da linha, como a receita escreve; vazia quando a linha conta peças."""
    uma: str
    """Uma unidade do que se pesa, falada: "um peito de frango", "uma colher de sopa de sal"."""


@dataclass(frozen=True, slots=True)
class Pergunta:
    """Uma informação que falta, formulada para ser dita à Dona Maria."""

    tipo: TipoRestricao
    campo: str
    texto: str
    motivo: str = ""
    """Por que estamos perguntando: o agente usa para não soar interrogatório."""
    assunto: AssuntoDaPergunta | None = None
    """Do que a pergunta trata; sem ele, sai do `tipo` e do `campo` (`assunto_da`)."""
    compras: tuple[ItemFaltante, ...] = ()
    """No preço do que falta comprar: cada ingrediente que falta, com quanto falta."""
    peso: PesoPedido | None = None
    """Na pergunta de medida que um peso responde: o que se pesa (`campo` é o texto da linha)."""

    def __str__(self) -> str:
        return self.texto


def assunto_da(pergunta: Pergunta) -> AssuntoDaPergunta:
    """O assunto da pergunta: o que ela diz de si, ou o que o tipo e o campo dizem."""
    if pergunta.assunto is not None:
        return pergunta.assunto
    pelo_campo = {
        (TipoRestricao.EQUIPAMENTO, "modo_preparo"): AssuntoDaPergunta.MODO_PREPARO,
        (TipoRestricao.OPERACIONAL, "rendimento_porcoes"): AssuntoDaPergunta.RENDIMENTO,
        (TipoRestricao.OPERACIONAL, CAMPO_DO_TEMPO_DA_RECEITA): AssuntoDaPergunta.TEMPO_COZIMENTO,
    }
    pelo_tipo = {
        TipoRestricao.EQUIPAMENTO: AssuntoDaPergunta.EQUIPAMENTO,
        TipoRestricao.TECNICA: AssuntoDaPergunta.TECNICA,
        TipoRestricao.OPERACIONAL: AssuntoDaPergunta.ROTINA,
        TipoRestricao.GOSTO: AssuntoDaPergunta.GOSTO,
        TipoRestricao.INGREDIENTE: AssuntoDaPergunta.INGREDIENTE,
    }
    return pelo_campo.get((pergunta.tipo, pergunta.campo)) or pelo_tipo[pergunta.tipo]


@dataclass(frozen=True, slots=True)
class Aviso:
    """Algo que não impede o prato, mas que ela precisa saber antes de decidir.

    Não muda o veredito: com uma boca só, a receita de duas panelas continua
    dando, só leva mais tempo. `tipo` diz do que é o aviso (`bocas`), para a
    tela escolher como mostrar e apontar onde isso se muda na cozinha dela.
    """

    tipo: str
    texto: str

    def __str__(self) -> str:
        return self.texto


@dataclass(frozen=True, slots=True)
class ItemFaltante:
    """Um ingrediente que a receita pede e a despensa não tem, ou não tem o bastante.

    `custo_estimado` é o desembolso: o que ela paga no mercado, comparado com o
    orçamento. `custo_no_prato` é o consumo: o que o prato gasta do que falta,
    e é o que entra no CMV. `parcial` diz que ela tem parte em casa; essa parte
    já está numa linha de uso, e aqui fica só o que falta.
    """

    nome: str
    quantidade_texto: str
    custo_estimado: Dinheiro | None = None
    parcial: bool = False
    #: Quanto o prato consome do que falta. `None` quando é igual ao desembolso.
    consumo: Dinheiro | None = None
    derivacao: str = ""
    #: Suposição por trás do número, para o agente confirmar com ela.
    premissa: str = ""
    #: De onde veio o preço: a cotação (`informado_por_ela`, `pesquisado_na_web`,
    #: `estimado`) ou `planilha`, quando a falta foi reposta ao preço que ela pagou.
    origem_do_preco: str = ""
    #: Quanto falta, medido ("240 ml", "1 lata"); `None` quando a receita não diz.
    falta: Medida | None = None
    #: O preço de referência que cotou a compra, quando ela ainda não disse o
    #: dela: é referência, com a página de onde saiu, e ela pode corrigir.
    referencia: PrecoDeReferencia | None = None

    @property
    def custo_conhecido(self) -> bool:
        return self.custo_estimado is not None

    @property
    def custo_no_prato(self) -> Dinheiro | None:
        """O que entra no CMV: o consumo, não o pacote inteiro que ela compra."""
        return self.consumo if self.consumo is not None else self.custo_estimado


@dataclass(frozen=True, slots=True)
class UsoDeIngrediente:
    """Um ingrediente da receita já casado, convertido e custeado."""

    casamento: Casamento
    quantidade: Quantidade
    custo: Dinheiro
    incerteza: Decimal
    derivacao: str
    #: Nome da linha quando não é o do item da despensa ("Alcatra (comprado)").
    rotulo: str = ""


@dataclass(slots=True)
class Checagem:
    """Resultado de uma das cinco checagens."""

    nome: str
    veredito: Veredito = Veredito.APTO
    impedimentos: list[Impedimento] = field(default_factory=list)
    perguntas: list[Pergunta] = field(default_factory=list)
    avisos: list[Aviso] = field(default_factory=list)

    def bloquear(self, imp: Impedimento) -> None:
        self.impedimentos.append(imp)
        self.veredito = max(self.veredito, Veredito.BLOQUEADO)

    def perguntar(self, p: Pergunta) -> None:
        self.perguntas.append(p)
        self.veredito = max(self.veredito, Veredito.FALTA_INFO)

    def avisar(self, aviso: Aviso) -> None:
        """Guarda o aviso sem mexer no veredito."""
        self.avisos.append(aviso)


@dataclass(slots=True)
class Avaliacao:
    """O parecer completo sobre uma receita."""

    receita_nome: str
    veredito: Veredito
    checagens: tuple[Checagem, ...]
    usos: tuple[UsoDeIngrediente, ...] = ()
    faltantes: tuple[ItemFaltante, ...] = ()
    a_gosto: tuple[str, ...] = ()
    orcamento_restante: Dinheiro | None = None
    """O que restava dos complementos quando a compra foi conferida."""
    rendimento: RendimentoDoPrato | None = None
    """Quantas porções a receita rende: a que ela diz, ou a estimativa (`estimar_rendimento`).

    Nunca é pergunta: sem o rendimento na página, a plataforma estima pelo peso
    dos ingredientes e pelo peso de uma porção (uma premissa que ela muda), diz
    que é estimativa, e ela corrige na receita.
    """

    @property
    def impedimentos(self) -> tuple[Impedimento, ...]:
        return tuple(i for c in self.checagens for i in c.impedimentos)

    @property
    def perguntas(self) -> tuple[Pergunta, ...]:
        return tuple(p for c in self.checagens for p in c.perguntas)

    @property
    def avisos(self) -> tuple[Aviso, ...]:
        """O que ela precisa saber e não impede o prato (uma boca só, por exemplo)."""
        return tuple(a for c in self.checagens for a in c.avisos)

    @property
    def permite_precificar(self) -> bool:
        return self.veredito.permite_precificar

    # -- a cozinha sem o gosto, e o ajuste de cada ingrediente --------------- #

    @property
    def veredito_da_cozinha(self) -> Veredito:
        """A conferência sem o gosto: despensa, equipamento, técnica e rotina.

        É o que decide se a receita aparece na grade como possível. Com o gosto
        dentro, toda receita ficava em "falta saber" até ela dizer se gosta de
        cada uma; o preço e o aceite continuam exigindo o gosto (`veredito`).
        """
        return max((c.veredito for c in self.checagens if c.nome != "gosto"), default=Veredito.APTO)

    @property
    def perguntas_da_cozinha(self) -> tuple[Pergunta, ...]:
        """As perguntas da conferência sem a do gosto, na ordem das checagens."""
        return tuple(p for c in self.checagens if c.nome != "gosto" for p in c.perguntas)

    @property
    def impedimentos_da_cozinha(self) -> tuple[Impedimento, ...]:
        """O que impede o prato fora o gosto e o impedimento que ela mesma apontou."""
        return tuple(i for c in self.checagens if c.nome != "gosto" for i in c.impedimentos)

    @property
    def ajustes(self) -> tuple[AjusteDoIngrediente, ...]:
        """O ajuste de cada linha da receita à despensa (`checar_ingredientes`)."""
        for checagem in self.checagens:
            if isinstance(checagem, ChecagemDeIngredientes):
                return tuple(checagem.ajustes)
        return ()

    @property
    def opcionais_de_fora(self) -> tuple[str, ...]:
        """Os opcionais que ficaram de fora da conta e da compra, porque ela não tem."""
        return tuple(
            a.ingrediente.nome for a in self.ajustes if a.situacao is SituacaoDoIngrediente.OPCIONAL
        )

    @property
    def pode_comprar(self) -> bool:
        """Ela já pode ir ao mercado por este prato?

        Só quando tudo que não é ingrediente está confirmado: equipamento,
        técnica, rotina e gosto. É a regra do §2.2 escrita como código: ela não
        pode comprar ingrediente e descobrir depois que não consegue cozinhar.
        """
        return all(
            c.veredito is Veredito.APTO for c in self.checagens if c.nome != "ingredientes"
        ) and all(
            c.veredito is not Veredito.BLOQUEADO or _so_falta_o_preco(c)
            for c in self.checagens
            if c.nome == "ingredientes"
        )

    @property
    def custo_das_compras(self) -> Dinheiro | None:
        """Total do que falta comprar. `None` se algum preço é desconhecido."""
        if not self.faltantes:
            return Dinheiro.zero()
        if any(not f.custo_conhecido for f in self.faltantes):
            return None
        total = Dinheiro.zero()
        for f in self.faltantes:
            assert f.custo_estimado is not None
            total = total + f.custo_estimado
        return total

    def resumo(self) -> str:
        """O veredito dito para ela: a tela mostra isto, e o agente lê.

        O nome do veredito (`APTO`, `FALTA INFO`) é vocabulário do sistema e
        fica no campo `veredito`; aqui vão as palavras que ela vê na tela.
        """
        if self.veredito is Veredito.BLOQUEADO:
            motivos = "; ".join(str(i) for i in self.impedimentos)
            return f"{self.receita_nome}: esse não dá. {motivos[:1].upper()}{motivos[1:]}"
        if self.veredito is Veredito.FALTA_INFO:
            n = len(self.perguntas)
            coisas = "1 coisa" if n == 1 else f"{n} coisas"
            return f"{self.receita_nome}: antes de decidir, preciso saber {coisas}"
        if self.veredito is Veredito.APTO_COM_COMPRA:
            custo = self.custo_das_compras
            n = len(self.faltantes)
            itens = "1 item" if n == 1 else f"{n} itens"
            quanto = f", {custo} no total" if custo else ""
            # APTO COM COMPRA só existe quando a compra cabe: dizer isso é o §2.3
            # inteiro, e sem esta frase o agente às vezes esquecia os R$ 80.
            cabe = (
                f"; cabe nos {self.orcamento_restante} que restam do orçamento"
                if custo and self.orcamento_restante is not None
                else ""
            )
            return f"{self.receita_nome}: dá, comprando {itens}{quanto}{cabe}"
        return f"{self.receita_nome}: dá pra fazer hoje, com o que a senhora tem"


def _so_falta_o_preco(checagem: Checagem) -> bool:
    """Os ingredientes só não fecham porque um preço não se achou: comprar diz o preço."""
    return bool(checagem.impedimentos) and all(i.id == SEM_PRECO for i in checagem.impedimentos)


# --------------------------------------------------------------------------- #
# As cinco checagens
# --------------------------------------------------------------------------- #


def checar_equipamentos(receita: Receita, perfil: PerfilCozinha) -> Checagem:
    """Ela tem com o que cozinhar isso?

    Tudo que a receita pede é conferido, inclusive o que qualquer cozinha tem
    (fogão, panela, geladeira). O pressuposto passa como suposto enquanto ela
    não disser nada; o "não tenho" dela bloqueia com o motivo, e o "não sei"
    vira pergunta. Pular o pressuposto deixava a receita de fogão passar com
    ela dizendo que não tem fogão.
    """
    checagem = Checagem("equipamentos")
    for id_ in sorted(receita.equipamentos):
        equip = equipamento(id_)
        posse, _ = perfil.tem_equipamento_ou_substituto(id_)

        if posse is Posse.TEM:
            continue
        if posse is Posse.NAO_TEM:
            alternativas = ", ".join(equipamento(s).nome for s in equip.substitutos)
            extra = f" (nem {alternativas}, que resolveriam)" if alternativas else ""
            checagem.bloquear(
                Impedimento(
                    TipoRestricao.EQUIPAMENTO,
                    id_,
                    f"a receita precisa de {equip.nome.lower()} e a senhora não tem{extra}",
                )
            )
        elif perfil.tem_equipamento(id_) is Posse.NAO_TEM:
            # Ela já disse que não tem. Perguntar de novo seria não ter ouvido;
            # a pergunta útil é pelo substituto que ainda ninguém perguntou.
            candidato = next(
                s for s in equip.substitutos if perfil.tem_equipamento(s) is Posse.DESCONHECIDO
            )
            alternativo = equipamento(candidato)
            checagem.perguntar(
                Pergunta(
                    TipoRestricao.EQUIPAMENTO,
                    candidato,
                    f"Sem {equip.nome.lower()}, {alternativo.nome.lower()} resolve esta receita. "
                    f"A senhora tem {alternativo.nome.lower()}?",
                    motivo=f"{receita.nome} precisa de {equip.nome.lower()} ou de um substituto",
                )
            )
        else:
            checagem.perguntar(
                Pergunta(
                    TipoRestricao.EQUIPAMENTO,
                    id_,
                    equip.pergunta_para_ela(),
                    motivo=f"{receita.nome} precisa de {equip.nome.lower()}",
                )
            )

    if not receita.modo_preparo and not receita.equipamentos:
        # Sem preparo não há equipamento a conferir, e "nada a conferir" não é
        # "pode fazer": um bolo colado só com a lista de ingredientes passava
        # como apto sem ninguém perguntar do forno. Só a receita que ela ditou
        # pergunta como ela faz; a da internet sem o preparo fica de fora.
        if receita.origem is Origem.WEB:
            checagem.bloquear(
                Impedimento(
                    TipoRestricao.EQUIPAMENTO,
                    "modo_preparo",
                    "a página não traz o modo de preparo, e sem ele não dá para conferir a cozinha",
                    evidencia="a página da receita",
                )
            )
            return checagem
        checagem.perguntar(
            Pergunta(
                TipoRestricao.EQUIPAMENTO,
                "modo_preparo",
                f"Como a senhora faz {receita.nome.lower()}? Vai ao forno, é de panela, "
                "de fritar? Me conta o passo a passo que eu confiro se a cozinha dá conta.",
                motivo="sem o modo de preparo não dá para saber que equipamento o prato pede",
            )
        )
    return checagem


def checar_tecnicas(receita: Receita, perfil: PerfilCozinha) -> Checagem:
    """Ela sabe fazer isso?

    "Não faço" dito por ela bloqueia. Dá para aprender, mas decidir por ela que
    vai aprender a tempo do cardápio seria pior: quem muda a resposta na tela da
    cozinha, se quiser tentar, é ela, e aí o prato volta. Técnica de que ninguém
    falou vira pergunta. O que qualquer cozinheira faz (refogar, fritar) passa
    como suposto enquanto ela não disser o contrário; o "não faço" dela também
    bloqueia essas, e o "não sei" também vira pergunta.
    """
    checagem = Checagem("tecnicas")
    for id_ in sorted(receita.tecnicas):
        tec = tecnica(id_)
        posse = perfil.domina_tecnica(id_)

        if posse is Posse.TEM:
            continue
        if posse is Posse.NAO_TEM:
            checagem.bloquear(
                Impedimento(
                    TipoRestricao.TECNICA,
                    id_,
                    f"a receita pede {tec.nome.lower()}, que a senhora disse não fazer",
                )
            )
        else:
            checagem.perguntar(
                Pergunta(
                    TipoRestricao.TECNICA,
                    id_,
                    tec.pergunta_para_ela(),
                    motivo=f"{receita.nome} pede {tec.nome.lower()}",
                )
            )
    return checagem


#: Aparelhos que puxam corrente o bastante para disputar o mesmo disjuntor.
#: Fogão a gás não entra: ele não consome energia elétrica relevante.
APARELHOS_DE_ALTA_POTENCIA: Final[frozenset[str]] = frozenset(
    {
        "forno_eletrico",
        "air_fryer",
        "microondas",
        "batedeira",
        "liquidificador",
        "processador",
        "mixer",
        "chapa",
        "cilindro",
    }
)

#: A partir de dois aparelhos de alta potência a pergunta sobre energia passa a
#: valer. Com um só não há disputa de disjuntor e perguntar seria ruído.
APARELHOS_QUE_DISPUTAM_DISJUNTOR: Final = 2

#: Equipamentos que indicam que o preparo precisa ocupar espaço frio.
EQUIPAMENTOS_DE_FRIO: Final[frozenset[str]] = frozenset({"geladeira", "freezer"})

#: Acima disto, uma fornada no fogão consome gás o bastante para a reserva
#: importar. É um limiar de conversa, não de física: serve para decidir se vale
#: perguntar sobre o botijão, não para estimar consumo.
MINUTOS_QUE_PESAM_NO_GAS: Final = 60

#: Passo que usa outra panela ao mesmo tempo pede duas bocas acesas juntas.
BOCAS_AO_MESMO_TEMPO: Final = 2

#: A pergunta do tempo no fogo, quando nem os passos nem a receita dizem. A
#: resposta é da receita (como o rendimento), e volta nela com este nome.
CAMPO_DO_TEMPO_DA_RECEITA: Final = "tempo_cozimento_min"


def checar_operacional(receita: Receita, perfil: PerfilCozinha) -> Checagem:
    """Cabe na rotina dela: tempo, bocas, energia, gás e geladeira?

    As quatro restrições que o §2.2 nomeia estão todas aqui, e todas podem
    bloquear, menos as bocas: com uma boca só, ela faz uma panela depois da
    outra, e isso vira aviso. É o parágrafo que o enunciado chama de coração do
    desafio, e a frase que o resume é a instrução de projeto deste módulo: o
    agente não pode deixar ela comprar ingrediente e descobrir depois que não
    consegue cozinhar.
    """
    checagem = Checagem("operacional")
    restricoes = perfil.restricoes

    _checar_tempo(receita, restricoes, checagem)
    _checar_bocas(receita, restricoes, checagem)
    _checar_energia(receita, restricoes, checagem)
    _checar_gas(receita, restricoes, checagem)
    _checar_geladeira(receita, restricoes, checagem)
    return checagem


#: O peso de uma porção de delivery (uma marmita) quando ela ainda não disse o
#: dela: é premissa da plataforma, em `mise.parametros` (`porcao_padrao_g`), e
#: ela muda. Serve só para estimar quantas porções rende a receita que não diz.
PORCAO_PADRAO_G: Final = Decimal(350)

_GRAMAS_NO_QUILO: Final = Decimal(1000)


@dataclass(frozen=True, slots=True)
class RendimentoDoPrato:
    """Quantas porções a receita rende, e de onde saiu o número."""

    porcoes: int
    #: A receita não dizia: o número é estimativa, e ela pode mudar.
    estimado: bool
    #: A conta da estimativa ("cerca de 1,05 kg de ingredientes ÷ 350 g por porção").
    derivacao: str = ""
    porcao_g: Decimal = PORCAO_PADRAO_G

    @property
    def texto(self) -> str:
        """ "4 porções", ou "cerca de 3 porções (estimativa: porções de 350 g; ...)"."""
        porcoes = "1 porção" if self.porcoes == 1 else f"{self.porcoes} porções"
        if not self.estimado:
            return porcoes
        return (
            f"cerca de {porcoes} (estimativa: porções de {_limpa(self.porcao_g)} g; "
            "a senhora pode mudar)"
        )


def estimar_rendimento(
    receita: Receita,
    porcao_g: Decimal = PORCAO_PADRAO_G,
    ajustes: tuple[AjusteDoIngrediente, ...] = (),
) -> RendimentoDoPrato:
    """O rendimento da receita: o que ela diz, ou a estimativa pelo peso dos ingredientes.

    O rendimento não é perguntado. A receita que não diz rende o peso dos seus
    ingredientes (o que se pesa, o que tem medida caseira conhecida e os
    líquidos, a água inclusive) dividido pelo peso de uma porção, arredondado,
    e no mínimo uma porção. Sem nenhum peso conhecido, a receita inteira é uma
    porção: o custo por porção sai maior, que é o lado seguro do erro. O texto
    diz que é estimativa e que ela pode mudar (a resposta da receita, campo
    `rendimento_porcoes`).
    """
    if receita.rendimento_informado:
        return RendimentoDoPrato(receita.rendimento_porcoes, estimado=False, porcao_g=porcao_g)
    total = Decimal(0)
    medidas = {id(a.ingrediente): a for a in ajustes}
    for linha in receita.ingredientes:
        total += _gramas_do_ajuste(medidas[id(linha)]) if id(linha) in medidas else Decimal(0)
        total += _gramas_da_linha(linha) if id(linha) not in medidas else Decimal(0)
    if total <= 0:
        return RendimentoDoPrato(
            1,
            estimado=True,
            derivacao="sem o peso dos ingredientes, a receita inteira conta como 1 porção",
            porcao_g=porcao_g,
        )
    porcoes = max(1, int((total / porcao_g).quantize(Decimal(1), rounding=ROUND_HALF_UP)))
    peso = (
        f"{_limpa((total / _GRAMAS_NO_QUILO).quantize(Decimal('0.01')))} kg"
        if total >= _GRAMAS_NO_QUILO
        else f"{_limpa(total.quantize(Decimal(1)))} g"
    )
    return RendimentoDoPrato(
        porcoes,
        estimado=True,
        derivacao=(
            f"cerca de {peso} de ingredientes ÷ {_limpa(porcao_g)} g por porção = "
            f"{'1 porção' if porcoes == 1 else f'{porcoes} porções'}"
        ),
        porcao_g=porcao_g,
    )


def _gramas_do_ajuste(ajuste: AjusteDoIngrediente) -> Decimal:
    """O peso da linha pela conta da despensa (o pacote dela, a medida do IBGE), ou pela linha."""
    precisa = ajuste.precisa
    if precisa is not None and precisa.dimensao is Dimensao.MASSA:
        return precisa.valor * _GRAMAS_NO_QUILO
    liquido = ajuste.da_torneira or e_liquido(ajuste.item.nome if ajuste.item else "")
    if precisa is not None and precisa.dimensao is Dimensao.VOLUME and liquido:
        return precisa.valor * _GRAMAS_NO_QUILO
    return _gramas_da_linha(ajuste.ingrediente)


def _gramas_da_linha(linha: IngredienteReceita) -> Decimal:
    """O peso da linha em gramas, quando se sabe; zero quando não."""
    if linha.peso_g is not None:
        return linha.peso_g
    if linha.quantidade is None:
        return Decimal(0)
    pedida = medida(linha.quantidade, linha.medida, linha.nome)
    if pedida is None or pedida.embalagem:
        return Decimal(0)
    valor = pedida.quantidade.valor
    if pedida.quantidade.dimensao is Dimensao.MASSA:
        return valor * _GRAMAS_NO_QUILO
    if pedida.quantidade.dimensao is Dimensao.VOLUME and (
        _e_agua_da_torneira(linha.nome) or e_liquido(linha.nome)
    ):
        return valor * _GRAMAS_NO_QUILO
    return Decimal(0)


#: A partir de quantos minutos por cozinhada o tempo que a receita não diz
#: deixa de ser perguntado: 4 horas. Uma receita caseira cujo passo não diz o
#: tempo no fogo (um refogado, um risoto, um bolo) cabe folgada nisso; a que
#: passa (a feijoada de muitas horas) costuma dizer o tempo, e aí a conta é a
#: dos passos. Abaixo disso, o limite é apertado, e o portão pergunta.
LIMITE_FOLGADO_MIN: Final = 240


def _checar_tempo(receita: Receita, restricoes: RestricoesOperacionais, checagem: Checagem) -> None:
    """O tempo com o fogo ligado cabe numa cozinhada dela?

    O tempo que conta é o ativo (`mise.passos.minutos_ativos`): o dos passos,
    com fogo, forno ou aparelho ligado, sem as esperas; quando os passos não
    dizem tudo, o cozimento que a receita declara. Passou do limite dela,
    bloqueia com a conta no motivo. Com duas bocas, ou sem saber quantas, a
    "outra panela" pode correr junto da de antes: se assim cabe, não bloqueia
    (sem saber as bocas, a pergunta delas já vem de `_checar_bocas`).

    Tempo desconhecido não é tempo que cabe. Se o que os passos dizem já passa
    do limite, não dá; se nem o tempo total declarado, com as esperas, passa do
    limite, cabe; fora isso, o portão pergunta o tempo da receita. Sem passos e
    sem nada que diga o equipamento, o portão já pergunta como ela faz, e os
    passos trazem o tempo: perguntar o tempo antes seria perguntar duas vezes.
    Receita que não acende fogo nem liga aparelho não tem o que conferir.
    """
    ativos = minutos_ativos(receita)
    limite = restricoes.tempo_max_por_fornada_min
    sem_como_fazer = not receita.modo_preparo and not receita.equipamentos
    if ativos.ativos == 0 or (not ativos.conhecido and sem_como_fazer):
        return

    if limite is None:
        motivo = (
            f"{receita.nome} fica {ativos.ativos} minutos {_onde(receita, ativos)}"
            if ativos.conhecido
            else f"para saber se {receita.nome.lower()} cabe numa cozinhada"
        )
        checagem.perguntar(
            Pergunta(
                TipoRestricao.OPERACIONAL,
                "tempo_max_por_fornada_min",
                PERGUNTAS_OPERACIONAIS["tempo_max_por_fornada_min"],
                motivo=motivo,
            )
        )
        return

    bocas = restricoes.bocas_fogao
    panelas_juntas = bocas is None or bocas >= BOCAS_AO_MESMO_TEMPO

    if ativos.ativos is None:
        minimo, conta = minimo_pelos_passos(receita, panelas_juntas=panelas_juntas)
        if minimo > limite:
            _bloquear_pelo_tempo(checagem, f"{conta}; a senhora tem {limite} por cozinhada")
        elif receita.tempo_total_min and receita.tempo_total_min <= limite:
            return
        elif limite >= LIMITE_FOLGADO_MIN:
            checagem.avisar(
                Aviso(
                    "tempo",
                    f"A receita não diz quanto tempo fica no fogo. Com as {horas_texto(limite)} "
                    "que a senhora tem por cozinhada, uma receita assim cabe com folga, e por "
                    "isso não perguntei.",
                )
            )
        else:
            # O tempo da receita não se pergunta: sem ele, não dá para confirmar
            # que cabe, e a receita fica de fora, com o motivo; ela diz o tempo
            # na receita, se quiser.
            total = (
                f"a receita diz {receita.tempo_total_min} minutos no total, com as esperas, "
                "e não diz quanto disso é fogo"
                if receita.tempo_total_min
                else "a receita não diz quanto tempo fica no fogo, no forno ou com aparelho ligado"
            )
            _bloquear_pelo_tempo(
                checagem,
                f"{total}; com {horas_texto(limite)} por cozinhada, não dá para confirmar que cabe",
                "o tempo que a receita não diz; a senhora pode dizer o tempo, na receita",
            )
        return

    if ativos.ativos <= limite:
        return
    pelos_passos = ativos.origem is OrigemDoTempo.PASSOS
    juntas = minutos_com_panelas_juntas(receita) if pelos_passos and panelas_juntas else None
    if juntas is not None and juntas <= limite:
        return
    conta = (
        ativos.derivacao
        if pelos_passos
        else f"a receita diz que o cozimento leva {ativos.ativos} minutos"
    )
    if juntas is not None:
        conta += f"; mesmo com as duas panelas ao mesmo tempo, são {juntas} minutos"
    _bloquear_pelo_tempo(
        checagem,
        f"{conta}; a senhora tem {limite} por cozinhada",
        "tempo com fogo ou aparelho ligado, passo a passo; as esperas não contam"
        if pelos_passos
        else "tempo de cozimento que a receita declara",
    )


def _bloquear_pelo_tempo(
    checagem: Checagem,
    descricao: str,
    evidencia: str = "tempo com fogo ou aparelho ligado, passo a passo; as esperas não contam",
) -> None:
    checagem.bloquear(
        Impedimento(
            TipoRestricao.OPERACIONAL,
            "tempo_max_por_fornada_min",
            descricao,
            evidencia=evidencia,
        )
    )


def _onde(receita: Receita, ativos: MinutosAtivos) -> str:
    """ "no fogo", "no forno"... para o tempo dos passos; o declarado não diz onde."""
    return onde_corre(receita) if ativos.origem is OrigemDoTempo.PASSOS else "no fogo ou no forno"


def _checar_bocas(receita: Receita, restricoes: RestricoesOperacionais, checagem: Checagem) -> None:
    """Outra panela ao mesmo tempo pede duas bocas acesas juntas.

    Só o passo diz quando duas panelas andam juntas ("em outra panela"). Com
    duas bocas ou mais, cabe; com uma, também dá, uma parte depois da outra, e
    isso vira aviso, não bloqueio; sem saber o fogão, pergunta.

    A conta antiga somava os equipamentos de cozinhar como se fossem panelas
    acesas juntas, com o próprio fogão contando como uma: refogar na panela e
    selar na frigideira virava "2 panelas juntas", e uma boca bloqueava.
    """
    passos = passos_com_outra_panela(receita)
    if not passos:
        return
    quais = quais_passos(passos)
    if restricoes.bocas_fogao is None:
        checagem.perguntar(
            Pergunta(
                TipoRestricao.OPERACIONAL,
                "bocas_fogao",
                PERGUNTAS_OPERACIONAIS["bocas_fogao"],
                motivo=(
                    f"{receita.nome} usa duas panelas no fogo ao mesmo tempo "
                    f"({quais_passos(passos, artigo=False)})"
                ),
            )
        )
    elif restricoes.bocas_fogao < BOCAS_AO_MESMO_TEMPO:
        pede = "pede" if len(passos) == 1 else "pedem"
        checagem.avisar(
            Aviso(
                "bocas",
                f"{quais[:1].upper()}{quais[1:]} {pede} outra panela no fogo ao mesmo tempo. "
                "Com uma boca, a senhora faz uma parte depois da outra e leva mais tempo.",
            )
        )


def _checar_energia(
    receita: Receita, restricoes: RestricoesOperacionais, checagem: Checagem
) -> None:
    """Aparelhos de alta potência ligados juntos derrubam o disjuntor.

    A contagem é aproximada de propósito: a receita não diz o que roda ao mesmo
    tempo, e inferir isso do texto seria fingir uma precisão que não temos. O que
    ela diz é quantos aparelhos o preparo exige, e esse número basta para decidir
    se vale perguntar, que é o objetivo, e não estimar amperagem.
    """
    aparelhos = sorted(receita.equipamentos & APARELHOS_DE_ALTA_POTENCIA)
    if len(aparelhos) < APARELHOS_QUE_DISPUTAM_DISJUNTOR:
        return

    nomes = ", ".join(equipamento(id_).nome.lower() for id_ in aparelhos)
    if restricoes.energia_aparelhos_simultaneos is None:
        checagem.perguntar(
            Pergunta(
                TipoRestricao.OPERACIONAL,
                "energia_aparelhos_simultaneos",
                PERGUNTAS_OPERACIONAIS["energia_aparelhos_simultaneos"],
                motivo=f"{receita.nome} pede {nomes}",
            )
        )
    elif len(aparelhos) > restricoes.energia_aparelhos_simultaneos:
        checagem.bloquear(
            Impedimento(
                TipoRestricao.OPERACIONAL,
                "energia_aparelhos_simultaneos",
                f"a receita pede {len(aparelhos)} aparelhos de alta potência "
                f"({nomes}) e a instalação aguenta "
                f"{restricoes.energia_aparelhos_simultaneos} ao mesmo tempo",
                evidencia="disjuntor cai no meio da fornada",
            )
        )


def _checar_gas(receita: Receita, restricoes: RestricoesOperacionais, checagem: Checagem) -> None:
    """Fornada longa no fogão exige saber se há reserva de botijão.

    Acabar o gás no meio da produção não estraga só a fornada: estraga o pedido
    já vendido, e é o tipo de risco que só aparece quando já é tarde. O tempo é
    o que a receita fica no fogão (`mise.passos.minutos_no_fogo`), não o total:
    a marinada na geladeira não gasta gás.
    """
    no_fogo = minutos_no_fogo(receita)
    if no_fogo is None or no_fogo < MINUTOS_QUE_PESAM_NO_GAS:
        return

    if restricoes.tem_gas_sobrando is None:
        checagem.perguntar(
            Pergunta(
                TipoRestricao.OPERACIONAL,
                "tem_gas_sobrando",
                PERGUNTAS_OPERACIONAIS["tem_gas_sobrando"],
                motivo=(
                    f"{receita.nome} fica {no_fogo} minutos no fogo, "
                    "e ficar sem gás no meio estraga o pedido"
                ),
            )
        )
    elif restricoes.tem_gas_sobrando is False:
        checagem.bloquear(
            Impedimento(
                TipoRestricao.OPERACIONAL,
                "tem_gas_sobrando",
                f"a receita fica {no_fogo} minutos no fogo e não há botijão de reserva",
                evidencia="risco de acabar o gás com o pedido já vendido",
            )
        )


def _checar_geladeira(
    receita: Receita, restricoes: RestricoesOperacionais, checagem: Checagem
) -> None:
    """Preparo que vai à geladeira disputa espaço com a comida da casa.

    A receita precisa de frio quando um passo leva ao frio, com ou sem tempo
    dito ("deixe gelar até firmar"), ou quando o nome, os ingredientes ou quem
    montou a receita pedem geladeira ou freezer. Sem saber o espaço, pergunta;
    sem espaço nenhum, bloqueia. Ter a geladeira é outra conta, a dos
    equipamentos: o "não tenho geladeira" dela bloqueia lá.
    """
    passos = passos_com_frio(receita)
    frio_de_fora = receita.equipamentos & EQUIPAMENTOS_DE_FRIO
    if receita.modo_preparo:
        # O que os passos dizem de frio, quem decide é a leitura do passo, com o
        # contexto ("se sobrar, pode congelar" é dica); o resto vem do nome, dos
        # ingredientes ou de quem declarou a receita.
        frio_de_fora -= detectar(" ".join(receita.modo_preparo)).ids_equipamentos
    if not passos and not frio_de_fora:
        return
    onde = f" ({quais_passos(passos, artigo=False)})" if passos else ""

    if restricoes.espaco_geladeira_litros is None:
        checagem.perguntar(
            Pergunta(
                TipoRestricao.OPERACIONAL,
                "espaco_geladeira_litros",
                PERGUNTAS_OPERACIONAIS["espaco_geladeira_litros"],
                motivo=f"{receita.nome} precisa de espaço na geladeira{onde}",
            )
        )
    elif restricoes.espaco_geladeira_litros <= 0:
        checagem.bloquear(
            Impedimento(
                TipoRestricao.OPERACIONAL,
                "espaco_geladeira_litros",
                f"a receita precisa de espaço na geladeira{onde} e a senhora disse que não sobra",
                evidencia="informado por ela",
            )
        )


def checar_gosto(
    receita: Receita,
    gosto: Gosto = Gosto.DESCONHECIDO,
    impedimento_dela: str = "",
) -> Checagem:
    """A quinta checagem: ela gosta de fazer isto?

    É a mais barata de responder e a que mais elimina, e por isso entra no portão
    junto das outras quatro, e não como preferência a ser ponderada depois. Um
    prato que ela não gosta de fazer não entra no cardápio por mais barato que o
    CMV saia, porque quem cozinha é ela, todo dia.

    O §2.1 pede as duas perguntas juntas, e elas são diferentes: "gosta de
    cozinhar aquilo?" e "vê algum impedimento?". A segunda captura o que nenhuma
    taxonomia nossa antecipa, e por isso bloqueia mesmo quando ela gosta do
    prato: gostar de fazer e conseguir fazer não são a mesma coisa.
    """
    checagem = Checagem("gosto")

    if impedimento_dela.strip():
        checagem.bloquear(
            Impedimento(
                TipoRestricao.GOSTO,
                "impedimento_dela",
                f"a senhora mesma apontou um impedimento: {impedimento_dela.strip()}",
                evidencia="informado por ela",
            )
        )

    if gosto is Gosto.NAO_GOSTA:
        checagem.bloquear(
            Impedimento(
                TipoRestricao.GOSTO,
                "gosto",
                f"a senhora disse que não gosta de fazer {receita.nome.lower()}",
                evidencia="informado por ela",
            )
        )
    elif gosto is Gosto.DESCONHECIDO:
        checagem.perguntar(
            Pergunta(
                TipoRestricao.GOSTO,
                "gosto",
                f"A senhora gosta de fazer {receita.nome.lower()}? "
                "E vê algum impedimento pra preparar esse prato aí na sua cozinha?",
                motivo="não adianta a conta fechar se a senhora não quer cozinhar o prato",
            )
        )

    return checagem


class SituacaoDoIngrediente(StrEnum):
    """Como cada ingrediente da receita fica diante da despensa dela."""

    TEM = "tem"
    """Ela tem o que a receita pede, em casa ou no que já comprou para o cardápio."""
    TEM_PARTE = "tem_parte"
    """Ela tem uma parte; o resto entra na compra."""
    FALTA = "falta"
    """Ela não tem: entra inteiro na compra."""
    A_GOSTO = "a_gosto"
    """A receita não dá quantidade de propósito: sal a gosto, azeite para untar."""
    OPCIONAL = "opcional"
    """A receita diz que é opcional e ela não tem o bastante: fica de fora da conta e da compra."""
    NAO_ENTENDI = "nao_entendi"
    """A linha não diz quanto vai de um jeito que dê para ler: vira pergunta a ela."""
    CONFIRMAR = "confirmar"
    """A despensa tem um item parecido ("Miolo de alcatra" para "alcatra"): ela confirma se é."""


@dataclass(frozen=True, slots=True)
class AjusteDoIngrediente:
    """Um ingrediente da receita diante da despensa: quanto pede, de onde sai, o que falta.

    É o §2.3 linha a linha: o que ela já tem e em que quantidade, o que falta
    comprar e quanto custa. `precisa` é o pedido já convertido para a unidade do
    item dela (kg, L ou unidades) quando dá para converter, com a conta em
    `conversao`; `de_casa` é o que sai do estoque, `do_comprado` o que sai do
    que ela já comprou para o cardápio, e `faltante` é o resto, a comprar. As
    três partes somam o que a receita pede. `pergunta` é a dúvida que segurou a
    conta deste ingrediente, quando houve.
    """

    ingrediente: IngredienteReceita
    situacao: SituacaoDoIngrediente
    #: O item da despensa que casou com a linha, quando o casamento é confiável.
    item: Ingrediente | None = None
    precisa: Quantidade | None = None
    conversao: str = ""
    #: Quanto a conversão da medida pode errar (densidade, peso típico): 0 quando é exata.
    incerteza: Decimal = Decimal(0)
    de_casa: Quantidade | None = None
    #: O que ela já comprou deste ingrediente para o cardápio, e quanto disso a receita usa.
    comprado: Comprado | None = None
    do_comprado: Quantidade | None = None
    #: O que falta, na medida da receita ("1 lata") ou na do item ("0,2 kg").
    falta: Medida | None = None
    faltante: ItemFaltante | None = None
    pergunta: Pergunta | None = None
    #: A água da torneira: vai na receita, mas não se compra nem entra no custo.
    da_torneira: bool = False
    #: A medida caseira da tabela do IBGE que fez a conta ("1 peito" = 180 g):
    #: é referência, e o peso que ela disser vale mais (`corrigir_peso`).
    medida_de_referencia: MedidaDeReferencia | None = None
    #: O que ela corrige quando diz o peso da cozinha dela (a mesma forma da pergunta de medida).
    corrigir_peso: PesoPedido | None = None
    #: A quantidade que a receita não diz e a plataforma estabeleceu com fonte
    #: ("1 lata de 170 g"): a conta usa esta, e ela corrige na receita.
    quantidade_estimada: QuantidadeEstimada | None = None
    #: O item parecido da despensa que a conferência decidiu não ser o que a
    #: receita pede ("Farinha de mandioca" para "mandioca"): a linha vira compra.
    item_considerado: str = ""
    #: A decisão dita para ela: "Considerei que mandioca não é a sua farinha de mandioca...".
    decisao: str = ""
    #: O que a plataforma não achou em fonte nenhuma para esta linha (o peso, a
    #: quantidade): a receita fica de fora, sem pergunta, e ela corrige se quiser.
    sem_dado: str = ""


@dataclass(frozen=True, slots=True)
class QuantidadeEstimada:
    """A quantidade de uma linha que a receita não diz, estabelecida com a fonte.

    É a unidade de venda do ingrediente ("1 lata de 170 g", "1 tablete"), lida
    na página do produto que cota a compra, ou a embalagem que ela comprou, pela
    planilha. É estimativa, e o texto diz isso.
    """

    quantidade: Decimal
    medida: str
    #: "1 lata de 170 g", "1 tablete", "1 kg".
    texto: str
    #: De onde veio: "Milho Verde Quero Lata 170g, no Savegnago, 27/09/2026".
    fonte: str
    url: str | None = None

    @property
    def frase(self) -> str:
        """ "a receita não diz quanto; considerei 1 lata de 170 g (Milho Verde ...)"."""
        return f"a receita não diz quanto; considerei {self.texto} ({self.fonte})"


@dataclass(slots=True)
class ChecagemDeIngredientes(Checagem):
    """A checagem dos ingredientes, com o ajuste de cada linha da receita à despensa."""

    ajustes: list[AjusteDoIngrediente] = field(default_factory=list)


@dataclass(slots=True)
class _ContaDosIngredientes:
    """O que a checagem dos ingredientes vai juntando, linha por linha."""

    despensa: Despensa
    cotacoes: dict[str, Cotacao]
    comprados: dict[str, Comprado]
    checagem: ChecagemDeIngredientes
    #: O nome da receita: numa receita de frango, "peito" é o peito de frango dela.
    contexto: str = ""
    #: Os preços de referência, para o que falta e ela ainda não disse o preço.
    referencias: PrecosDeReferencia | None = None
    usos: list[UsoDeIngrediente] = field(default_factory=list)
    faltantes: list[ItemFaltante] = field(default_factory=list)
    a_gosto: list[str] = field(default_factory=list)


def checar_ingredientes(
    receita: Receita,
    despensa: Despensa,
    *,
    orcamento_restante: Dinheiro | None = None,
    precos: Mapping[str, Dinheiro | Cotacao] | None = None,
    compras: Mapping[str, Comprado] | None = None,
    referencias: PrecosDeReferencia | None = None,
) -> tuple[Checagem, tuple[UsoDeIngrediente, ...], tuple[ItemFaltante, ...], tuple[str, ...]]:
    """O que ela tem, o que falta, quanto custa o que falta, e se cabe no orçamento.

    Cada ingrediente é atendido nesta ordem: o que ela tem em casa, ao custo da
    planilha; o que ela já comprou para o cardápio, ao preço que pagou; e o
    resto vira compra, com consumo e desembolso separados (`mise.compras`).
    A soma das três partes é sempre a quantidade que a receita pede.

    Nenhuma linha some da conta sem dizer. A que a receita diz ser a gosto
    (ou que traz só o nome do tempero, "Sal", "Azeite") entra como "a gosto";
    a opcional que ela não tem fica listada como opcional, fora da compra; e a
    linha que não diz quanto vai ("Milho") ganha a unidade de venda do
    ingrediente, com a fonte ("a receita não diz quanto; considerei 1 lata de
    170 g"), em vez de passar como a gosto em silêncio ou virar pergunta. A
    checagem devolvida
    (`ChecagemDeIngredientes`) traz o ajuste de cada linha: quanto a receita
    pede, quanto ela tem, quanto sobra e o que falta comprar.

    `precos` são as cotações que o dossiê conhece. `compras` é o que ela já
    comprou: sem isso, registrar a compra não tirava o item da lista do que
    falta, e o orçamento era descontado duas vezes. `referencias` são os
    preços de referência (`mise.referencias`): cotam o que falta quando ela
    ainda não disse o preço, e o dela vale mais.
    """
    checagem = ChecagemDeIngredientes("ingredientes")
    conta = _ContaDosIngredientes(
        despensa=despensa,
        cotacoes={
            k: v if isinstance(v, Cotacao) else Cotacao(v) for k, v in (precos or {}).items()
        },
        comprados=dict(compras or {}),
        checagem=checagem,
        contexto=receita.nome,
        referencias=referencias,
    )
    for item in receita.ingredientes:
        if (item.texto_original or item.nome).strip():
            checagem.ajustes.append(_ajustar(item, conta))

    _checar_compras(checagem, conta.faltantes, orcamento_restante)
    return checagem, tuple(conta.usos), tuple(conta.faltantes), tuple(conta.a_gosto)


def _ajustar(item: IngredienteReceita, conta: _ContaDosIngredientes) -> AjusteDoIngrediente:
    """O ajuste de uma linha: sem quantidade, fora da despensa ou com o item em casa.

    O parecido nunca vira "tem" sozinho: quando o item dela só contém o que a
    receita pede, a conferência decide pelo lado seguro (não é o item dela, e a
    linha vira compra) e diz a decisão, que ela corrige quando quiser. O que ela
    disse (`item_da_despensa`) vale mais que qualquer casamento.
    """
    if _e_agua_da_torneira(item.nome):
        pedida = _medida_da_receita(item)
        return AjusteDoIngrediente(
            item,
            SituacaoDoIngrediente.TEM,
            precisa=pedida.quantidade if pedida is not None else None,
            da_torneira=True,
        )
    if item.item_da_despensa is not None:
        casamento = casar_confirmado(item.nome, item.item_da_despensa, conta.despensa)
    else:
        casamento = casar(item.nome, conta.despensa, contexto=conta.contexto)
    em_casa = casamento.item if casamento.confiavel else None
    if item.quantidade is None:
        return _sem_quantidade(item, casamento, em_casa, conta)
    if casamento.estrategia is Estrategia.PARCIAL and casamento.item is not None:
        return _nao_e_o_item_dela(item, casamento.item, conta)
    if em_casa is None:
        return _fora_de_casa(item, casamento, conta)
    ajuste = _com_o_item_em_casa(item, casamento, em_casa, conta)
    if casamento.estrategia is Estrategia.SINONIMO and (porque := motivo_do_sinonimo(item.nome)):
        # "Couro do bacon" é o bacon dela: a decisão é dita, e ela corrige se não for.
        ajuste = replace(ajuste, decisao=decisao_do_sinonimo(item.nome, em_casa.nome, porque))
    return ajuste


#: A água que a receita pede: a da torneira, quente, fria ou "até cobrir". Não
#: se compra e não entra no custo, como não entra em receita nenhuma. A água de
#: coco, a com gás e a tônica são outra coisa, e ficam de fora. A medida que
#: sobra no nome de uma quantidade escrita errada na página ("1 5 litro de
#: água", que a leitura lê como uma unidade de "5 litro de água") não faz da
#: água da torneira uma compra.
_AGUA_DA_TORNEIRA: Final = re.compile(
    r"^(?:\d+(?:[.,]\d+)?\s*(?:litros?|l|ml|mililitros?|x[ií]caras?|copos?)\s+de\s+)?"
    r"[aá]gua(?:\s+(?:quente|fria|morna|gelada|filtrada|fervente|fervendo|natural))?"
    r"(?:\s+(?:ou|e|para|at[eé])\b.*)?$",
    re.IGNORECASE,
)


def _e_agua_da_torneira(nome: str) -> bool:
    return bool(_AGUA_DA_TORNEIRA.match(" ".join(nome.split())))


#: Por que o item parecido pode ser o dela, dito no `editar` da decisão.
MOTIVO_DO_MESMO_ITEM: Final = (
    "se for, a receita usa o que a senhora já tem; se não for, fica na lista de compras"
)


def pergunta_do_mesmo_item(pedido: str, item: str) -> str:
    """ "A receita pede alcatra. É o seu miolo de alcatra?": o item dela, com o possessivo certo.

    É o texto do `editar` da decisão, para ela corrigir se quiser; nunca uma
    pergunta que segura a receita.
    """
    nome = falar(item)
    genero = nome.genero
    if genero is None:
        return f"A receita pede {_em_minuscula(pedido)}. É o item {nome.minusculo} da sua despensa?"
    seu = {"o": "o seu", "a": "a sua", "os": "os seus", "as": "as suas"}[genero.value]
    verbo = "São" if genero.plural else "É"
    return f"A receita pede {_em_minuscula(pedido)}. {verbo} {seu} {nome.minusculo}?"


def decisao_do_item(pedido: str, item: str) -> str:
    """ "Considerei que mandioca não é a sua farinha de mandioca: farinha é outro produto..."."""
    from mise.casamento import forma_diferente  # noqa: PLC0415

    nome = falar(item)
    genero = nome.genero
    seu = (
        {"o": "o seu", "a": "a sua", "os": "os seus", "as": "as suas"}[genero.value]
        if genero is not None
        else "o item"
    )
    forma = forma_diferente(pedido, item)
    porque = (
        f"{_FORMA_ESCRITA.get(forma, forma)} é outro produto"
        if forma is not None
        else "a receita não diz que é o mesmo"
    )
    return (
        f"Considerei que {_em_minuscula(pedido)} não é {seu} {nome.minusculo}: {porque}, e "
        "fica na lista de compras. Se for o mesmo, a senhora corrige."
    )


def decisao_do_sinonimo(pedido: str, item: str, porque: str) -> str:
    """ "Considerei que couro do bacon é o seu bacon: o couro é a pele da mesma peça..."."""
    nome = falar(item)
    genero = nome.genero
    seu = (
        {"o": "o seu", "a": "a sua", "os": "os seus", "as": "as suas"}[genero.value]
        if genero is not None
        else "o item"
    )
    return (
        f"Considerei que {_em_minuscula(pedido)} é {seu} {nome.minusculo}: {porque}. Se não "
        "for, a senhora corrige, e entra na lista de compras."
    )


#: Como a forma do produto se escreve na frase da decisão.
_FORMA_ESCRITA: Final[dict[str, str]] = {
    "po": "em pó",
    "fuba": "fubá",
    "oleo": "óleo",
    "geleia": "geleia",
    "essencia": "essência",
}


def _nao_e_o_item_dela(
    item: IngredienteReceita, parecido: Ingrediente, conta: _ContaDosIngredientes
) -> AjusteDoIngrediente:
    """A linha que só se parece com um item dela: não é o dela, vira compra, e a decisão é dita."""
    nenhum = Casamento(item.nome, None, Estrategia.NENHUM, 0.0)
    ajuste = _fora_de_casa(item, nenhum, conta)
    return replace(
        ajuste, item_considerado=parecido.nome, decisao=decisao_do_item(item.nome, parecido.nome)
    )


def _sem_quantidade(
    item: IngredienteReceita,
    casamento: Casamento,
    em_casa: Ingrediente | None,
    conta: _ContaDosIngredientes,
) -> AjusteDoIngrediente:
    """A gosto e opcional entram como são; a linha sem quantidade ganha a unidade de venda.

    A unidade vem da embalagem que ela comprou (pela planilha) ou da página do
    produto que cota a compra, e o texto diz que é estimativa. Sem nenhuma das
    duas, o tempero pronto vai a gosto; o resto deixa a receita de fora, sem
    pergunta, com o motivo.
    """
    if item.a_gosto:
        conta.a_gosto.append(item.nome)
    if item.a_gosto or item.opcional:
        situacao = (
            SituacaoDoIngrediente.OPCIONAL if item.opcional else SituacaoDoIngrediente.A_GOSTO
        )
        return AjusteDoIngrediente(item, situacao, em_casa)
    estimada = _quantidade_de_referencia(item, em_casa, conta)
    if estimada is not None:
        linha = replace(
            item, quantidade=estimada.quantidade, medida=estimada.medida, entendida=True
        )
        if em_casa is None:
            nenhum = Casamento(item.nome, None, Estrategia.NENHUM, 0.0)
            ajuste = _fora_de_casa(linha, nenhum, conta)
        else:
            ajuste = _com_o_item_em_casa(linha, casamento, em_casa, conta)
        return replace(ajuste, ingrediente=item, quantidade_estimada=estimada)
    if e_tempero_pronto(item.nome or item.texto_original):
        conta.a_gosto.append(item.nome)
        return AjusteDoIngrediente(item, SituacaoDoIngrediente.A_GOSTO, em_casa)
    motivo = (
        f"a receita não diz quanto vai de {_em_minuscula(item.nome or item.texto_original)}, "
        "e não achei a embalagem em que se vende; sem isso não dá para confirmar a compra "
        "nem o custo"
    )
    conta.checagem.bloquear(
        Impedimento(
            TipoRestricao.INGREDIENTE,
            f"linha:{item.texto_original or item.nome}",
            motivo,
            evidencia="a senhora pode dizer quanto vai, na receita",
        )
    )
    return AjusteDoIngrediente(item, SituacaoDoIngrediente.NAO_ENTENDI, em_casa, sem_dado=motivo)


#: O tempero pronto que a receita lista sem quantidade ("Sazón", "temperos de
#: sua preferência"): sem embalagem de referência, vai a gosto, como o sal.
_TEMPERO_PRONTO: Final = re.compile(
    r"\b(?:temperos?|sazon|sazón|condimentos?|ervas?)\b", re.IGNORECASE
)


def e_tempero_pronto(nome: str) -> bool:
    """A linha é de tempero pronto ou de temperos em geral: "Sazón", "temperos de sua escolha"."""
    return bool(_TEMPERO_PRONTO.search(nome))


def _quantidade_de_referencia(
    item: IngredienteReceita, em_casa: Ingrediente | None, conta: _ContaDosIngredientes
) -> QuantidadeEstimada | None:
    """A unidade de venda da linha que não diz quanto: a embalagem dela, ou a da página."""
    if em_casa is not None and (dela := _embalagem_dela(em_casa)) is not None:
        return dela
    if not conta.referencias:
        return None
    precos = conta.referencias.de(item.nome)
    if not precos:
        return None
    preco = next((p for p in precos if p.cada), precos[0])
    fonte = f"{preco.produto}, no {preco.site}, {preco.data_texto}"
    if preco.cada:
        cada = preco.cada
        return QuantidadeEstimada(
            Decimal(1), cada, f"1 {cada}, da {preco.embalagem_texto}", fonte, preco.url
        )
    if preco.embalagem in ("quilo", "unidade"):
        return QuantidadeEstimada(Decimal(1), "", "1 unidade", fonte, preco.url)
    return QuantidadeEstimada(
        Decimal(1), preco.embalagem, f"1 {preco.embalagem_texto}", fonte, preco.url
    )


def _embalagem_dela(em_casa: Ingrediente) -> QuantidadeEstimada | None:
    """A embalagem que ela comprou de uma vez, pela planilha ("1 | kg", "1 | un 500ml")."""
    conteudo = em_casa.unidade_compra.conteudo_por_embalagem
    if conteudo is None or em_casa.quantidade_bruta != 1:
        return None
    if conteudo.dimensao is Dimensao.MASSA:
        quantidade, medida = conteudo.valor * _GRAMAS_NO_QUILO, "g"
    elif conteudo.dimensao is Dimensao.VOLUME:
        quantidade, medida = conteudo.valor * _GRAMAS_NO_QUILO, "ml"
    else:  # pragma: no cover (o rótulo com conteúdo é de massa ou de volume)
        return None
    texto = _texto_da_quantidade(conteudo)
    return QuantidadeEstimada(
        quantidade, medida, texto, "a embalagem que a senhora comprou, pela planilha"
    )


def _fora_de_casa(
    item: IngredienteReceita, casamento: Casamento, conta: _ContaDosIngredientes
) -> AjusteDoIngrediente:
    """Ingrediente que a despensa não tem: sai do que ela já comprou, e o resto é compra."""
    nome = item.nome
    comprado = buscar(conta.comprados, nome)
    pedida = _medida_da_receita(item)
    precisa = pedida.quantidade if pedida is not None else None
    if item.opcional and not _cobre(comprado, pedida):
        # Opcional que ela não tem não vira compra: fica listado, fora da conta.
        return AjusteDoIngrediente(
            item, SituacaoDoIngrediente.OPCIONAL, precisa=precisa, comprado=comprado
        )
    resto, usado = _usar_o_comprado(item, casamento, pedida, comprado, conta.usos)
    if resto is _ATENDIDO:
        return AjusteDoIngrediente(
            item, SituacaoDoIngrediente.TEM, precisa=precisa, comprado=comprado, do_comprado=usado
        )
    faltante = _faltante(
        nome,
        str(item),
        resto,
        buscar(conta.cotacoes, nome),
        parcial=False,
        referencias=conta.referencias,
    )
    conta.faltantes.append(faltante)
    return AjusteDoIngrediente(
        item,
        SituacaoDoIngrediente.TEM_PARTE if usado is not None else SituacaoDoIngrediente.FALTA,
        precisa=precisa,
        comprado=comprado,
        do_comprado=usado,
        falta=resto,
        faltante=faltante,
    )


def _com_o_item_em_casa(
    item: IngredienteReceita,
    casamento: Casamento,
    em_casa: Ingrediente,
    conta: _ContaDosIngredientes,
) -> AjusteDoIngrediente:
    """Ingrediente que a despensa tem: o estoque atende o que dá, e o resto vem de fora."""
    comprado = buscar(conta.comprados, em_casa.nome)
    try:
        convertida = _converter(item, em_casa)
    except (MassaDesconhecida, DensidadeDesconhecida, UnidadeNaoNormalizavel) as erro:
        if item.opcional:
            return AjusteDoIngrediente(item, SituacaoDoIngrediente.OPCIONAL, em_casa)
        motivo = _sem_a_medida(item, em_casa, erro)
        conta.checagem.bloquear(
            Impedimento(
                TipoRestricao.INGREDIENTE,
                f"medida:{item.texto_original or item.nome}",
                motivo,
                evidencia="nenhuma fonte diz esse peso; a senhora pode dizer, se quiser",
            )
        )
        return AjusteDoIngrediente(
            item,
            SituacaoDoIngrediente.TEM,
            em_casa,
            comprado=comprado,
            corrigir_peso=_peso_pedido(item, erro),
            sem_dado=motivo,
        )
    pedida, conversao, incerteza = convertida.quantidade, convertida.conversao, convertida.incerteza

    de_casa = Quantidade(min(pedida.valor, em_casa.estoque.valor), pedida.dimensao)
    falta = Quantidade(pedida.valor - de_casa.valor, pedida.dimensao)
    if item.opcional and falta.valor > 0 and not _cobre(comprado, Medida(falta)):
        # Opcional que ela não tem inteiro não vira compra, nem entra pela metade.
        return AjusteDoIngrediente(
            item,
            SituacaoDoIngrediente.OPCIONAL,
            em_casa,
            precisa=pedida,
            conversao=conversao,
            incerteza=incerteza,
            medida_de_referencia=convertida.referencia,
            corrigir_peso=convertida.corrigir,
        )

    duvida = _custear_o_estoque(
        casamento, em_casa, (pedida, conversao, incerteza), de_casa=de_casa, conta=conta
    )
    if falta.valor <= 0:
        return AjusteDoIngrediente(
            item,
            SituacaoDoIngrediente.TEM,
            em_casa,
            precisa=pedida,
            conversao=conversao,
            incerteza=incerteza,
            de_casa=de_casa,
            comprado=comprado,
            pergunta=duvida,
            medida_de_referencia=convertida.referencia,
            corrigir_peso=convertida.corrigir,
        )

    resto, usado = _usar_o_comprado(item, casamento, Medida(falta), comprado, conta.usos)
    tem_algo = de_casa.valor > 0 or usado is not None
    faltante: ItemFaltante | None = None
    if resto is not _ATENDIDO:
        faltante = _faltante(
            em_casa.nome,
            f"faltam {resto}" if resto is not None else str(item),
            resto,
            buscar(conta.cotacoes, em_casa.nome),
            parcial=de_casa.valor > 0,
            # Sem o preço que ela pagou não há custo da planilha para repor a falta.
            custo_da_planilha=em_casa.custo.valor if em_casa.preco_informado else None,
            referencias=conta.referencias,
        )
        conta.faltantes.append(faltante)
    if faltante is None:
        situacao = SituacaoDoIngrediente.TEM
    elif tem_algo:
        situacao = SituacaoDoIngrediente.TEM_PARTE
    else:
        situacao = SituacaoDoIngrediente.FALTA
    return AjusteDoIngrediente(
        item,
        situacao,
        em_casa,
        precisa=pedida,
        conversao=conversao,
        incerteza=incerteza,
        de_casa=de_casa,
        comprado=comprado,
        do_comprado=usado,
        falta=None if resto is _ATENDIDO else resto,
        faltante=faltante,
        pergunta=duvida,
        medida_de_referencia=convertida.referencia,
        corrigir_peso=convertida.corrigir,
    )


def _custear_o_estoque(
    casamento: Casamento,
    em_casa: Ingrediente,
    convertida: tuple[Quantidade, str, Decimal],
    *,
    de_casa: Quantidade,
    conta: _ContaDosIngredientes,
) -> Pergunta | None:
    """A linha de custo do que sai do estoque, ou a pergunta do preço que ela não disse.

    `convertida` é o pedido da receita na unidade do item, com a conta e a incerteza.
    """
    pedida, conversao, incerteza = convertida
    if de_casa.valor <= 0:
        return None
    try:
        custo = em_casa.custo_de(pedida)
        derivacao = (
            f"{conversao} × {em_casa.custo.valor}/{em_casa.dimensao.value} = {custo.arredondado()}"
        )
    except PrecoDesconhecido:
        # Ela não disse quanto pagou: vale o preço de referência, dito como
        # referência; sem ele, a receita fica de fora, e ninguém pergunta.
        pela_referencia = _custo_pela_referencia(em_casa.nome, pedida, conta)
        if pela_referencia is None:
            conta.checagem.bloquear(
                Impedimento(
                    TipoRestricao.INGREDIENTE,
                    SEM_PRECO,
                    f"a senhora não disse quanto pagou {falar(em_casa.nome).de()}, e não achei o "
                    "preço em página de supermercado; sem ele não dá para saber o custo do prato",
                    evidencia=EVIDENCIA_SEM_PRECO,
                )
            )
            return None
        custo, texto = pela_referencia
        derivacao = f"{conversao} pelo {texto} = {custo.arredondado()}"
    uso = UsoDeIngrediente(
        casamento=casamento,
        quantidade=pedida,
        custo=custo,
        incerteza=incerteza,
        derivacao=derivacao,
    )
    conta.usos.append(
        uso if de_casa.valor >= pedida.valor else _parte(uso, de_casa.valor, em_casa.custo.valor)
    )
    return None


def _peso_pedido(item: IngredienteReceita, erro: ErroDeDados) -> PesoPedido | None:
    """O peso que ela pode dizer da linha cuja medida não se converte (a forma do `editar`)."""
    if isinstance(erro, MassaDesconhecida):
        return None
    o_que_pesa = getattr(erro, "o_que_pesa", None)
    if not o_que_pesa or item.quantidade is None:
        return None
    return PesoPedido(item.quantidade, item.medida, o_que_pesa)


def _sem_a_medida(item: IngredienteReceita, em_casa: Ingrediente, erro: ErroDeDados) -> str:
    """Por que a linha fica sem conta, dito para ela: o peso que fonte nenhuma diz."""
    if isinstance(erro, MassaDesconhecida):
        return (
            f"a embalagem {falar(em_casa.nome).de()} não diz o peso, e sem ele não dá para "
            "saber quanto a receita usa nem quanto custa o prato"
        )
    o_que_pesa = getattr(erro, "o_que_pesa", None) or (
        f"o que a receita pede de {_em_minuscula(item.nome)}"
    )
    return (
        f"não achei em fonte nenhuma quanto pesa {o_que_pesa}; sem isso não dá para saber "
        "quanto sai da despensa nem quanto custa o prato"
    )


def _custo_pela_referencia(
    nome: str, pedida: Quantidade, conta: _ContaDosIngredientes
) -> tuple[Dinheiro, str] | None:
    """O custo do que sai da despensa pelo preço de referência, e o texto dele; `None` sem ele."""
    if not conta.referencias:
        return None
    cotada = conta.referencias.cotar(nome, Medida(pedida))
    if cotada is None:
        return None
    referencia, na_embalagem = cotada
    preco = precificar_falta(na_embalagem, referencia.cotacao)
    if preco is None:  # pragma: no cover (a cotação de referência sempre tem preço)
        return None
    return preco.consumo, referencia.texto


#: O impedimento do preço que não se acha: ninguém pergunta, e a receita fica de fora.
SEM_PRECO: Final = "sem_preco"
EVIDENCIA_SEM_PRECO: Final = (
    "sem preço de referência em página de supermercado; o preço da senhora vale, se ela "
    "quiser dizer"
)


#: Por que ela precisa dizer o peso: sem ele, a conta do prato não fecha.
MOTIVO_DO_PESO: Final = (
    "sem o peso, não dá para saber quanto sai da despensa nem quanto custa o prato"
)


def _cobre(comprado: Comprado | None, pedida: Medida | None) -> bool:
    """O que ela já comprou cobre, sozinho, tudo o que falta?"""
    return (
        comprado is not None
        and pedida is not None
        and pedida.compativel(comprado.medida)
        and comprado.medida.quantidade.valor >= pedida.quantidade.valor
    )


def _lista(nomes: list[str]) -> str:
    """ "milho", "milho e coco", "milho, coco e fubá"."""
    if len(nomes) <= 1:
        return "".join(nomes)
    return ", ".join(nomes[:-1]) + " e " + nomes[-1]


def _em_minuscula(texto: str) -> str:
    """ "Sal" vira "sal"; sigla ("UHT") e nome que já vem em minúscula ficam como estão."""
    primeira = texto.split(" ", 1)[0]
    if len(primeira) > 1 and primeira.isupper():
        return texto
    return texto[:1].lower() + texto[1:]


def _checar_compras(
    checagem: Checagem, faltantes: list[ItemFaltante], orcamento_restante: Dinheiro | None
) -> None:
    """Bloqueia o que não cabe no orçamento, e o que não tem preço em fonte nenhuma.

    O preço nunca é perguntado. Sem a cotação dela, sem o preço que ela pagou e
    sem preço de referência, não dá para confirmar que a compra cabe nos R$ 80,00:
    a receita fica de fora da grade, com o motivo, e o preço dela vale quando
    ela quiser dizer.
    """
    if faltantes:
        checagem.veredito = max(checagem.veredito, Veredito.APTO_COM_COMPRA)
        sem_preco = [_em_minuscula(f.nome) for f in faltantes if not f.custo_conhecido]
        if sem_preco:
            checagem.bloquear(
                Impedimento(
                    TipoRestricao.INGREDIENTE,
                    SEM_PRECO,
                    f"não achei em página de supermercado o preço de {_lista(sem_preco)}; sem "
                    "ele não dá para confirmar que a compra cabe no orçamento",
                    evidencia=EVIDENCIA_SEM_PRECO,
                )
            )
        elif orcamento_restante is not None:
            total = Dinheiro.zero()
            for f in faltantes:
                assert f.custo_estimado is not None
                total = total + f.custo_estimado
            if total.valor > orcamento_restante.valor:
                pela_referencia = [_em_minuscula(f.nome) for f in faltantes if f.referencia]
                porque = (
                    f", com o preço de referência de {_lista(pela_referencia)}; se a senhora "
                    "paga menos, corrija o preço"
                    if pela_referencia
                    else ""
                )
                checagem.bloquear(
                    Impedimento(
                        TipoRestricao.INGREDIENTE,
                        "orcamento",
                        f"a compra sai {total} e restam {orcamento_restante} do orçamento{porque}",
                    )
                )


#: Marca de "o comprado cobriu tudo": distinta de `None`, que é "não sei medir".
_ATENDIDO: Final = Medida(Quantidade(Decimal(0), Dimensao.CONTAGEM), "atendido")


def _medida_da_receita(item: IngredienteReceita) -> Medida | None:
    if item.quantidade is None:
        return None
    return medida(item.quantidade, item.medida, item.nome)


def _usar_o_comprado(
    item: IngredienteReceita,
    casamento: Casamento,
    falta: Medida | None,
    comprado: Comprado | None,
    usos: list[UsoDeIngrediente],
) -> tuple[Medida | None, Quantidade | None]:
    """Usa o que ela já comprou para cobrir `falta`. Devolve o que ainda falta e o que usou.

    O comprado entra como linha própria, ao preço que ela pagou: é custo real
    do prato e não pode sumir, nem ser cobrado de novo como compra.
    """
    if comprado is None or falta is None or not falta.compativel(comprado.medida):
        return falta, None
    usado = min(falta.quantidade.valor, comprado.medida.quantidade.valor)
    custo = comprado.custo_unitario * usado
    usos.append(
        UsoDeIngrediente(
            casamento=casamento,
            quantidade=Quantidade(usado, falta.quantidade.dimensao),
            custo=custo,
            incerteza=Decimal(0),
            derivacao=(
                f"{Medida(Quantidade(usado, falta.quantidade.dimensao), falta.embalagem)} "
                f"do que a senhora comprou ({comprado.valor} por {comprado.medida}) "
                f"= {custo.arredondado()}"
            ),
            rotulo=f"{casamento.item.nome if casamento.item else item.nome} (comprado)",
        )
    )
    resto = falta.quantidade.valor - usado
    quanto = Quantidade(usado, falta.quantidade.dimensao)
    if resto <= 0:
        return _ATENDIDO, quanto
    return Medida(Quantidade(resto, falta.quantidade.dimensao), falta.embalagem), quanto


def _parte(uso: UsoDeIngrediente, quantidade: Decimal, unitario: Dinheiro) -> UsoDeIngrediente:
    """A parte de um uso que o estoque dela atende, ao custo da planilha."""
    parcial = Quantidade(quantidade, uso.quantidade.dimensao)
    custo = unitario * quantidade
    return UsoDeIngrediente(
        casamento=uso.casamento,
        quantidade=parcial,
        custo=custo,
        incerteza=uso.incerteza,
        derivacao=(
            f"{parcial} em estoque × {unitario}/{parcial.dimensao.value} = {custo.arredondado()}"
        ),
    )


def _faltante(
    nome: str,
    texto: str,
    falta: Medida | None,
    cotacao: Cotacao | None,
    *,
    parcial: bool,
    custo_da_planilha: Dinheiro | None = None,
    referencias: PrecosDeReferencia | None = None,
) -> ItemFaltante:
    """O que falta, com o preço: o que ela disse, o que ela pagou, ou o de referência.

    A ordem é a da confiança. A cotação dela vem primeiro; depois, o preço que
    ela pagou na despensa, para repor o que falta; e só sem nenhum dos dois, o
    preço de referência de uma página de supermercado, dito como referência e
    com a fonte (`mise.referencias`). Sem nada disso, o preço é pergunta.
    """
    preco = precificar_falta(falta, cotacao, custo_da_planilha)
    referencia: PrecoDeReferencia | None = None
    if preco is None and referencias:
        cotada = referencias.cotar(nome, falta)
        if cotada is not None:
            referencia, na_embalagem = cotada
            preco = precificar_falta(na_embalagem, referencia.cotacao)
    if preco is None:
        return ItemFaltante(nome, texto, parcial=parcial, falta=falta)
    if referencia is not None:
        origem = "referencia"
    else:
        origem = cotacao.origem if cotacao is not None else "planilha"
    return ItemFaltante(
        nome,
        texto,
        preco.desembolso,
        parcial=parcial,
        consumo=preco.consumo,
        derivacao=preco.derivacao,
        premissa=referencia.texto if referencia is not None else preco.premissa,
        origem_do_preco=origem,
        falta=falta,
        referencia=referencia,
    )


@dataclass(frozen=True, slots=True)
class _Convertida:
    """A medida da receita na unidade do item dela, com a conta e de onde a conta saiu."""

    quantidade: Quantidade
    conversao: str
    incerteza: Decimal
    #: A medida caseira da tabela do IBGE, quando foi ela que fez a conta.
    referencia: MedidaDeReferencia | None = None
    #: O peso que ela pode dizer para corrigir a medida de referência.
    corrigir: PesoPedido | None = None


def _converter(item: IngredienteReceita, encontrado: Ingrediente) -> _Convertida:
    """A medida da receita na unidade do item da despensa: a quantidade, a conta e a incerteza.

    O peso que ela disse da linha (`peso_g`) entra quando a medida não se
    converte sozinha, e também no lugar de uma medida de referência da tabela
    do IBGE ("1 peito" = 180 g): o peso da cozinha dela vale mais que a
    média da tabela. Só para o item que a despensa conta em quilo, e nunca no
    lugar de uma conversão exata ("500 g").
    """
    erro: DensidadeDesconhecida | UnidadeNaoNormalizavel | None = None
    try:
        convertida: _Convertida | None = _converter_a_medida(item, encontrado)
    except (DensidadeDesconhecida, UnidadeNaoNormalizavel) as falhou:
        convertida, erro = None, falhou
    peso = item.peso_g
    dela = peso is not None and item.quantidade is not None
    if (
        dela
        and encontrado.dimensao is Dimensao.MASSA
        and (convertida is None or convertida.referencia is not None)
    ):
        assert peso is not None
        assert item.quantidade is not None
        escrita = _medida_escrita(item.medida, item.quantidade).strip() or item.nome
        return _Convertida(
            Quantidade(peso / Decimal(1000), Dimensao.MASSA),
            f"{_limpa(item.quantidade)} {escrita} = {_limpa(peso)} g (a senhora disse)",
            Decimal(0),
        )
    if convertida is None:
        assert erro is not None
        raise erro
    return convertida


#: As embalagens que a receita escreve: "1 pacote de feijão preto" é o pacote dela.
_EMBALAGENS_DA_RECEITA: Final = frozenset(
    {
        "pacote",
        "pacotinho",
        "lata",
        "latinha",
        "caixa",
        "caixinha",
        "vidro",
        "pote",
        "sache",
        "garrafa",
        "embalagem",
        "saco",
        "saquinho",
        "bandeja",
    }
)

#: O rótulo da planilha que diz só "uma unidade", sem dizer que embalagem é.
_UNIDADE_GENERICA: Final = frozenset({"un", "und", "unid", "unidade"})

#: O número e a unidade de um rótulo da planilha ("balde 2kg"): o que sobra é a embalagem.
_CONTEUDO_DO_ROTULO: Final = re.compile(r"\d+(?:[.,]\d+)?\s*(?:kg|mg|g|ml|l)\b")


def _sem_acento_minusculo(texto: str) -> str:
    import unicodedata  # noqa: PLC0415

    decomposto = unicodedata.normalize("NFKD", texto)
    return " ".join("".join(c for c in decomposto if not unicodedata.combining(c)).lower().split())


def _pacote_dela(item: IngredienteReceita, encontrado: Ingrediente) -> _Convertida | None:
    """ "1 pacote de feijão preto", do item que ela tem: o pacote é o que a planilha dela diz.

    A planilha diz quanto ela comprou e em que embalagem. Um quilo comprado de
    uma vez ("1 | kg") é o pacote de 1 kg; "1 | un 500ml" é a unidade de 500
    ml, que vale para a garrafa, o vidro ou a lata; "1 | un" conta a peça. O
    rótulo que nomeia outra embalagem ("balde 2kg") só vale para ela, e a
    compra de vários quilos ("5 | kg") não diz o tamanho do pacote: aí a
    pergunta fica.
    """
    pedida = _sem_acento_minusculo(item.medida)
    if pedida not in _EMBALAGENS_DA_RECEITA or item.quantidade is None:
        return None
    rotulo = encontrado.unidade_compra
    palavras = _CONTEUDO_DO_ROTULO.sub(" ", _sem_acento_minusculo(rotulo.rotulo_original)).split()
    conteudo = rotulo.conteudo_por_embalagem
    uma_so = encontrado.quantidade_bruta == 1
    if conteudo is None:
        pacote = Quantidade(Decimal(1), Dimensao.CONTAGEM) if uma_so and palavras else None
    elif not palavras or palavras == [rotulo.dimensao.value.lower()]:
        pacote = encontrado.comprado if uma_so else None
    elif set(palavras) <= _UNIDADE_GENERICA or palavras == [pedida]:
        pacote = conteudo
    else:
        pacote = None
    if pacote is None or pacote.dimensao is not encontrado.dimensao:
        return None
    total = Quantidade(pacote.valor * item.quantidade, pacote.dimensao)
    escrita = _medida_escrita(item.medida, item.quantidade).strip()
    return _Convertida(
        total,
        f"{_limpa(item.quantidade)} {escrita} = {_texto_da_quantidade(total)} "
        "(a embalagem que a senhora comprou, pela planilha)",
        Decimal(0),
    )


def _texto_da_quantidade(quantidade: Quantidade) -> str:
    """ "1 kg", "500 ml", "1 unidade": a quantidade como ela lê."""
    from mise.despensa_json import quantidade_texto  # noqa: PLC0415

    return quantidade_texto(quantidade)


def _converter_a_medida(item: IngredienteReceita, encontrado: Ingrediente) -> _Convertida:
    """A conversão da medida da receita, sem o peso que ela disse."""
    assert item.quantidade is not None
    if (do_pacote := _pacote_dela(item, encontrado)) is not None:
        return do_pacote
    pedida = classificar_medida(item.medida)

    if encontrado.dimensao is Dimensao.CONTAGEM:
        # A despensa conta este item por peça. Só dá para usar se a receita
        # também falar em peças. Se ela pede massa ou volume, "200 g de
        # cobertura", precisaríamos do peso da embalagem, que não temos.
        if pedida is not Dimensao.CONTAGEM:
            raise MassaDesconhecida(
                encontrado.nome,
                float(encontrado.preco_pago.valor),
                encontrado.unidade_compra.rotulo_original,
            )
        return _Convertida(
            Quantidade(item.quantidade, Dimensao.CONTAGEM),
            f"{_limpa(item.quantidade)} {encontrado.nome.lower()}",
            Decimal("0"),
        )
    if encontrado.dimensao is Dimensao.VOLUME:
        convertida = converter_medida_para_volume(item.quantidade, item.medida)
    else:
        try:
            convertida = converter_medida(item.quantidade, item.medida, encontrado.nome)
            pesado = encontrado.nome
        except (DensidadeDesconhecida, UnidadeNaoNormalizavel):
            # O nome do item dela não diz o peso, e a linha da receita às vezes diz:
            # "1 couro do bacon" é um pedaço de toucinho, na tabela do IBGE.
            if medida_de_referencia(item.medida, item.nome) is None:
                raise
            convertida = converter_medida(item.quantidade, item.medida, item.nome)
            pesado = item.nome
    referencia = convertida.referencia
    corrigir = None
    if referencia is not None:
        uma = (
            DensidadeDesconhecida(pesado, item.medida).o_que_pesa
            if referencia.medida
            else UnidadeNaoNormalizavel("", pesado).o_que_pesa
        )
        if uma:
            corrigir = PesoPedido(item.quantidade, item.medida if referencia.medida else "", uma)
    return _Convertida(
        convertida.quantidade,
        convertida.derivacao,
        convertida.incerteza_relativa,
        referencia,
        corrigir,
    )


# --------------------------------------------------------------------------- #
# O portão
# --------------------------------------------------------------------------- #


def avaliar(
    receita: Receita,
    perfil: PerfilCozinha,
    despensa: Despensa,
    *,
    orcamento_restante: Dinheiro | None = None,
    precos: Mapping[str, Dinheiro | Cotacao] | None = None,
    compras: Mapping[str, Comprado] | None = None,
    gosto: Gosto = Gosto.DESCONHECIDO,
    impedimento_dela: str = "",
    referencias: PrecosDeReferencia | None = None,
    porcao_g: Decimal = PORCAO_PADRAO_G,
) -> Avaliacao:
    """Roda as cinco checagens e combina os vereditos.

    A combinação é o máximo (pior) dos quatro. É o que garante monotonicidade:
    nenhuma checagem consegue "melhorar" o resultado de outra. O rendimento
    não entra no veredito: é pergunta do preço (`Avaliacao.perguntas_do_preco`).
    """
    checagem_ingredientes, usos, faltantes, a_gosto = checar_ingredientes(
        receita,
        despensa,
        orcamento_restante=orcamento_restante,
        precos=precos,
        compras=compras,
        referencias=referencias,
    )
    checagens = (
        checagem_ingredientes,
        checar_equipamentos(receita, perfil),
        checar_tecnicas(receita, perfil),
        checar_operacional(receita, perfil),
        checar_gosto(receita, gosto, impedimento_dela),
    )
    return Avaliacao(
        receita_nome=receita.nome,
        veredito=max(c.veredito for c in checagens),
        checagens=checagens,
        usos=usos,
        faltantes=faltantes,
        a_gosto=a_gosto,
        orcamento_restante=orcamento_restante,
        rendimento=estimar_rendimento(
            receita,
            porcao_g,
            tuple(checagem_ingredientes.ajustes)
            if isinstance(checagem_ingredientes, ChecagemDeIngredientes)
            else (),
        ),
    )


def _limpa(valor: Decimal) -> str:
    """Como se escreve no Brasil: "0,5 kg", não "0.5 kg"."""
    n = valor.normalize()
    return (
        str(n.quantize(Decimal("1"))) if n == n.to_integral_value() else f"{n:f}".replace(".", ",")
    )


__all__ = [
    "AjusteDoIngrediente",
    "AssuntoDaPergunta",
    "Avaliacao",
    "Aviso",
    "Checagem",
    "ChecagemDeIngredientes",
    "Impedimento",
    "ItemFaltante",
    "Pergunta",
    "PesoPedido",
    "RendimentoDoPrato",
    "SituacaoDoIngrediente",
    "TipoRestricao",
    "UsoDeIngrediente",
    "Veredito",
    "assunto_da",
    "avaliar",
    "checar_equipamentos",
    "checar_ingredientes",
    "checar_operacional",
    "checar_tecnicas",
    "estimar_rendimento",
]
