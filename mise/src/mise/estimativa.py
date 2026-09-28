"""O preço preliminar: quanto cobrar, com o que se sabe hoje, antes da receita ser conferida.

É uma estimativa para ela ter uma ideia, e diz isso em todo lugar: vem sempre
rotulada "preliminar", nunca é gravada como decisão e nunca vira o preço do
cardápio (o preço final passa pela conferência completa, em `cenarios_preco`).
Receita que ela não consegue fazer não tem estimativa: a recusa vem com o motivo.

**As linhas do custo de produção**, cada uma com a conta e as premissas:

- ingredientes da porção: a mesma conta do custo por porção do motor, com o que
  ela tem, o que já comprou e o que falta comprar, só que sem exigir a receita
  conferida. Se algum ingrediente ainda não tem custo (o peso da embalagem, o
  preço do que falta), a estimativa não inventa: diz o que falta saber;
- mão de obra: o valor da hora dela × os minutos de trabalho ÷ as porções. Os
  minutos são os dos passos (`mise.passos.minutos_ativos`); sem tempo nos
  passos, o tempo que a receita declara, dito como premissa;
- gás: os minutos no fogão e no forno a gás × o custo do minuto de fogo (o
  botijão ÷ as horas que ele dura) ÷ as porções;
- energia: a potência de cada aparelho elétrico × os minutos × o preço do kWh
  ÷ as porções;
- embalagem: o que ela paga por porção; sem esse número, a linha fica de fora
  da conta, e a estimativa pede.

**Os preços**, todos com a taxa de 10% da plataforma aberta:

- custo de produção: a soma das linhas conhecidas;
- piso: custo de produção ÷ 0,90, arredondado para cima, o menor preço que não
  dá prejuízo depois da taxa;
- mínimo do desafio: só o ingrediente ÷ 0,90, arredondado para cima;
- três pontos: o maior entre o piso e o ingrediente ÷ 0,40, ÷ 0,35 e ÷ 0,30,
  cada um com o que chega para ela (0,90 × preço), o que a plataforma fica (o
  resto), o lucro sobre o ingrediente (0,90 × preço − ingrediente) e o que
  sobra de verdade depois de todo o custo.

Toda conta é em `Decimal`, e toda linha de custo é arredondada para cima: custo
que vira base de preço nunca desce.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, Final

from mise import parametros
from mise.dinheiro import CENTAVO, Dinheiro
from mise.erros import Ausente, ErroDeRegra, ErroDeUso
from mise.preco import FOOD_COSTS_PADRAO, RETENCAO
from mise.viabilidade import TipoRestricao, Veredito

if TYPE_CHECKING:
    from mise.cmv import CMV
    from mise.mcp_server import Sessao
    from mise.perfil import PerfilCozinha
    from mise.receita import Receita
    from mise.tempo import MinutosAtivos
    from mise.viabilidade import Avaliacao

#: O que a estimativa é, dito em todo lugar em que ela aparece.
ROTULO: Final = "Preço preliminar"

#: A frase das referências de mercado: nenhuma é conferida nesta versão.
SEM_REFERENCIA: Final = (
    "Ainda não tenho preço de mercado conferido numa página para comparar; "
    "os três preços saem da conta do custo."
)

#: O que roda a gás: o fogão (com as panelas dele) e o forno do fogão.
A_GAS: Final[frozenset[str]] = frozenset(
    {
        "fogao",
        "forno",
        "panela_pressao",
        "frigideira",
        "frigideira_antiaderente",
        "panela_funda",
        "chapa",
        "banho_maria",
    }
)

#: A ordem em que um aparelho elétrico é escolhido quando a receita não diz o tempo por passo.
_ELETRICOS_POR_ORDEM: Final = ("forno_eletrico", "air_fryer", "microondas")

#: A casa decimal do custo do minuto de gás (em reais): 0,0479 é 4,79 centavos.
_CASAS_DO_MINUTO: Final = 4

#: A casa decimal do kWh gasto: o watt-hora.
_CASAS_DO_KWH: Final = 3


class EstimativaRecusada(ErroDeRegra):
    """A receita que ela não consegue fazer não tem preço, nem preliminar."""

    def __init__(self, receita: str, motivos: str) -> None:
        super().__init__(
            f"{receita}: a senhora não consegue fazer essa receita hoje, porque {motivos}. "
            "Por isso não faço estimativa de preço para ela.",
            receita=receita,
        )
        self.receita = receita


@dataclass(frozen=True, slots=True)
class Linha:
    """Uma linha do custo de produção por porção."""

    id: str
    rotulo: str
    valor: Dinheiro | None
    derivacao: str
    premissas: tuple[str, ...] = ()

    def para_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rotulo": self.rotulo,
            "valor": _dinheiro(self.valor) if self.valor is not None else None,
            "derivacao": self.derivacao,
            "premissas": list(self.premissas),
        }


@dataclass
class _Conta:
    """O que a estimativa vai juntando: premissas usadas, o que falta e o que confirmar."""

    premissas: dict[str, parametros.Premissa]
    usadas: dict[str, None] = field(default_factory=dict)
    faltam: dict[str, None] = field(default_factory=dict)
    confirmar: dict[str, None] = field(default_factory=dict)

    def usar(self, nome: str) -> parametros.Premissa:
        self.usadas.setdefault(nome)
        premissa = self.premissas[nome]
        if not premissa.conhecida:
            self.faltam.setdefault(nome)
        return premissa


# --------------------------------------------------------------------------- #
# Números em texto
# --------------------------------------------------------------------------- #


def _dinheiro(valor: Dinheiro) -> dict[str, Any]:
    return {"valor": float(valor.arredondado().valor), "texto": str(valor)}


def _numero(valor: Decimal) -> str:
    from mise.despensa_json import numero_texto  # noqa: PLC0415

    return numero_texto(valor)


def _tres_casas(valor: Decimal) -> str:
    """ "5,856": a divisão antes do arredondamento, com três casas."""
    return f"{valor.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP):f}".replace(".", ",")


def _centavos(valor: Decimal) -> str:
    """ "4,79 centavos": o que vale menos de um centavo inteiro, dito como ela diria."""
    return f"{_numero((valor * 100).normalize())} centavos"


def _para_cima(valor: Decimal) -> Dinheiro:
    return Dinheiro(valor.quantize(CENTAVO, rounding=ROUND_CEILING))


def _redondo(valor: Decimal) -> Dinheiro:
    return Dinheiro(valor.quantize(CENTAVO, rounding=ROUND_HALF_UP))


def _porcoes(n: int) -> str:
    return f"{n} {'porção' if n == 1 else 'porções'}"


def _lista(nomes: list[str]) -> str:
    if len(nomes) <= 1:
        return "".join(nomes)
    return ", ".join(nomes[:-1]) + " e " + nomes[-1]


def _minuscula(texto: str) -> str:
    primeira = texto.split(" ", 1)[0]
    return texto if len(primeira) > 1 and primeira.isupper() else texto[:1].lower() + texto[1:]


def _arredondado(exato: Decimal, valor: Dinheiro) -> str:
    return "" if exato == valor.valor else ", arredondado para cima"


# --------------------------------------------------------------------------- #
# Tempo e onde ele corre
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _Tempos:
    """Os minutos de trabalho e os de fogo ou aparelho, com as premissas."""

    trabalho: int | None
    trabalho_premissa: str
    gas: int
    eletricos: dict[str, int]
    fonte_premissa: str
    sem_conta: tuple[str, ...]


def _substituto_do_forno(perfil: PerfilCozinha) -> str | None:
    """O aparelho que faz o papel do forno quando ela disse que não tem forno."""
    from mise.perfil import Posse  # noqa: PLC0415
    from mise.taxonomia import equipamento  # noqa: PLC0415

    if perfil.tem_equipamento("forno") is not Posse.NAO_TEM:
        return None
    return next(
        (s for s in equipamento("forno").substitutos if perfil.tem_equipamento(s) is Posse.TEM),
        None,
    )


def _onde_a_receita_cozinha(receita: Receita) -> str | None:
    """Sem tempo por passo: o fogão se a receita vai ao fogo, senão o aparelho elétrico dela."""
    if receita.equipamentos & A_GAS:
        return "fogao"
    return next((e for e in _ELETRICOS_POR_ORDEM if e in receita.equipamentos), None)


def _trabalho(receita: Receita, ativos: MinutosAtivos) -> tuple[int | None, str]:
    """Os minutos de trabalho e a premissa: os dos passos, senão o tempo declarado."""
    from mise.tempo import OrigemDoTempo  # noqa: PLC0415

    if ativos.ativos:
        premissa = ativos.derivacao if ativos.origem is OrigemDoTempo.TEMPO_DECLARADO else ""
        return ativos.ativos, premissa
    declarado = receita.tempo_declarado_min
    if declarado:
        return declarado, (
            f"os passos não dizem o tempo de trabalho; a conta usa os {declarado} min que a "
            "receita declara"
        )
    return None, ""


def _por_aparelho(receita: Receita, ativos: MinutosAtivos) -> tuple[dict[str | None, int], str]:
    """Os minutos de fogo ou aparelho, por aparelho, e a premissa quando os passos não dizem."""
    from mise.passos import TipoDeLimite, extrair_limites  # noqa: PLC0415
    from mise.tempo import OrigemDoTempo  # noqa: PLC0415

    por_aparelho: dict[str | None, int] = defaultdict(int)
    if ativos.origem is OrigemDoTempo.PASSOS:
        for texto in receita.modo_preparo:
            for limite in extrair_limites(texto):
                if limite.tipo is TipoDeLimite.TEMPO and limite.minutos:
                    por_aparelho[limite.equipamento] += limite.minutos
        return dict(por_aparelho), ""
    if not ativos.ativos:
        return {}, ""
    onde = _onde_a_receita_cozinha(receita)
    if onde is None:
        return {None: ativos.ativos}, ""
    lugar = "no fogão" if onde == "fogao" else "no aparelho elétrico"
    return {onde: ativos.ativos}, (
        f"a receita não diz o tempo de cada passo; a conta põe os {ativos.ativos} min {lugar}"
    )


def _tempos(receita: Receita, perfil: PerfilCozinha) -> _Tempos:
    from mise.passos import minutos_ativos  # noqa: PLC0415

    ativos = minutos_ativos(receita)
    trabalho, premissa_trabalho = _trabalho(receita, ativos)
    por_aparelho, premissa_fonte = _por_aparelho(receita, ativos)
    vai_ao_fogo = bool(receita.equipamentos & A_GAS)
    substituto = _substituto_do_forno(perfil)
    gas = 0
    eletricos: dict[str, int] = defaultdict(int)
    sem_conta: list[str] = []
    for aparelho, minutos in por_aparelho.items():
        destino = substituto if aparelho == "forno" and substituto else aparelho
        if destino in A_GAS or (destino is None and vai_ao_fogo):
            gas += minutos
        elif destino in parametros.POTENCIA_DO_APARELHO:
            eletricos[destino] += minutos
        else:
            sem_conta.append(f"{minutos} min {_nome_do_aparelho(destino)}")
    if substituto and "forno" in por_aparelho:
        premissa_fonte = (
            f"a senhora não tem forno, e a conta põe o tempo de forno "
            f"{_nome_do_aparelho(substituto)}"
        )
    return _Tempos(
        trabalho=trabalho,
        trabalho_premissa=premissa_trabalho,
        gas=gas,
        eletricos=dict(eletricos),
        fonte_premissa=premissa_fonte,
        sem_conta=tuple(sem_conta),
    )


def _nome_do_aparelho(aparelho: str | None) -> str:
    from mise.taxonomia import EQUIPAMENTOS_POR_ID  # noqa: PLC0415

    if aparelho is None or aparelho not in EQUIPAMENTOS_POR_ID:
        return "sem aparelho definido"
    return f"na {EQUIPAMENTOS_POR_ID[aparelho].nome.lower()}"


# --------------------------------------------------------------------------- #
# As linhas
# --------------------------------------------------------------------------- #


def custo_da_porcao(receita: Receita, avaliacao: Avaliacao) -> CMV:
    """O custo de ingrediente de uma porção, a mesma conta de `mise.cmv.calcular`.

    Sem a exigência da receita conferida: é a conta do preço preliminar. As
    linhas saem das mesmas funções do motor, para o número ser o mesmo que o
    custo por porção vai dar quando a receita for conferida.
    """
    from mise.cmv import CMV, _incerteza_agregada, _linha, _linha_de_compra  # noqa: PLC0415

    divisor = Decimal(receita.rendimento_porcoes)
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
        rendimento_original=receita.rendimento_porcoes,
    )


def _linha_dos_ingredientes(
    receita: Receita, avaliacao: Avaliacao, conta: _Conta
) -> tuple[Linha, Dinheiro | None]:
    perguntas = [p.texto for p in avaliacao.perguntas if p.tipo is TipoRestricao.INGREDIENTE]
    if perguntas or not receita.rendimento_informado:
        for pergunta in perguntas:
            conta.confirmar.setdefault(pergunta)
        motivo = (
            "falta saber quantas porções a receita rende"
            if not receita.rendimento_informado
            else "falta saber o custo de um ingrediente"
        )
        derivacao = f"ainda não dá para somar: {motivo}"
        return Linha("ingredientes", "Ingredientes da porção", None, derivacao), None
    cmv = custo_da_porcao(receita, avaliacao)
    valor = cmv.para_precificar
    derivacao = "a soma das linhas do custo por porção"
    if cmv.e_faixa:
        derivacao += (
            f"; com medidas caseiras, o custo fica entre {cmv.minimo} e {cmv.maximo}, e a "
            "conta usa o maior, para não faltar"
        )
    return Linha("ingredientes", "Ingredientes da porção", valor, derivacao), valor


def _linha_da_mao_de_obra(receita: Receita, tempos: _Tempos, conta: _Conta) -> Linha:
    hora = conta.usar("valor_hora")
    porcoes = receita.rendimento_porcoes
    if tempos.trabalho is None:
        conta.confirmar.setdefault("quanto tempo a receita leva, do começo ao fim")
        return Linha(
            "mao_de_obra",
            "Mão de obra sugerida",
            None,
            "a receita não diz quanto tempo leva; fica de fora da conta",
            ("valor_hora",),
        )
    if hora.valor is None or not receita.rendimento_informado:  # pragma: no cover (há padrão)
        return Linha(
            "mao_de_obra", "Mão de obra sugerida", None, "falta o valor da hora", ("valor_hora",)
        )
    exato = Decimal(tempos.trabalho) / 60 * hora.valor / porcoes
    valor = _para_cima(exato)
    derivacao = (
        f"{tempos.trabalho} min ÷ 60 × {hora.texto} ÷ {_porcoes(porcoes)} = {valor}"
        f"{_arredondado(exato, valor)}"
    )
    if tempos.trabalho_premissa:
        derivacao += f" ({tempos.trabalho_premissa})"
        conta.confirmar.setdefault(f"o tempo de trabalho: {tempos.trabalho_premissa}")
    return Linha("mao_de_obra", "Mão de obra sugerida", valor, derivacao, ("valor_hora",))


def _linha_do_gas(receita: Receita, tempos: _Tempos, conta: _Conta) -> Linha | None:
    if not tempos.gas:
        return None
    preco = conta.usar("botijao_preco")
    horas = conta.usar("botijao_horas")
    nomes = ("botijao_preco", "botijao_horas")
    if preco.valor is None or horas.valor is None:  # pragma: no cover (os dois têm padrão)
        return Linha("gas", "Gás", None, "falta o preço ou a duração do botijão", nomes)
    minuto = parametros.para_cima(preco.valor / (horas.valor * 60), _CASAS_DO_MINUTO)
    porcoes = receita.rendimento_porcoes
    exato = tempos.gas * minuto / porcoes
    valor = _para_cima(exato)
    derivacao = (
        f"botijão de {Dinheiro(preco.valor)} ÷ ({_numero(horas.valor)} h × 60 min) = "
        f"{_centavos(minuto)} por minuto de fogo; {tempos.gas} min × {_centavos(minuto)} ÷ "
        f"{_porcoes(porcoes)} = {valor}{_arredondado(exato, valor)}"
    )
    if tempos.fonte_premissa:
        derivacao += f" ({tempos.fonte_premissa})"
    return Linha("gas", "Gás", valor, derivacao, nomes)


def _linha_da_energia(receita: Receita, tempos: _Tempos, conta: _Conta) -> Linha | None:
    if not tempos.eletricos:
        return None
    from mise.taxonomia import EQUIPAMENTOS_POR_ID  # noqa: PLC0415

    kwh = conta.usar("kwh_preco")
    nomes = ["kwh_preco"]
    partes: list[str] = []
    de_fora: list[str] = []
    total_kwh = Decimal(0)
    for aparelho, minutos in sorted(tempos.eletricos.items()):
        nome = EQUIPAMENTOS_POR_ID[aparelho].nome.lower()
        potencia = conta.usar(parametros.POTENCIA_DO_APARELHO[aparelho])
        nomes.append(potencia.nome)
        if potencia.valor is None:
            de_fora.append(nome)
            continue
        gasto = parametros.para_cima(potencia.valor * minutos / 60_000, _CASAS_DO_KWH)
        total_kwh += gasto
        partes.append(
            f"{nome} de {_numero(potencia.valor)} W por {minutos} min = {_numero(gasto)} kWh"
        )
    fora = f"; {_lista(de_fora)} fica de fora: falta a potência" if de_fora else ""
    if not partes or kwh.valor is None:
        derivacao = f"falta a potência de {_lista(de_fora)}; fica de fora da conta"
        return Linha("energia", "Energia elétrica", None, derivacao, tuple(nomes))
    porcoes = receita.rendimento_porcoes
    exato = total_kwh * kwh.valor / porcoes
    valor = _para_cima(exato)
    derivacao = (
        f"{'; '.join(partes)}; {_numero(total_kwh)} kWh × {_centavos(kwh.valor)} ÷ "
        f"{_porcoes(porcoes)} = {valor}{_arredondado(exato, valor)}{fora}"
    )
    if tempos.fonte_premissa:
        derivacao += f" ({tempos.fonte_premissa})"
    return Linha("energia", "Energia elétrica", valor, derivacao, tuple(nomes))


def _linha_da_embalagem(conta: _Conta) -> Linha:
    embalagem = conta.usar("embalagem_por_porcao")
    if embalagem.valor is None:
        return Linha(
            "embalagem",
            "Embalagem",
            None,
            "a senhora ainda não disse quanto paga na embalagem; fica de fora da conta",
            ("embalagem_por_porcao",),
        )
    valor = _para_cima(embalagem.valor)
    return Linha(
        "embalagem",
        "Embalagem",
        valor,
        f"{valor} por porção, que a senhora informou",
        ("embalagem_por_porcao",),
    )


# --------------------------------------------------------------------------- #
# Os preços
# --------------------------------------------------------------------------- #


def _dividido(valor: Dinheiro, rotulo: str) -> dict[str, Any]:
    exato = valor.valor / RETENCAO
    resultado = _para_cima(exato)
    if exato == resultado.valor:
        derivacao = f"{valor} ÷ 0,90 = {resultado}"
    else:
        derivacao = f"{valor} ÷ 0,90 = {_tres_casas(exato)}, arredondado para cima: {resultado}"
    return {**_dinheiro(resultado), "derivacao": derivacao, "_valor": resultado, "_nome": rotulo}


def _pontos(
    ingrediente: Dinheiro, producao: Dinheiro, piso: Dinheiro, outros: list[str]
) -> list[dict[str, Any]]:
    pontos: list[dict[str, Any]] = []
    for nome, descricao, fracao in FOOD_COSTS_PADRAO:
        pelo_ingrediente = _redondo(ingrediente.valor / fracao)
        fracao_texto = f"{fracao:.2f}".replace(".", ",")
        if pelo_ingrediente.valor >= piso.valor:
            preco = pelo_ingrediente
            inicio = f"{ingrediente} ÷ {fracao_texto} = {preco}"
        else:
            preco = piso
            inicio = (
                f"{ingrediente} ÷ {fracao_texto} daria {pelo_ingrediente}, abaixo do piso de "
                f"{piso}; fica o piso, {piso}"
            )
        # O que chega para ela é 0,90 × preço, no centavo; a taxa é o resto, para
        # as duas somarem o preço na conta que ela lê.
        recebe = _redondo(preco.valor * RETENCAO)
        taxa = preco - recebe
        lucro = recebe - ingrediente
        sobra = recebe - producao
        fim = (
            f"; tirando também {_lista(outros)}, sobram {sobra}"
            if outros
            else "; sem outro custo na conta, a sobra é a mesma"
        )
        pontos.append(
            {
                "nome": nome,
                "descricao": descricao,
                "preco": _dinheiro(preco),
                "taxa": _dinheiro(taxa),
                "recebe": _dinheiro(recebe),
                "lucro": _dinheiro(lucro),
                "sobra_real": _dinheiro(sobra),
                "derivacao": (
                    f"{inicio}; a plataforma fica com {taxa} e chegam {recebe}; tirando "
                    f"{ingrediente} de ingrediente, sobram {lucro}{fim}"
                ),
            }
        )
    return pontos


_DO_QUE_E: Final[dict[str, str]] = {
    "mao_de_obra": "a mão de obra",
    "gas": "o gás",
    "energia": "a energia",
    "embalagem": "a embalagem",
}

_O_QUE_FALTA: Final[dict[str, str]] = {
    "embalagem_por_porcao": "quanto paga na embalagem",
    "potencia_batedeira": "a potência da batedeira",
    "potencia_mixer": "a potência do mixer",
    "potencia_processador": "a potência do processador",
}


def estimar(sessao: Sessao, receita: Receita, *, slug: str | None = None) -> dict[str, Any]:
    """O preço preliminar da receita, na forma de `contratos/web/estimativa.json`.

    Recusa (`EstimativaRecusada`) a receita que a conferência bloqueia. O que
    ainda falta confirmar (uma pergunta da cozinha, o tempo que a receita não
    diz) não impede a estimativa: vai em `sinais.falta_confirmar`.
    """
    from mise.catalogo import id_da_receita  # noqa: PLC0415

    avaliacao = sessao.avaliar(receita)
    if avaliacao.rendimento is not None and avaliacao.rendimento.estimado:
        # Sem o rendimento na receita, a estimativa pelo peso vale aqui também:
        # o rendimento nunca é pergunta, e a premissa vai dita na conta.
        receita = replace(
            receita, rendimento_porcoes=avaliacao.rendimento.porcoes, rendimento_informado=True
        )
    if avaliacao.veredito is Veredito.BLOQUEADO:
        motivos = "; ".join(str(i) for i in avaliacao.impedimentos) or "a conferência não deixa"
        raise EstimativaRecusada(receita.nome, _minuscula(motivos))
    conta = _Conta(parametros.ler(sessao.dossie))
    for pergunta in avaliacao.perguntas:
        if pergunta.tipo is not TipoRestricao.INGREDIENTE:
            conta.confirmar.setdefault(pergunta.texto)
    tempos = _tempos(receita, sessao.perfil)
    ingredientes, c_ing = _linha_dos_ingredientes(receita, avaliacao, conta)
    linhas = [ingredientes, _linha_da_mao_de_obra(receita, tempos, conta)]
    linhas += [
        linha
        for linha in (
            _linha_do_gas(receita, tempos, conta),
            _linha_da_energia(receita, tempos, conta),
        )
        if linha is not None
    ]
    linhas.append(_linha_da_embalagem(conta))
    if not receita.rendimento_informado:
        linhas = [
            Linha(
                linha.id,
                linha.rotulo,
                None,
                "sem saber quantas porções a receita rende, não dá para dividir",
                linha.premissas,
            )
            for linha in linhas
        ]
    for descricao in tempos.sem_conta:
        conta.confirmar.setdefault(f"o custo do tempo {descricao}, que fica de fora da conta")

    agora = sessao.dossie.agora()
    dados: dict[str, Any] = {
        "slug": slug or id_da_receita(receita),
        "prato": receita.nome,
        "preliminar": True,
        "rotulo": ROTULO,
        "linhas": [linha.para_json() for linha in linhas],
        "premissas": [conta.premissas[n].para_json(agora) for n in conta.usadas],
        "custo_producao": None,
        "piso": None,
        "minimo_so_ingrediente": None,
        "pontos": [],
        "referencias_de_mercado": [],
        "referencias_texto": SEM_REFERENCIA,
        "sinais": {
            "mercado_abaixo_do_piso": False,
            "faltam_parametros": list(conta.faltam),
            "falta_confirmar": list(conta.confirmar),
        },
    }
    prato = _minuscula(receita.nome)
    if c_ing is None or not receita.rendimento_informado:
        do_custo = [p.texto for p in avaliacao.perguntas if p.tipo is TipoRestricao.INGREDIENTE]
        if not receita.rendimento_informado:  # pragma: no cover (a estimativa sempre diz)
            do_custo = []
        o_que = next(iter(do_custo), "Quantas porções a receita rende?")
        dados["texto"] = (
            f"Preço preliminar: ainda não consigo estimar a porção de {prato}; antes, "
            f"preciso de uma resposta da senhora. {o_que}"
        )
        return dados

    conhecidas = [linha for linha in linhas if linha.valor is not None]
    producao = Dinheiro.zero()
    for linha in conhecidas:
        assert linha.valor is not None
        producao = producao + linha.valor
    de_fora = [_DO_QUE_E[linha.id] for linha in linhas if linha.valor is None]
    soma = " + ".join(str(linha.valor) for linha in conhecidas)
    dados["custo_producao"] = {
        **_dinheiro(producao),
        "derivacao": (
            f"{soma} = {producao}" if len(conhecidas) > 1 else f"só o ingrediente: {producao}"
        )
        + (f", sem {_lista(de_fora)}" if de_fora else ""),
    }
    piso = _dividido(producao, "piso")
    minimo = _dividido(c_ing, "minimo")
    dados["piso"] = {k: v for k, v in piso.items() if not k.startswith("_")}
    dados["minimo_so_ingrediente"] = {k: v for k, v in minimo.items() if not k.startswith("_")}
    outros = [_DO_QUE_E[linha.id] for linha in conhecidas if linha.id != "ingredientes"]
    dados["pontos"] = _pontos(c_ing, producao, piso["_valor"], outros)
    dados["texto"] = _texto(prato, dados["pontos"], conta)
    return dados


def _texto(prato: str, pontos: list[dict[str, Any]], conta: _Conta) -> str:
    precos = sorted({p["preco"]["valor"]: p["preco"]["texto"] for p in pontos}.items())
    if len(precos) == 1:
        faixa = f"fica em {precos[0][1]}"
    else:
        faixa = f"fica entre {precos[0][1]} e {precos[-1][1]}"
    texto = (
        f"Preço preliminar, sem compromisso: com o que eu sei hoje, a porção de {prato} {faixa}."
    )
    faltam = [_O_QUE_FALTA.get(n, n) for n in conta.faltam]
    if faltam:
        texto += f" Falta a senhora me dizer {_lista(faltam)}."
    if conta.confirmar:
        n = len(conta.confirmar)
        texto += (
            " Ainda falta confirmar uma coisa da receita."
            if n == 1
            else f" Ainda faltam confirmar {n} coisas da receita."
        )
    return texto


def receita_da_estimativa(sessao: Sessao, receita_id: str | None, prato: str | None) -> Receita:
    """A receita pedida: pelo id (em avaliação ou no catálogo), senão pelo nome."""
    from mise.catalogo import Catalogo  # noqa: PLC0415

    if receita_id is not None and receita_id.strip():
        try:
            return sessao.candidata_por_id(receita_id)
        except Ausente:
            guardada = Catalogo(sessao.dossie).obter(receita_id.strip())
            if guardada is None:
                raise
            return guardada.receita
    if prato is not None and prato.strip():
        receita = sessao.dossie.candidata(prato)
        if receita is None:
            raise Ausente(
                "não encontrei essa receita entre as que estão em avaliação",
                prato=prato,
                em_avaliacao=", ".join(sorted(sessao.candidatas)) or "nenhuma",
            )
        return receita
    raise ErroDeUso("informe a receita: o receita_id ou o nome do prato")


__all__ = [
    "A_GAS",
    "ROTULO",
    "SEM_REFERENCIA",
    "EstimativaRecusada",
    "Linha",
    "custo_da_porcao",
    "estimar",
    "receita_da_estimativa",
]
