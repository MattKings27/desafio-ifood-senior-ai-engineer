"""As premissas do preço preliminar: o valor da hora dela, o gás, a energia e a embalagem.

Cada premissa tem um de três estados, e a tela e a conversa dizem qual:

- **da senhora** (`dela`): o valor que ela informou na tela, que vale mais que
  qualquer padrão;
- **padrão** (`padrao`): um número público, com a página de onde ele veio, a
  data em que alguém conferiu e o trecho da página, copiado letra por letra.
  `scripts/conferir_conhecimento.py` busca cada página de novo e prova que o
  trecho continua lá;
- **falta** (`falta`): ninguém sabe ainda (quanto ela paga na embalagem). A
  linha que depende dela fica de fora da conta, e a estimativa diz isso.

Os padrões são para ela ter um ponto de partida, e não a verdade da cozinha
dela: o salário mínimo por hora não é o quanto a hora dela vale, e o botijão
da média do país não é o do bairro dela. Por isso todos são editáveis
(`PUT /api/parametros/{nome}`).

Os valores ficam no dossiê, numa tabela deste módulo (`parametros`), com a
data e o canal de cada mudança.
"""

from __future__ import annotations

import datetime as dt
import weakref
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Final

from mise.dinheiro import Dinheiro
from mise.erros import Ausente, ErroDeUso

if TYPE_CHECKING:
    from datetime import datetime

    from mise.dossie import Dossie

ESQUEMA: Final = """
CREATE TABLE IF NOT EXISTS parametros (
    nome        TEXT PRIMARY KEY,
    valor       TEXT NOT NULL,
    registrado  TEXT NOT NULL,
    canal       TEXT NOT NULL DEFAULT 'tela'
);
"""


@dataclass(frozen=True, slots=True)
class FonteDoPadrao:
    """De onde veio um valor padrão: a página, a data da conferência e o trecho literal."""

    titulo: str
    url: str
    verificado_em: dt.date
    #: As palavras da página, como a conferência lê: o texto visível de uma
    #: página HTML, ou as células de uma linha de planilha separadas por " | ".
    trecho: str


@dataclass(frozen=True, slots=True)
class Parametro:
    """Uma premissa do preço preliminar, com o padrão e a faixa que ela pode informar."""

    nome: str
    rotulo: str
    #: `dinheiro` sai como "R$ 7,37 por hora"; `numero`, como "40 horas de fogo".
    tipo: str
    #: O que vem depois do número: "por hora", "o botijão de 13 kg", "W".
    unidade: str
    minimo: Decimal
    maximo: Decimal
    padrao: Decimal | None = None
    fonte: FonteDoPadrao | None = None
    #: O que ela lê sobre o padrão: de onde ele veio, em uma frase.
    sobre_o_padrao: str = ""
    #: Casas decimais do valor mostrado (o kWh tem três: R$ 0,998).
    casas: int = 2

    def texto(self, valor: Decimal) -> str:
        """O valor escrito como ela lê: "R$ 7,37 por hora", "1.500 W", "99,8 centavos por kWh"."""
        if self.tipo == "dinheiro" and self.casas > 2:  # noqa: PLR2004
            centavos = _numero(valor * 100)
            return f"{centavos} centavos {self.unidade}".strip()
        if self.tipo == "dinheiro":
            return f"{Dinheiro(valor)} {self.unidade}".strip()
        return f"{_numero(valor)} {self.unidade}".strip()


def _numero(valor: Decimal) -> str:
    """ "1.500", "0,5", "99,8": inteiro com ponto de milhar, decimal com vírgula."""
    from mise.despensa_json import numero_texto  # noqa: PLC0415

    return numero_texto(valor)


_DIA_DA_CONFERENCIA: Final = dt.date(2026, 9, 26)

#: As premissas, na ordem em que a estimativa as mostra.
PARAMETROS: Final[tuple[Parametro, ...]] = (
    Parametro(
        nome="valor_hora",
        rotulo="Valor da hora da senhora",
        tipo="dinheiro",
        unidade="por hora",
        minimo=Decimal("0.01"),
        maximo=Decimal("1000"),
        padrao=Decimal("7.37"),
        fonte=FonteDoPadrao(
            titulo="Decreto nº 12.797, de 23 de dezembro de 2025 (salário mínimo de 2026)",
            url="https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/decreto/D12797.htm",
            verificado_em=_DIA_DA_CONFERENCIA,
            trecho=(
                "o valor diário do salário mínimo corresponderá a R$ 54,04 (cinquenta e quatro "
                "reais e quatro centavos) e o valor horário, a R$ 7,37 (sete reais e trinta e "
                "sete centavos)"
            ),
        ),
        sobre_o_padrao="o valor de uma hora de salário mínimo em 2026, pelo decreto do governo",
    ),
    Parametro(
        nome="botijao_preco",
        rotulo="Preço do botijão de gás",
        tipo="dinheiro",
        unidade="o botijão de 13 kg",
        minimo=Decimal("1"),
        maximo=Decimal("1000"),
        padrao=Decimal("114.80"),
        fonte=FonteDoPadrao(
            titulo=(
                "ANP, Levantamento de Preços de Combustíveis, semana de 20/09/2026 a "
                "26/09/2026, média do Brasil"
            ),
            url=(
                "https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/"
                "arquivos-lpc/2026/resumo_semanal_lpc_2026-09-20_2026-09-26.xlsx"
            ),
            verificado_em=_DIA_DA_CONFERENCIA,
            trecho="BRASIL | GLP | 3301 | R$/13kg | 114.8",
        ),
        sobre_o_padrao=(
            "o preço médio do botijão de 13 kg no Brasil na semana de 20 a 26 de setembro "
            "de 2026, pela pesquisa da ANP"
        ),
    ),
    Parametro(
        nome="botijao_horas",
        rotulo="Quanto tempo o botijão dura no fogo",
        tipo="numero",
        unidade="horas de fogo",
        minimo=Decimal("1"),
        maximo=Decimal("1000"),
        padrao=Decimal("40"),
        fonte=FonteDoPadrao(
            titulo=("Sindigás, Qual é a média de duração de um botijão de gás em uma residência?"),
            url="https://www.sindigas.org.br/?p=40399",
            verificado_em=_DIA_DA_CONFERENCIA,
            trecho=(
                "De acordo com especialistas, o tempo de uso total de um botijão deste tamanho "
                "é de aproximadamente 40 horas ininterruptas."
            ),
        ),
        sobre_o_padrao=(
            "o Sindigás diz que um botijão de 13 kg dura cerca de 40 horas de uso sem parar"
        ),
    ),
    Parametro(
        nome="kwh_preco",
        rotulo="Preço da energia elétrica",
        tipo="dinheiro",
        unidade="por kWh",
        minimo=Decimal("0.05"),
        maximo=Decimal("10"),
        padrao=Decimal("0.998"),
        fonte=FonteDoPadrao(
            titulo=(
                "Canal Solar, ANEEL eleva para 9,4% projeção de alta das tarifas de energia "
                "em 2026 (dados do boletim InfoTarifas da ANEEL)"
            ),
            url="https://canalsolar.com.br/aneel-eleva-94-alta-tarifas-energia/",
            verificado_em=_DIA_DA_CONFERENCIA,
            trecho=(
                "O InfoTarifas também mostra que a tarifa residencial B1 alcançou R$ 998/MWh "
                "em 2026, antes da incidência de tributos."
            ),
        ),
        sobre_o_padrao=(
            "a tarifa residencial média do país em 2026, sem os impostos da conta de luz, "
            "pelo boletim da ANEEL"
        ),
        casas=3,
    ),
    Parametro(
        nome="potencia_air_fryer",
        rotulo="Potência da air fryer",
        tipo="numero",
        unidade="W",
        minimo=Decimal("100"),
        maximo=Decimal("10000"),
        padrao=Decimal("1500"),
        fonte=FonteDoPadrao(
            titulo="Calculadora de Energia, Quanto gasta uma air fryer?",
            url="https://calculadoradeenergia.com/artigos/quanto-gasta-uma-air-fryer",
            verificado_em=_DIA_DA_CONFERENCIA,
            trecho="vamos considerar uma air fryer comum de 1500W",
        ),
        sobre_o_padrao="a potência de uma air fryer comum; a da senhora está na etiqueta dela",
    ),
    Parametro(
        nome="potencia_forno_eletrico",
        rotulo="Potência do forno elétrico",
        tipo="numero",
        unidade="W",
        minimo=Decimal("100"),
        maximo=Decimal("10000"),
        padrao=Decimal("1500"),
        fonte=FonteDoPadrao(
            titulo="ValorFinal, Tabela de Potência dos Aparelhos",
            url="https://valorfinal.com.br/tabela-potencia-aparelhos",
            verificado_em=_DIA_DA_CONFERENCIA,
            trecho="Forno eletrico 1.500 W 1.000 W a 2.200 W",
        ),
        sobre_o_padrao=(
            "a potência típica de um forno elétrico numa tabela de referência; a do forno "
            "da senhora está na etiqueta dele"
        ),
    ),
    Parametro(
        nome="potencia_microondas",
        rotulo="Potência do micro-ondas",
        tipo="numero",
        unidade="W",
        minimo=Decimal("100"),
        maximo=Decimal("10000"),
        padrao=Decimal("1300"),
        fonte=FonteDoPadrao(
            titulo="ValorFinal, Tabela de Potência dos Aparelhos",
            url="https://valorfinal.com.br/tabela-potencia-aparelhos",
            verificado_em=_DIA_DA_CONFERENCIA,
            trecho="Micro-ondas 1.300 W 700 W a 1.500 W",
        ),
        sobre_o_padrao=(
            "a potência típica de um micro-ondas numa tabela de referência; a do aparelho "
            "da senhora está na etiqueta dele"
        ),
    ),
    Parametro(
        nome="potencia_liquidificador",
        rotulo="Potência do liquidificador",
        tipo="numero",
        unidade="W",
        minimo=Decimal("50"),
        maximo=Decimal("5000"),
        padrao=Decimal("400"),
        fonte=FonteDoPadrao(
            titulo="ValorFinal, Tabela de Potência dos Aparelhos",
            url="https://valorfinal.com.br/tabela-potencia-aparelhos",
            verificado_em=_DIA_DA_CONFERENCIA,
            trecho="Liquidificador 400 W 250 W a 900 W",
        ),
        sobre_o_padrao=(
            "a potência típica de um liquidificador numa tabela de referência; a do dela "
            "está na etiqueta"
        ),
    ),
    Parametro(
        nome="potencia_batedeira",
        rotulo="Potência da batedeira",
        tipo="numero",
        unidade="W",
        minimo=Decimal("50"),
        maximo=Decimal("5000"),
    ),
    Parametro(
        nome="potencia_mixer",
        rotulo="Potência do mixer",
        tipo="numero",
        unidade="W",
        minimo=Decimal("50"),
        maximo=Decimal("5000"),
    ),
    Parametro(
        nome="potencia_processador",
        rotulo="Potência do processador",
        tipo="numero",
        unidade="W",
        minimo=Decimal("50"),
        maximo=Decimal("5000"),
    ),
    Parametro(
        nome="porcao_padrao_g",
        rotulo="Peso de uma porção",
        tipo="numero",
        unidade="g por porção",
        minimo=Decimal("50"),
        maximo=Decimal("2000"),
        padrao=Decimal("350"),
        sobre_o_padrao=(
            "estimativa da plataforma para uma marmita, usada só quando a receita não diz "
            "quantas porções rende; a senhora pode mudar"
        ),
        casas=0,
    ),
    Parametro(
        nome="embalagem_por_porcao",
        rotulo="Embalagem por porção",
        tipo="dinheiro",
        unidade="por porção",
        minimo=Decimal("0"),
        maximo=Decimal("100"),
    ),
)

PARAMETROS_POR_NOME: Final[dict[str, Parametro]] = {p.nome: p for p in PARAMETROS}

#: As premissas que a plataforma assume sem número público por trás: o peso de
#: uma marmita não tem fonte oficial. O padrão delas é dito como estimativa da
#: plataforma (`sobre_o_padrao`), e ela muda; todos os outros padrões têm fonte.
SEM_FONTE_PUBLICA: Final = frozenset({"porcao_padrao_g"})

#: A potência de cada aparelho elétrico, pelo id do equipamento na cozinha.
POTENCIA_DO_APARELHO: Final[dict[str, str]] = {
    "air_fryer": "potencia_air_fryer",
    "forno_eletrico": "potencia_forno_eletrico",
    "microondas": "potencia_microondas",
    "liquidificador": "potencia_liquidificador",
    "batedeira": "potencia_batedeira",
    "mixer": "potencia_mixer",
    "processador": "potencia_processador",
}


@dataclass(frozen=True, slots=True)
class Premissa:
    """Uma premissa com o valor de agora e de onde ele veio."""

    parametro: Parametro
    valor: Decimal | None
    #: `dela`, `padrao` ou `falta`.
    origem: str
    registrado: datetime | None = None

    @property
    def nome(self) -> str:
        return self.parametro.nome

    @property
    def conhecida(self) -> bool:
        return self.valor is not None

    @property
    def texto(self) -> str:
        return self.parametro.texto(self.valor) if self.valor is not None else ""

    @property
    def fonte(self) -> str | None:
        """O que ela lê sobre a origem do número."""
        if self.origem == "dela":
            return "informado pela senhora"
        if self.origem == "padrao":
            return self.parametro.sobre_o_padrao or None
        return None

    def para_json(self, agora: datetime) -> dict[str, Any]:
        """A forma de `contratos/web/estimativa.json#premissas[]`."""
        from mise.despensa_json import quando_texto  # noqa: PLC0415

        atualizado: str | None = None
        if self.origem == "dela" and self.registrado is not None:
            atualizado = quando_texto(self.registrado, agora)
        elif self.origem == "padrao" and self.parametro.fonte is not None:
            atualizado = f"conferido em {self.parametro.fonte.verificado_em:%d/%m/%Y}"
        fonte_url = (
            self.parametro.fonte.url
            if self.origem == "padrao" and self.parametro.fonte is not None
            else None
        )
        return {
            "nome": self.nome,
            "rotulo": self.parametro.rotulo,
            "valor": (
                {"valor": float(self.valor), "texto": self.texto}
                if self.valor is not None
                else None
            ),
            "origem": self.origem,
            "fonte": self.fonte,
            "fonte_url": fonte_url,
            "atualizado_texto": atualizado,
            "editavel": True,
        }


#: Os dossiês em que a tabela já foi conferida neste processo.
_GARANTIDOS: weakref.WeakSet[Dossie] = weakref.WeakSet()


def garantir(dossie: Dossie) -> None:
    """Cria a tabela das premissas no dossiê, se ainda não existir (uma vez por dossiê)."""
    if dossie not in _GARANTIDOS:
        dossie.garantir_esquema(ESQUEMA)
        _GARANTIDOS.add(dossie)


def parametro(nome: str) -> Parametro:
    """O parâmetro pelo nome; `Ausente` se não existe."""
    achado = PARAMETROS_POR_NOME.get(nome)
    if achado is None:
        raise Ausente("não conheço essa premissa do preço", nome=nome)
    return achado


def ler(dossie: Dossie) -> dict[str, Premissa]:
    """Todas as premissas de agora: o que ela informou, senão o padrão, senão falta."""
    from datetime import datetime  # noqa: PLC0415

    garantir(dossie)
    with dossie.cursor() as cur:
        dela = {
            linha["nome"]: (Decimal(linha["valor"]), datetime.fromisoformat(linha["registrado"]))
            for linha in cur.execute("SELECT nome, valor, registrado FROM parametros")
        }
    premissas: dict[str, Premissa] = {}
    for p in PARAMETROS:
        if p.nome in dela:
            valor, quando = dela[p.nome]
            premissas[p.nome] = Premissa(p, valor, "dela", quando)
        elif p.padrao is not None:
            premissas[p.nome] = Premissa(p, p.padrao, "padrao")
        else:
            premissas[p.nome] = Premissa(p, None, "falta")
    return premissas


def definir(dossie: Dossie, nome: str, valor: object, canal: str = "tela") -> Premissa:
    """Grava o valor que ela informou; `None` apaga, e a premissa volta ao padrão.

    O valor tem de ser número dentro da faixa do parâmetro: "80 bocas" não vira
    premissa, vira a pergunta de novo.
    """
    alvo = parametro(nome)
    if valor is None:
        garantir(dossie)
        with dossie.cursor() as cur:
            cur.execute("DELETE FROM parametros WHERE nome = ?", (nome,))
        return ler(dossie)[nome]
    numero = _decimal(valor)
    if numero is None:
        raise ErroDeUso("esse valor não é um número", nome=nome, recebido=valor)
    if not alvo.minimo <= numero <= alvo.maximo:
        raise ErroDeUso(
            f"{alvo.rotulo.lower()} fora da faixa que eu consigo usar",
            nome=nome,
            minimo=str(alvo.minimo),
            maximo=str(alvo.maximo),
        )
    garantir(dossie)
    with dossie.cursor() as cur:
        cur.execute(
            "INSERT INTO parametros (nome, valor, registrado, canal) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(nome) DO UPDATE SET valor = excluded.valor, "
            "registrado = excluded.registrado, canal = excluded.canal",
            (nome, str(numero), dossie.agora().isoformat(), canal),
        )
    return ler(dossie)[nome]


def _decimal(valor: object) -> Decimal | None:
    """O número informado, como `Decimal`; texto, booleano e infinito não servem."""
    if isinstance(valor, bool) or not isinstance(valor, int | float | Decimal):
        return None
    try:
        numero = Decimal(str(valor))
    except InvalidOperation:  # pragma: no cover (int, float e Decimal sempre convertem)
        return None
    return numero if numero.is_finite() else None


def para_cima(valor: Decimal, casas: int) -> Decimal:
    """Arredonda para cima na casa pedida: a premissa de custo nunca desce."""
    return valor.quantize(Decimal(1).scaleb(-casas), rounding=ROUND_CEILING)


__all__ = [
    "PARAMETROS",
    "PARAMETROS_POR_NOME",
    "POTENCIA_DO_APARELHO",
    "SEM_FONTE_PUBLICA",
    "FonteDoPadrao",
    "Parametro",
    "Premissa",
    "definir",
    "garantir",
    "ler",
    "para_cima",
    "parametro",
]
