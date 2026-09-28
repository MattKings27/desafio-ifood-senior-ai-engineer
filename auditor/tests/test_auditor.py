"""O par A2A que confere a conta.

O teste mais importante deste arquivo não mede conta nenhuma: é
`test_o_auditor_nao_importa_o_motor`. A independência é a propriedade que faz a
conferência valer alguma coisa: conferir com o mesmo código que produziu o
número não é auditoria, é tautologia, e um erro de fórmula passaria pelos dois
lados sem deixar rastro.
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from auditor.cartao import VERSAO_A2A, cartao
from auditor.conferencia import RETENCAO, TAXA, conferir, conferir_cmv, conferir_preco
from auditor.servidor import (
    ERRO_METODO_NAO_ENCONTRADO,
    ERRO_PARAMETRO_INVALIDO,
    ERRO_REQUISICAO_INVALIDA,
    criar_app,
)

FONTE = Path(__file__).resolve().parents[1] / "src" / "auditor"

#: O prato do roteiro da demo, com os números já conferidos à mão.
PRATO = {
    "linhas": [
        {"ingrediente": "peito de frango", "custo": "1.75"},
        {"ingrediente": "queijo mussarela", "custo": "2.00"},
        {"ingrediente": "farinha de trigo", "custo": "0.16"},
        {"ingrediente": "ovos", "custo": "0.40"},
    ],
    "cmv": "4.31",
    "preco": "12.31",
    "lucro": "6.77",
}


# --------------------------------------------------------------------------- #
# A propriedade central                                                        #
# --------------------------------------------------------------------------- #


def test_o_auditor_nao_importa_o_motor() -> None:
    """Independência não é convenção: é verificada.

    Se um dia alguém importar `mise.preco` aqui para "não repetir código", a
    conferência deixa de conferir e ninguém percebe, porque os dois lados
    passariam a concordar por construção.
    """
    proibidos: list[str] = []
    for arquivo in FONTE.rglob("*.py"):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                proibidos += [a.name for a in no.names if a.name.split(".")[0] == "mise"]
            elif isinstance(no, ast.ImportFrom) and (no.module or "").split(".")[0] == "mise":
                proibidos.append(no.module or "")

    assert not proibidos, (
        f"o auditor importou {proibidos}: conferir com o mesmo código "
        "que produziu o número não é auditoria"
    )


def test_a_taxa_vem_do_enunciado() -> None:
    """10% sobre a venda; ela recebe 0,90·P."""
    assert TAXA == Decimal("0.10")
    assert RETENCAO == Decimal("0.90")


# --------------------------------------------------------------------------- #
# Conferência do CMV                                                           #
# --------------------------------------------------------------------------- #


def test_cmv_que_fecha_confere() -> None:
    veredito = conferir_cmv(PRATO["linhas"], Decimal("4.31"))
    assert veredito.confere
    assert "4 linhas somam" in veredito.observacao


def test_total_que_nao_fecha_com_as_linhas() -> None:
    """Já aconteceu neste repositório: a compra complementar era somada por fora."""
    veredito = conferir_cmv(PRATO["linhas"], Decimal("3.00"))
    assert not veredito.confere
    assert veredito.divergencias[0].diferenca == Decimal("1.31")


def test_arredondamento_de_um_centavo_e_tolerado() -> None:
    """Duas implementações arredondam diferente; um centavo é ruído legítimo."""
    assert conferir_cmv(PRATO["linhas"], Decimal("4.32")).confere


def test_dois_centavos_ja_e_formula_diferente() -> None:
    assert not conferir_cmv(PRATO["linhas"], Decimal("4.33")).confere


def test_linha_sem_custo_e_recusada() -> None:
    veredito = conferir_cmv([{"ingrediente": "misterioso"}], Decimal("1.00"))
    assert not veredito.confere
    assert "sem custo" in veredito.observacao


def test_sem_linha_nenhuma_nao_confere() -> None:
    assert not conferir_cmv([], Decimal("4.31")).confere


# --------------------------------------------------------------------------- #
# Conferência do preço                                                         #
# --------------------------------------------------------------------------- #


def test_as_duas_formulas_do_enunciado() -> None:
    """`P >= CMV/0,90` e `lucro = 0,90·P - CMV`, recalculadas do texto."""
    veredito = conferir_preco(Decimal("4.31"), Decimal("12.31"), Decimal("6.77"))
    assert veredito.confere
    assert "4.79" in veredito.observacao  # o mínimo


def test_lucro_inflado_e_pego() -> None:
    veredito = conferir_preco(Decimal("4.31"), Decimal("12.31"), Decimal("9.99"))
    assert not veredito.confere
    assert veredito.divergencias[0].campo == "lucro"


def test_preco_abaixo_do_minimo_e_pego() -> None:
    """Cobrar o CMV mais um pouco **perde** dinheiro, e é o erro mais comum.

    Aqui o motor ainda mostrou lucro onde há prejuízo: a conta não bate e o
    preço é segurado. O prejuízo vem avisado junto.
    """
    veredito = conferir_preco(Decimal("4.31"), Decimal("4.50"), Decimal("0.19"))
    assert not veredito.confere
    assert veredito.divergencias[0].campo == "lucro"
    assert veredito.da_prejuizo
    assert "mínimo" in veredito.aviso


def test_um_centavo_de_prejuizo_nao_passa_sem_aviso() -> None:
    """R$ 8,68 de custo a R$ 9,64: ela recebe R$ 8,676 e perde dinheiro.

    O arredondamento meio-para-cima com um centavo de tolerância aprovava isto
    calado. A conta mostrada (lucro de R$ 0,00) está certa no centavo; o aviso de
    prejuízo é conferido sem tolerância nenhuma.
    """
    veredito = conferir_preco(Decimal("8.68"), Decimal("9.64"), Decimal("0.00"))
    assert veredito.confere
    assert veredito.da_prejuizo
    assert "R$ 9,65" in veredito.aviso
    no_minimo = conferir_preco(Decimal("8.68"), Decimal("9.65"), Decimal("0.01"))
    assert no_minimo.confere
    assert not no_minimo.da_prejuizo
    assert no_minimo.aviso == ""


def test_abaixo_do_minimo_com_a_conta_certa_e_escolha_dela() -> None:
    """O enunciado deixa a decisão com ela: o auditor avisa, não segura o preço."""
    veredito = conferir_preco(Decimal("4.31"), Decimal("4.50"), Decimal("-0.26"))
    assert veredito.confere
    assert veredito.divergencias == ()
    assert veredito.da_prejuizo
    assert veredito.aviso == (
        "abaixo do mínimo sem prejuízo: a R$ 4,50 ela perde dinheiro em cada venda; "
        "o mínimo é R$ 4,79"
    )
    assert str(veredito) == f"confere; {veredito.aviso}"


def test_preco_com_folga_nao_tem_aviso() -> None:
    veredito = conferir_preco(Decimal("4.31"), Decimal("12.31"), Decimal("6.77"))
    assert (veredito.da_prejuizo, veredito.aviso) == (False, "")


def test_aviso_escreve_reais_como_no_brasil() -> None:
    veredito = conferir_preco(Decimal("1500"), Decimal("1200"), Decimal("-420"))
    assert "a R$ 1.200,00 ela perde" in veredito.aviso
    assert "o mínimo é R$ 1.666,67" in veredito.aviso


def test_preco_exatamente_no_minimo_confere() -> None:
    minimo = Decimal("4.79")
    lucro = (Decimal("0.90") * minimo - Decimal("4.31")).quantize(Decimal("0.01"))
    assert conferir_preco(Decimal("4.31"), minimo, lucro).confere


def test_divergencia_mostra_os_dois_lados() -> None:
    d = conferir_preco(Decimal("4.31"), Decimal("12.31"), Decimal("9.99")).divergencias[0]
    assert "o motor diz" in str(d)
    assert "eu calculo" in str(d)


# --------------------------------------------------------------------------- #
# Prato inteiro                                                                #
# --------------------------------------------------------------------------- #


def test_prato_completo_confere() -> None:
    assert conferir(PRATO).confere


def test_prato_sem_preco_confere_so_o_cmv() -> None:
    veredito = conferir({k: v for k, v in PRATO.items() if k not in {"preco", "lucro"}})
    assert veredito.confere


def test_prato_sem_linhas_e_recusado() -> None:
    assert not conferir({"cmv": "4.31"}).confere


def test_total_que_nao_fecha_segura_antes_de_olhar_o_preco() -> None:
    veredito = conferir(dict(PRATO, cmv="3.00"))
    assert not veredito.confere
    assert veredito.divergencias[0].campo == "total do CMV"


def test_faixa_confere_as_linhas_com_o_total_delas_e_o_preco_com_o_topo() -> None:
    """Numa faixa, o preço sai do topo (R$ 5,00), e as linhas somam R$ 4,31.

    Comparar as linhas com o topo acusava uma diferença que não é erro e
    segurava um preço certo. O preço é conferido sobre o topo:
    0,90 x 12,50 - 5,00 = 6,25.
    """
    veredito = conferir(
        dict(PRATO, total_das_linhas="4.31", cmv="5.00", preco="12.50", lucro="6.25")
    )
    assert veredito.confere, veredito
    assert "4 linhas somam 4.31" in veredito.observacao
    assert "o preço parte de 5.00, o topo da faixa" in veredito.observacao


def test_faixa_ainda_pega_linha_que_nao_fecha_com_o_total_delas() -> None:
    veredito = conferir(dict(PRATO, total_das_linhas="4.00", cmv="5.00"))
    assert not veredito.confere
    assert veredito.divergencias[0].campo == "total do CMV"


def test_custo_do_preco_abaixo_da_soma_das_linhas_nao_confere() -> None:
    """Preço que parte de um custo menor que o das linhas dá prejuízo escondido."""
    veredito = conferir(dict(PRATO, total_das_linhas="4.31", cmv="4.20"))
    assert not veredito.confere
    assert veredito.divergencias[0].campo == "custo usado no preço"


def test_uma_linha_so_soma_no_singular() -> None:
    linha = [{"ingrediente": "leite condensado", "custo": "6.50"}]
    assert conferir({"linhas": linha, "cmv": "6.50"}).observacao == "1 linha soma 6.50"


def test_prato_inteiro_abaixo_do_minimo_confere_com_aviso() -> None:
    veredito = conferir(dict(PRATO, preco="4.50", lucro="-0.26"))
    assert veredito.confere
    assert veredito.da_prejuizo
    assert "R$ 4,79" in veredito.aviso
    assert "4 linhas somam" in veredito.observacao


def test_veredito_se_apresenta() -> None:
    assert str(conferir(PRATO)) == "confere"
    assert "não confere" in str(conferir(dict(PRATO, lucro="9.99")))


# --------------------------------------------------------------------------- #
# Transporte A2A                                                               #
# --------------------------------------------------------------------------- #


@pytest.fixture
def cliente() -> TestClient:
    return TestClient(criar_app())


def test_cartao_no_lugar_que_a_especificacao_manda(cliente: TestClient) -> None:
    resposta = cliente.get("/.well-known/agent-card.json")
    assert resposta.status_code == 200
    assert resposta.json()["protocolVersion"] == VERSAO_A2A


def test_o_cartao_declara_o_que_nao_tem() -> None:
    """Anunciar capacidade inexistente quebra o par, não o próprio."""
    capacidades = cartao()["capabilities"]
    assert capacidades["streaming"] is False
    assert capacidades["pushNotifications"] is False


def test_cartao_lista_as_habilidades() -> None:
    ids = {s["id"] for s in cartao()["skills"]}
    assert ids == {"conferir-cmv", "conferir-preco"}
    assert all(s["examples"] for s in cartao()["skills"])


def test_mensagem_com_parte_de_dados(cliente: TestClient) -> None:
    corpo = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {"message": {"parts": [{"kind": "data", "data": PRATO}]}},
    }
    r = cliente.post("/a2a", json=corpo).json()
    assert r["result"]["parts"][1]["data"]["confere"] is True
    assert r["id"] == 1


def test_divergencia_volta_estruturada(cliente: TestClient) -> None:
    corpo = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "message/send",
        "params": {"prato": dict(PRATO, lucro="9.99")},
    }
    dados = cliente.post("/a2a", json=corpo).json()["result"]["parts"][1]["data"]
    assert dados["confere"] is False
    assert dados["divergencias"][0]["campo"] == "lucro"
    assert dados["divergencias"][0]["diferenca"] == "3.22"


def test_aviso_de_prejuizo_volta_pelo_a2a(cliente: TestClient) -> None:
    corpo = {
        "jsonrpc": "2.0",
        "id": 8,
        "method": "message/send",
        "params": {"prato": dict(PRATO, preco="4.50", lucro="-0.26")},
    }
    dados = cliente.post("/a2a", json=corpo).json()["result"]["parts"][1]["data"]
    assert dados["confere"] is True
    assert dados["da_prejuizo"] is True
    assert "mínimo" in dados["aviso"]


def test_metodo_desconhecido_usa_o_codigo_padrao(cliente: TestClient) -> None:
    """Código do JSON-RPC, não inventado: cliente genérico sabe tratar."""
    r = cliente.post("/a2a", json={"jsonrpc": "2.0", "id": 3, "method": "tasks/get"}).json()
    assert r["error"]["code"] == ERRO_METODO_NAO_ENCONTRADO


def test_versao_errada_do_protocolo(cliente: TestClient) -> None:
    corpo = {"jsonrpc": "1.0", "id": 4, "method": "message/send"}
    r = cliente.post("/a2a", json=corpo).json()
    assert r["error"]["code"] == ERRO_REQUISICAO_INVALIDA


def test_sem_prato_nos_parametros(cliente: TestClient) -> None:
    r = cliente.post("/a2a", json={"jsonrpc": "2.0", "id": 5, "method": "message/send"}).json()
    assert r["error"]["code"] == ERRO_PARAMETRO_INVALIDO


def test_numero_ilegivel_nao_derruba_o_auditor(cliente: TestClient) -> None:
    corpo = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "message/send",
        "params": {"prato": {"linhas": [{"ingrediente": "x", "custo": "não é número"}]}},
    }
    r = cliente.post("/a2a", json=corpo).json()
    assert r["error"]["code"] == ERRO_PARAMETRO_INVALIDO


def test_parte_de_texto_sem_dados_e_ignorada(cliente: TestClient) -> None:
    corpo = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "message/send",
        "params": {"message": {"parts": [{"kind": "text", "text": "confere aí"}]}},
    }
    assert cliente.post("/a2a", json=corpo).json()["error"]["code"] == ERRO_PARAMETRO_INVALIDO
