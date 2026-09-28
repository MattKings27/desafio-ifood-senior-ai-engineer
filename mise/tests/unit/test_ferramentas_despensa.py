"""As ferramentas da despensa editável na conversa: `atualizar_despensa` e `consultar_planilha`."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from mise.despensa import Despensa
from mise.dinheiro import Dinheiro
from mise.erros import Ausente
from mise.ferramentas.despensa import item_da_conversa
from mise.mcp_server import Sessao, abrir_sessao, construir_servidor

if TYPE_CHECKING:
    from collections.abc import Iterator

PLANILHA = Path(__file__).resolve().parents[3] / "dados" / "despensa_dona_maria.xlsx"


@pytest.fixture
def sessao(tmp_path: Path) -> Iterator[Sessao]:
    s = abrir_sessao(planilha=PLANILHA, banco=tmp_path / "dossie.db")
    yield s
    s.dossie.fechar()


@pytest.fixture
def servidor(sessao: Sessao) -> Any:
    return construir_servidor(sessao)


async def chamar(servidor: Any, ferramenta: str, **argumentos: Any) -> dict[str, Any]:
    resultado = await servidor.call_tool(ferramenta, argumentos)
    corpo: dict[str, Any] = json.loads(resultado.content[0].text)
    return corpo


async def test_informar_a_embalagem_pela_conversa(servidor: Any, sessao: Sessao) -> None:
    corpo = await chamar(
        servidor,
        "atualizar_despensa",
        acao="informar_embalagem",
        ingrediente="cobertura de chocolate",
        conteudo_da_embalagem="1 kg",
    )
    assert corpo["texto"] == "Com 1 kg na embalagem, a cobertura de chocolate sai a R$ 79,90/kg."
    # O peso estimado dá lugar ao dela: não havia pergunta a resolver.
    assert corpo["pendencias_resolvidas"] == []
    assert corpo["antes"]["custo_unitario"] == "R$ 79,90/kg"
    assert corpo["depois"]["custo_unitario"] == "R$ 79,90/kg"
    assert corpo["depois"]["confianca"] == "media"
    assert corpo["orcamento_mudou"] is False
    (evento,) = sessao.editavel.eventos()
    assert evento.canal == "conversa"


async def test_acrescentar_pela_conversa_e_sempre_o_que_ela_ja_tinha(
    servidor: Any, sessao: Sessao
) -> None:
    corpo = await chamar(
        servidor,
        "atualizar_despensa",
        acao="adicionar",
        ingrediente="Farinha de rosca",
        estoque=0.5,
        unidade="kg",
        preco_pago=4.5,
    )
    assert corpo["item"]["origem"] == "ja_tinha"
    assert corpo["item"]["custo_unitario"]["texto"] == "R$ 9,00/kg"
    assert corpo["texto"] == (
        "Anotei a farinha de rosca. Como a senhora já tinha, não mexi nos complementos."
    )
    assert sessao.dossie.orcamento().restante == Dinheiro.de("80.00")


async def test_acabou_corrigir_e_remover_pela_conversa(servidor: Any, sessao: Sessao) -> None:
    acabou = await chamar(servidor, "atualizar_despensa", acao="acabou", ingrediente="o bacon")
    assert acabou["texto"] == "Anotei que o bacon acabou."
    assert acabou["depois"]["estoque"] == "acabou"

    corrigido = await chamar(
        servidor, "atualizar_despensa", acao="corrigir", ingrediente="frango", estoque=1.5
    )
    assert corrigido["ingrediente"] == "Peito de frango"
    assert corrigido["texto"] == "Corrigi o peito de frango. Agora sai a R$ 14,00/kg."

    tirado = await chamar(servidor, "atualizar_despensa", acao="remover", ingrediente="alcaparras")
    assert tirado["removido"] == "alcaparras"
    assert tirado["texto"] == "Tirei as alcaparras da despensa. Não mexi nos complementos."
    assert "Alcaparras" not in sessao.despensa


@pytest.mark.parametrize(
    ("argumentos", "trecho"),
    [
        ({"acao": "comprar", "ingrediente": "bacon"}, "acao desconhecida"),
        ({"acao": "adicionar", "ingrediente": "Nata"}, "estoque"),
        ({"acao": "adicionar", "ingrediente": "Nata", "estoque": 1}, "estoque"),
        ({"acao": "informar_embalagem", "ingrediente": "cobertura de chocolate"}, "quanto vem"),
        ({"acao": "informar_embalagem", "ingrediente": "cobertura"}, "não encontrei"),
        ({"acao": "corrigir", "ingrediente": "caviar", "estoque": 1}, "não encontrei"),
        ({"acao": "corrigir", "ingrediente": "bacon"}, "diga o que mudou"),
    ],
)
async def test_pedido_incompleto_volta_como_erro_para_a_agente(
    servidor: Any, argumentos: dict[str, Any], trecho: str
) -> None:
    corpo = await chamar(servidor, "atualizar_despensa", **argumentos)
    assert corpo["categoria"] == "uso"
    assert trecho in corpo["erro"]


async def test_consultar_planilha_devolve_o_texto_e_grava_o_arquivo(
    servidor: Any, sessao: Sessao
) -> None:
    corpo = await chamar(servidor, "consultar_planilha")
    assert corpo["versao"] == 1
    assert corpo["arquivo"] == str(sessao.arquivo_txt)
    assert corpo["texto"].startswith("DESPENSA DA DONA MARIA")
    assert "Cobertura de chocolate | 1 | un | R$ 79,90" in corpo["texto"]
    # Todo dinheiro no formato que o guard-rail reconhece.
    assert re.search(r"R\$\s*\d+\.\d{2}\b", corpo["texto"]) is None

    await chamar(servidor, "atualizar_despensa", acao="acabou", ingrediente="bacon")
    depois = await chamar(servidor, "consultar_planilha")
    assert depois["versao"] == 2
    assert "Bacon: A senhora avisou que acabou. (pela conversa)" in depois["texto"]


async def test_diagnostico_e_capital_parado_com_a_despensa_vazia(
    servidor: Any, sessao: Sessao
) -> None:
    for item in list(sessao.despensa):
        sessao.editavel.remover(item.id)
    assert len(sessao.despensa) == 0
    corpo = await chamar(servidor, "diagnostico_despensa")
    assert corpo["itens"] == 0
    assert corpo["capital_sem_prato"]["fracao_da_despensa"] == 0.0
    assert corpo["capital_sem_prato"]["dois_maiores"]["parte_de_tudo"] == {
        "fracao": 0.0,
        "texto": "nada pago na despensa ainda",
    }
    assert corpo["total_investido"]["texto"] == "R$ 0,00"


def test_item_da_conversa_pelo_id_pelo_nome_e_sem_chute(despensa: Despensa) -> None:
    assert item_da_conversa(despensa, "alcaparras").nome == "Alcaparras"
    assert item_da_conversa(despensa, "carne moída").nome == "Carne moída (patinho)"
    with pytest.raises(Ausente) as erro:
        item_da_conversa(despensa, "trufa negra")
    assert "confirme com ela" in str(erro.value.contexto["orientacao"])


async def test_custo_de_item_sem_preco_nao_inventa_zero(servidor: Any, sessao: Sessao) -> None:
    sessao.editavel.adicionar(nome="Farinha de rosca", estoque=Decimal("0.5"), unidade="kg")
    corpo = await chamar(servidor, "custo_unitario", ingrediente="farinha de rosca")
    assert corpo["custo_unitario"] == "sem o preço, não dá para saber"
    assert corpo["pago_na_compra"] is None
    assert "pergunta" not in corpo
    cobertura = await chamar(servidor, "custo_unitario", ingrediente="cobertura de chocolate")
    assert cobertura["custo_unitario"] == "R$ 79,90/kg"
    assert "estimativa" in cobertura["derivacao"]
    assert "pergunta" not in cobertura


async def test_resposta_de_ingrediente_ensina_o_caminho_da_despensa(servidor: Any) -> None:
    corpo = await chamar(
        servidor, "registrar_resposta", tipo="ingrediente", campo="Cobertura", resposta="1 kg"
    )
    assert "informar_embalagem" in corpo["contexto"]["embalagem_da_despensa"]
    assert "preco_pago" in corpo["contexto"]["preco_pago_da_despensa"]


async def test_a_conversa_nao_muda_o_valor_de_compra_com_os_80(
    servidor: Any, sessao: Sessao
) -> None:
    from mise.despensa import OrigemDoItem

    compra = sessao.editavel.adicionar(
        nome="Creme de leite",
        estoque=Decimal(2),
        unidade="un 200g",
        quantidade_comprada=Decimal(2),
        preco_pago=Decimal("9.00"),
        origem=OrigemDoItem.ORCAMENTO,
    )
    corpo = await chamar(
        servidor, "atualizar_despensa", acao="corrigir", ingrediente="creme de leite", preco_pago=12
    )
    assert corpo["categoria"] == "uso"
    assert "se corrige na tela" in corpo["erro"]
    assert sessao.dossie.orcamento().restante == Dinheiro.de("71.00")
    # O mesmo valor, ou outra coisa do item, a conversa corrige.
    mesmo = await chamar(
        servidor,
        "atualizar_despensa",
        acao="corrigir",
        ingrediente="creme de leite",
        preco_pago=9,
        estoque=1,
    )
    assert mesmo["mudou"] is True
    # Tirar devolve o valor: é dinheiro que volta, não que sai.
    tirado = await chamar(
        servidor, "atualizar_despensa", acao="remover", ingrediente=compra.item_id
    )
    assert tirado["estorno"]["texto"] == "R$ 9,00"
    assert sessao.dossie.orcamento().restante == Dinheiro.de("80.00")


def test_parte_de_tudo_escreve_a_proporcao_pronta() -> None:
    from mise.ferramentas.despensa import _parte_de_tudo

    assert _parte_de_tudo(Dinheiro.de("161.90"), Decimal("663.39"))["texto"] == (
        "24,4% de tudo o que a senhora pagou"
    )
    assert _parte_de_tudo(Dinheiro.de("0.01"), Decimal("663.39"))["texto"] == (
        "menos de 0,1% de tudo o que a senhora pagou"
    )
