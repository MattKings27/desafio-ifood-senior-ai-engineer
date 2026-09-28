"""A máscara do rascunho: nenhum dígito de valor em reais aparece antes da conferência.

O que estes testes protegem:

1. A expressão é a do guard-rail, lida do arquivo do plugin: se alguém mudar
   uma, o teste manda mudar a outra.
2. Um valor partido entre dois pedaços nunca mostra um dígito, em qualquer
   partição do texto (propriedade, com textos e cortes aleatórios).
3. O texto final só mantém valor que alguma coisa na conversa sustenta.
"""

from __future__ import annotations

import importlib.util
import json
import re
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from gateway.frases import SENTINELA
from gateway.mascara import (
    PADRAO_DO_VALOR,
    PADRAO_FALADO_DO_PLUGIN,
    REDACAO,
    MascaraDeValores,
    mascarar,
    retirar_sem_procedencia,
    valores_com_cifrao,
    valores_da_fala,
    valores_falados,
)

PLUGIN = (
    Path(__file__).resolve().parents[2]
    / "hermes"
    / "plugins"
    / "guardrail-numerico"
    / "__init__.py"
)


def _plugin() -> ModuleType:
    especificacao = importlib.util.spec_from_file_location("guardrail_do_teste", PLUGIN)
    assert especificacao is not None and especificacao.loader is not None
    modulo = importlib.util.module_from_spec(especificacao)
    especificacao.loader.exec_module(modulo)
    return modulo


def _em_pedacos(texto: str, cortes: list[int]) -> list[str]:
    pontos = sorted({c for c in cortes if 0 < c < len(texto)})
    inicio = 0
    pedacos = []
    for ponto in [*pontos, len(texto)]:
        pedacos.append(texto[inicio:ponto])
        inicio = ponto
    return pedacos


def _transmitir(pedacos: list[str]) -> tuple[str, list[str]]:
    """O que a tela recebe: cada saída, na ordem, e o total."""
    mascara = MascaraDeValores()
    saidas = [mascara.alimentar(p) for p in pedacos]
    saidas.append(mascara.finalizar())
    return "".join(saidas), saidas


# --------------------------------------------------------------------------- #
# A expressão é a do guard-rail                                                #
# --------------------------------------------------------------------------- #


def test_a_expressao_do_valor_e_a_do_plugin() -> None:
    plugin = _plugin()
    assert plugin._VALOR.pattern == PADRAO_DO_VALOR
    assert plugin._VALOR.flags == re.compile(PADRAO_DO_VALOR).flags


def test_a_expressao_do_falado_e_a_do_plugin() -> None:
    plugin = _plugin()
    assert plugin._REAIS_FALADO.pattern == PADRAO_FALADO_DO_PLUGIN
    assert plugin._REAIS_FALADO.flags & re.IGNORECASE


def test_o_plugin_e_o_texto_final_conferem_as_mesmas_quantias_por_extenso() -> None:
    """A segunda versão do guard-rail e a segunda conferência do gateway concordam."""
    plugin = _plugin()
    autorizados = [Decimal(18)]
    estado = plugin.ProvenienciaNumerica(lambda _s: (["R$ 18,00"], []))
    for texto in (
        "Cobre 18 reais.",
        "Cobre 25 reais.",
        "Cobre 12.5 reais.",
        "Fica em 1.234,56 reais ou 1 real.",
        "É quase 1 em cada 8 reais da despensa.",
        "A cada 10 reais, sobra 18 reais.",
    ):
        _, retirados = retirar_sem_procedencia(texto, autorizados)
        assert retirados == len(estado.sem_proveniencia(texto, "")), texto


def test_a_proporcao_nao_e_quantia_no_texto_final() -> None:
    texto = "As alcaparras são quase 1 em cada 8 reais da despensa."
    assert retirar_sem_procedencia(texto, []) == (texto, 0)
    assert retirar_sem_procedencia("Custa 8 reais.", []) == (f"Custa {REDACAO}.", 1)


def test_a_mascara_cobre_tudo_o_que_o_plugin_confere() -> None:
    """Todo valor que o plugin enxerga some da tela, inteiro."""
    plugin = _plugin()
    texto = "Custa R$ 1.234,56, R$ 8,68, R$12, 6 reais e 4,50 reais; R$ 1500,00 também."
    for achado in plugin._VALOR.finditer(texto):
        assert achado.group(0) not in mascarar(texto)
    assert not re.search(r"\d", mascarar(texto))


# --------------------------------------------------------------------------- #
# Casos que doeriam                                                            #
# --------------------------------------------------------------------------- #


def test_valor_partido_entre_dois_pedacos_nao_mostra_digito() -> None:
    total, saidas = _transmitir(["A senhora já colocou R$ 66", "3,39 na despensa."])
    assert saidas[0] == "A senhora já colocou "
    assert total == f"A senhora já colocou {SENTINELA} na despensa."


def test_cifrao_sozinho_no_fim_fica_retido() -> None:
    mascara = MascaraDeValores()
    assert mascara.alimentar("Sai por R") == "Sai por "
    assert mascara.retido == "R"
    assert mascara.alimentar("$") == ""
    assert mascara.alimentar(" 7,") == ""
    assert mascara.retido == "R$ 7,"
    assert mascara.alimentar("50 a porção") == f"{SENTINELA} a porção"
    assert mascara.mascarado == f"Sai por {SENTINELA} a porção"


def test_numero_no_fim_espera_para_saber_se_e_dinheiro() -> None:
    mascara = MascaraDeValores()
    assert mascara.alimentar("São 4,5") == "São "
    assert mascara.alimentar(" rea") == ""
    assert mascara.alimentar("is por quilo") == f"{SENTINELA} por quilo"


def test_numero_que_nao_e_dinheiro_sai_quando_a_frase_segue() -> None:
    mascara = MascaraDeValores()
    assert mascara.alimentar("São 37") == "São "
    assert mascara.alimentar(" itens, 12,36% do total") == "37 itens, 12,36% do total"


def test_palavra_com_r_maiusculo_nao_trava_o_texto() -> None:
    mascara = MascaraDeValores()
    assert mascara.alimentar("Receita da R") == "Receita da "
    assert mascara.alimentar("ua do Sol") == "Rua do Sol"


def test_milhar_sem_ponto_nao_deixa_digito_para_tras() -> None:
    """A `_VALOR` para em "R$ 150" de "R$ 1500,00": o "0,00" não pode aparecer."""
    assert mascarar("Gastou R$ 1500,00 no mês") == f"Gastou {SENTINELA} no mês"
    assert mascarar("R$ 1234 e R$12.5.") == f"{SENTINELA} e {SENTINELA}."
    assert mascarar("R$ 12, 5 itens") == f"{SENTINELA}, 5 itens"


def test_dinheiro_falado_some_inteiro() -> None:
    assert mascarar("Uns 6 reais, 1 real, 1.234 reais e 10 Reais.") == (
        f"Uns {SENTINELA}, {SENTINELA}, {SENTINELA} e {SENTINELA}."
    )
    assert mascarar("5 realmente") == "5 realmente"


def test_finalizar_libera_o_valor_retido_mascarado() -> None:
    mascara = MascaraDeValores()
    assert mascara.alimentar("Fica R$ 18") == "Fica "
    assert mascara.finalizar() == SENTINELA
    assert mascara.finalizar() == ""


# --------------------------------------------------------------------------- #
# Propriedade: nenhuma partição mostra dígito de valor                         #
# --------------------------------------------------------------------------- #


def _reais(inteiro: int, centavos: int | None, milhar: bool) -> str:
    corpo = f"{inteiro:,}".replace(",", ".") if milhar else str(inteiro)
    return corpo if centavos is None else f"{corpo},{centavos:02d}"


_CENTAVOS = st.one_of(st.none(), st.integers(0, 99))
_INTEIRO = st.integers(0, 99_999)

_COM_CIFRAO = st.builds(
    lambda inteiro, centavos, milhar, espaco: f"R${espaco}{_reais(inteiro, centavos, milhar)}",
    _INTEIRO,
    _CENTAVOS,
    st.booleans(),
    st.sampled_from(["", " ", "  ", "\n"]),
)
_FALADO = st.builds(
    lambda inteiro, centavos, milhar, palavra: f"{_reais(inteiro, centavos, milhar)} {palavra}",
    _INTEIRO,
    _CENTAVOS,
    st.booleans(),
    st.sampled_from(["reais", "Reais", "REAIS"]),
) | st.just("1 real")

_VALOR_EM_REAIS = st.one_of(_COM_CIFRAO, _FALADO)

#: Número que não é dinheiro: sempre com a unidade, que nunca começa com "r".
_NUMERO_QUALQUER = st.builds(
    lambda n, unidade: f"{n}{unidade}",
    st.sampled_from(["37", "12,36", "2", "0,5", "1.200", "3"]),
    st.sampled_from([" itens", "%", " kg", " vezes", " porções", "°C", " min"]),
)
_PALAVRA = st.sampled_from(
    ["a", "senhora", "Receita", "custa", "Rua", "R", "prato", "às", "ção", "rapidinho", "(ok)"]
)
#: O travessão entra porque o modelo às vezes o escreve entre dois valores.
_SEPARADOR = st.sampled_from([" ", ", ", ". ", "\n\n", ": ", "; ", "! ", " \u2014 "])


@st.composite
def _texto_com_valores(draw: st.DrawFn) -> tuple[str, str]:
    """(o texto, o que a tela deve mostrar): cada valor vira um sentinela."""
    fichas = draw(
        st.lists(
            st.one_of(
                _VALOR_EM_REAIS.map(lambda v: (v, True)),
                _NUMERO_QUALQUER.map(lambda n: (n, False)),
                _PALAVRA.map(lambda p: (p, False)),
            ),
            min_size=1,
            max_size=14,
        )
    )
    texto, esperado = "", ""
    for ficha, e_valor in fichas:
        separador = draw(_SEPARADOR)
        texto += ficha + separador
        esperado += (SENTINELA if e_valor else ficha) + separador
    return texto, esperado


@settings(max_examples=400, deadline=None)
@given(_texto_com_valores(), st.lists(st.integers(0, 400), max_size=40))
def test_nenhuma_particao_mostra_digito_de_valor(caso: tuple[str, str], cortes: list[int]) -> None:
    texto, esperado = caso
    assert mascarar(texto) == esperado
    mascara = MascaraDeValores()
    mostrado = ""
    for pedaco in _em_pedacos(texto, cortes):
        mostrado += mascara.alimentar(pedaco)
        # Em nenhum instante a tela vê algo que não seja o começo do texto conferido.
        assert esperado.startswith(mostrado)
    mostrado += mascara.finalizar()
    assert mostrado == esperado


@settings(max_examples=200, deadline=None)
@given(_texto_com_valores())
def test_um_caractere_por_vez_tambem_nao_vaza(caso: tuple[str, str]) -> None:
    texto, esperado = caso
    total, _ = _transmitir(list(texto))
    assert total == esperado


# --------------------------------------------------------------------------- #
# A segunda conferência do texto final                                         #
# --------------------------------------------------------------------------- #


def test_valores_lidos_como_o_guard_rail_le() -> None:
    assert valores_com_cifrao("R$ 1.234,56 e R$ 8,68 e R$12") == [
        Decimal("1234.56"),
        Decimal("8.68"),
        Decimal("12"),
    ]
    assert valores_com_cifrao("R$ 1500,00") == [Decimal("1500.00")]
    assert valores_com_cifrao("R$ 12.5") == []
    assert valores_falados("6 reais, 4,50 reais e 1 real") == [
        Decimal("6"),
        Decimal("4.50"),
        Decimal("1"),
    ]
    assert valores_da_fala("a lata sai R$ 6 e o pacote 4 reais") == [Decimal("6"), Decimal("4")]


def test_valor_sustentado_fica_e_o_resto_sai() -> None:
    texto = "O custo é R$ 2,47 e o preço R$ 18,00; de cabeça, uns 9 reais."
    limpo, retirados = retirar_sem_procedencia(texto, {Decimal("2.47"), Decimal("18")})
    assert limpo == f"O custo é R$ 2,47 e o preço R$ 18,00; de cabeça, uns {REDACAO}."
    assert retirados == 1


def test_arredondamento_de_centavo_nao_e_invencao() -> None:
    _, retirados = retirar_sem_procedencia("R$ 2,49", {Decimal("2.47")})
    assert retirados == 0
    _, retirados = retirar_sem_procedencia("R$ 2,50", {Decimal("2.47")})
    assert retirados == 1


def test_numero_que_nao_e_pt_br_nao_tem_como_ser_sustentado() -> None:
    limpo, retirados = retirar_sem_procedencia("R$ 12.5 ou 3.5 reais", {Decimal("12.5")})
    assert limpo == f"{REDACAO} ou {REDACAO}"
    assert retirados == 2


def test_milhar_sem_ponto_e_conferido_inteiro() -> None:
    """O plugin conferiria 150; aqui é 1500 que precisa ter procedência."""
    limpo, retirados = retirar_sem_procedencia("R$ 1500,00", {Decimal("150")})
    assert (limpo, retirados) == (REDACAO, 1)
    assert retirar_sem_procedencia("R$ 1500,00", {Decimal("1500")}) == ("R$ 1500,00", 0)


#: Os exemplos que a máscara do navegador (`webapp/src/lib/conversa/mascara.ts`)
#: também confere, no teste dela. O mesmo arquivo nos dois lados é o que garante
#: que as duas portas escondem os mesmos valores.
_EXEMPLOS_COMPARTILHADOS = json.loads(
    (Path(__file__).resolve().parents[2] / "contratos" / "web" / "mascara.json").read_text(
        encoding="utf-8"
    )
)["casos"]


def _com_sentinela(texto: str) -> str:
    return texto.replace("{S}", SENTINELA)


@pytest.mark.parametrize("caso", _EXEMPLOS_COMPARTILHADOS, ids=lambda caso: caso["texto"])
def test_os_exemplos_que_o_navegador_tambem_confere(caso: dict[str, str]) -> None:
    assert mascarar(caso["texto"]) == _com_sentinela(caso["mascarado"])
    assert MascaraDeValores().alimentar(caso["texto"]) == _com_sentinela(caso["rascunho"])
