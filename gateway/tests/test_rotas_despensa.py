"""As rotas da despensa: a forma do contrato, os R$ 80,00, desfazer e a chave de idempotência.

A forma é conferida contra `contratos/web/despensa*.json`, os mesmos arquivos que
os testes da tela leem: todo campo do contrato existe na resposta, com o mesmo
tipo. Campo a mais é permitido (a tela ignora); campo a menos ou de outro tipo
quebra aqui antes de quebrar lá.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gateway.http import criar_app

RAIZ = Path(__file__).resolve().parents[2]
PLANILHA = RAIZ / "dados" / "despensa_dona_maria.xlsx"
CONTRATOS = RAIZ / "contratos" / "web"

#: Campos que o contrato mostra preenchidos e que podem vir `null`: a foto (que
#: chega com a busca de imagens), o que ela pagou e o custo, num item que ela já
#: tinha e de que não disse o preço, a pergunta de um item (só o que tem
#: pendência traz uma), o cursor da última página de mudanças, e a compra e o
#: estorno de uma escrita que não mexe nos R$ 80,00.
ANULAVEIS = frozenset(
    {
        "imagem",
        "pago",
        "custo_unitario",
        "pendencia",
        "proximo_cursor",
        "compra",
        "estorno",
        # A receita que não diz o tempo, e a que ela ainda não avaliou: o card vem sem eles
        # (`string | null` e `Pontuacao | null` no tipo da tela).
        "tempo_texto",
        "pontuacao",
        "gosta",
    }
)

CREME = {
    "nome": "Creme de leite",
    "estoque": 2,
    "unidade": "un 200g",
    "quantidade_comprada": 2,
    "preco_pago": 9.0,
    "origem": "orcamento",
}


def contrato(nome: str) -> Any:
    return json.loads((CONTRATOS / nome).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# A forma do contrato
# --------------------------------------------------------------------------- #


def _tipo(valor: object) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return "bool"
    if isinstance(valor, int | float):
        return "number"
    if isinstance(valor, str):
        return "string"
    if isinstance(valor, list):
        return "array"
    return "object"


@dataclass
class Forma:
    """Os tipos que um campo teve nos exemplos, e a forma dos campos e dos itens dele."""

    tipos: set[str] = field(default_factory=set)
    campos: dict[str, Forma] = field(default_factory=dict)
    obrigatorios: set[str] | None = None
    item: Forma | None = None


def forma_de(valor: object) -> Forma:
    forma = Forma(tipos={_tipo(valor)})
    if isinstance(valor, dict):
        forma.campos = {k: forma_de(v) for k, v in valor.items()}
        forma.obrigatorios = set(valor)
    elif isinstance(valor, list):
        for elemento in valor:
            forma.item = juntar(forma.item, forma_de(elemento))
    return forma


def juntar(a: Forma | None, b: Forma) -> Forma:
    if a is None:
        return b
    campos = dict(a.campos)
    for chave, forma in b.campos.items():
        campos[chave] = juntar(campos.get(chave), forma)
    obrigatorios = (
        a.obrigatorios & b.obrigatorios
        if a.obrigatorios is not None and b.obrigatorios is not None
        else a.obrigatorios
        if a.obrigatorios is not None
        else b.obrigatorios
    )
    item = juntar(a.item, b.item) if b.item is not None else a.item
    return Forma(a.tipos | b.tipos, campos, obrigatorios, item)


def conferir(forma: Forma, valor: object, caminho: str = "dados") -> None:
    nome = caminho.rsplit(".", 1)[-1].split("[", 1)[0]
    if nome == "imagem" and forma.tipos == {"null"} and valor is not None:
        # A foto tem a mesma forma em todo contrato (`{url, credito}` ou `null`):
        # o exemplo de um item sem foto não proíbe a foto do item que tem.
        forma = forma_de({"url": "/motor/imagens/0", "credito": "Foto: x"})
    aceitos = forma.tipos | ({"null"} if nome in ANULAVEIS else set())
    assert _tipo(valor) in aceitos, f"{caminho}: {_tipo(valor)} não é {sorted(aceitos)}"
    if isinstance(valor, dict):
        for chave in forma.obrigatorios or ():
            assert chave in valor, f"{caminho}.{chave} faltando"
        for chave, sub in forma.campos.items():
            if chave in valor:
                conferir(sub, valor[chave], f"{caminho}.{chave}")
    elif isinstance(valor, list) and forma.item is not None:
        for n, elemento in enumerate(valor):
            conferir(forma.item, elemento, f"{caminho}[{n}]")


def conferir_contrato(exemplo: object, resposta: object) -> None:
    conferir(forma_de(exemplo), resposta)


def test_o_conferidor_de_forma_pega_campo_faltando_e_tipo_errado() -> None:
    exemplo = {"itens": [{"id": "a", "valor": 1, "foto": None}, {"id": "b", "valor": 2.5}]}
    conferir_contrato(exemplo, {"itens": [{"id": "x", "valor": 3, "extra": True}]})
    with pytest.raises(AssertionError, match="faltando"):
        conferir_contrato(exemplo, {"itens": [{"valor": 3}]})
    with pytest.raises(AssertionError, match="não é"):
        conferir_contrato(exemplo, {"itens": [{"id": 1, "valor": 3}]})


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    return tmp_path / "estado" / "dossie.db"


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch, banco: Path) -> TestClient:
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(banco))
    monkeypatch.delenv("MISE_AUDITORIA", raising=False)
    monkeypatch.delenv("MISE_DESPENSA_TXT", raising=False)
    return TestClient(criar_app())


def dados(resposta: Any) -> Any:
    corpo = resposta.json()
    assert resposta.status_code == 200, corpo
    assert corpo["ok"], corpo.get("erro")
    return corpo["dados"]


def _com_receita_de_frango(cliente: TestClient) -> None:
    receita = {
        "nome": "Arroz com frango",
        "rendimento_porcoes": 4,
        "modo_preparo": ["Refogue o frango na panela e junte o arroz."],
        "ingredientes": [
            {"texto": "500 g de frango", "nome": "frango", "quantidade": 500, "medida": "g"},
            {"texto": "2 xícaras de arroz", "nome": "arroz", "quantidade": 2, "medida": "xicara"},
        ],
    }
    assert cliente.post("/api/avaliar", json=receita).json()["ok"]


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #


def test_a_lista_tem_a_forma_do_contrato(cliente: TestClient) -> None:
    d = dados(cliente.get("/api/despensa"))
    conferir_contrato(contrato("despensa.json"), d)
    assert d["total_itens"] == 37
    assert d["total_investido"] == {"valor": 663.39, "texto": "R$ 663,39"}
    assert sum(c["quantidade"] for c in d["categorias"]) == 37
    alcaparras = d["itens"][0]
    assert alcaparras["id"] == "alcaparras"
    assert alcaparras["estoque_texto"] == "2 kg (1 balde de 2 kg)"
    assert alcaparras["custo_unitario"] == {"valor": 41.0, "texto": "R$ 41,00/kg"}
    # A embalagem sem peso vem estimada, com a fonte: nenhuma pergunta para ela.
    assert d["pendencias"] == []
    assert d["orcamento"]["texto"] == "Nada gasto ainda: restam R$ 80,00 para complementos."


def test_a_lista_filtra_e_ordena(cliente: TestClient) -> None:
    d = dados(cliente.get("/api/despensa", params={"q": "FEIJAO", "ordem": "nome"}))
    assert [i["id"] for i in d["itens"]] == ["feijao-carioquinha", "feijao-preto"]
    assert (d["encontrados"], d["total_itens"]) == (2, 37)
    graos = dados(cliente.get("/api/despensa/itens", params={"categoria": "graos"}))
    assert set(graos) == {"itens", "total_itens", "encontrados", "categorias"}
    assert {i["categoria"] for i in graos["itens"]} == {"graos"}
    assert cliente.get("/api/despensa", params={"ordem": "preco"}).status_code == 422
    corpo = cliente.get("/api/despensa", params={"categoria": "joias"}).json()
    assert (corpo["ok"], corpo["categoria"]) == (False, "uso")


def test_o_item_tem_a_forma_do_contrato(cliente: TestClient) -> None:
    _com_receita_de_frango(cliente)
    d = dados(cliente.get("/api/despensa/itens/peito-de-frango"))
    exemplo = contrato("despensa-item.json")
    conferir_contrato(exemplo, d)
    assert d["comprado_texto"] == exemplo["comprado_texto"] == "2 kg por R$ 28,00"
    assert d["derivacao"] == exemplo["derivacao"]
    assert d["rascunho_chat"] == exemplo["rascunho_chat"]
    assert d["receitas"][0]["nome"] == "Arroz com frango"
    assert d["receitas"][0]["usa_texto"] == "usa 500 g"
    assert d["receitas_que_usam_texto"] == "entra em 1 receita"
    assert d["historico"][0]["tipo"] == "planilha"
    assert d["historico"][0]["pode_desfazer"] is False


def test_o_item_com_o_peso_estimado_nao_traz_pergunta(cliente: TestClient) -> None:
    d = dados(cliente.get("/api/despensa/itens/cobertura-de-chocolate"))
    sem_a_pergunta = {k: v for k, v in contrato("despensa-item.json").items() if k != "pendencia"}
    conferir_contrato(sem_a_pergunta, d)
    assert d["pendencia"] is None
    assert "estimativa" in d["derivacao"]
    assert "motivo" not in contrato("despensa.json")["pendencias"][0]


def test_item_que_nao_existe_e_404(cliente: TestClient) -> None:
    resposta = cliente.get("/api/despensa/itens/caviar")
    assert resposta.status_code == 404
    assert resposta.json()["categoria"] == "ausente"


def test_a_planilha_em_texto(cliente: TestClient, banco: Path) -> None:
    resposta = cliente.get("/api/despensa/planilha.txt")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "text/plain; charset=utf-8"
    assert resposta.headers["x-versao-da-planilha"] == "1"
    assert resposta.text.startswith("DESPENSA DA DONA MARIA")
    assert "Arroz branco tipo 1 | 5 | kg | R$ 24,90" in resposta.text
    assert (banco.parent / "despensa.txt").read_text(encoding="utf-8") == resposta.text


# --------------------------------------------------------------------------- #
# Escrita: acrescentar, corrigir, tirar
# --------------------------------------------------------------------------- #


def test_a_receita_da_compra_entra_na_descricao(cliente: TestClient) -> None:
    d = dados(cliente.post("/api/despensa/itens", json={**CREME, "receita": "Frango com creme"}))
    assert (
        d["orcamento"]["compras"][0]["descricao"]
        == "Creme de leite (despensa, para Frango com creme)"
    )


def test_comprar_com_os_80_tem_a_forma_do_contrato_e_nao_debita_duas_vezes(
    cliente: TestClient,
) -> None:
    exemplo = contrato("despensa-escrita.json")["adicionar"]
    cabecalho = {"Idempotency-Key": "c1f0e2d3"}
    d = dados(cliente.post("/api/despensa/itens", json=exemplo["pedido"], headers=cabecalho))
    conferir_contrato(exemplo["resposta"], d)
    assert d["item"]["id"].startswith("item-")
    assert d["item"]["origem_rotulo"] == "comprado com os complementos"
    assert d["orcamento"]["restante"]["texto"] == "R$ 71,00"
    assert (
        d["texto"] == "Anotei o creme de leite. Saíram R$ 9,00 dos complementos; restam R$ 71,00."
    )
    assert d["orcamento"]["compras"][0]["item_id"] == d["item"]["id"]

    de_novo = dados(cliente.post("/api/despensa/itens", json=exemplo["pedido"], headers=cabecalho))
    assert de_novo["repetida"] is True
    assert de_novo["item"]["id"] == d["item"]["id"]
    assert de_novo["orcamento"]["restante"]["texto"] == "R$ 71,00"
    # Sem cabeçalho, o id_cliente do corpo é a chave.
    pelo_corpo = dados(cliente.post("/api/despensa/itens", json=exemplo["pedido"]))
    assert pelo_corpo["repetida"] is True


def test_acrescentar_o_que_ja_tinha(cliente: TestClient) -> None:
    escrita = contrato("despensa-escrita.json")
    exemplo = escrita["adicionar_ja_tinha"]
    d = dados(cliente.post("/api/despensa/itens", json=exemplo["pedido"]))
    conferir_contrato(exemplo["resposta"], d)
    assert (
        d["texto"]
        == exemplo["resposta"]["texto"]
        == ("Anotei a farinha de rosca. Como a senhora já tinha, não mexi nos complementos.")
    )
    assert d["item"]["pago"] is None
    # Sem o preço, nada vira pergunta: a receita que usa custa pela referência.
    assert d["item"]["pendente"] is False
    assert d["pendencia"] is None
    assert d["orcamento"]["restante"]["texto"] == "R$ 80,00"
    # O preço que ela disser, quando quiser, entra pela mesma correção.
    preco = escrita["corrigir_preco"]
    pago = dados(cliente.patch(f"/api/despensa/itens/{d['item']['id']}", json=preco["pedido"]))
    conferir_contrato(preco["resposta"], pago)
    assert pago["texto"] == preco["resposta"]["texto"]
    assert pago["pendencias_resolvidas"] == []
    assert dados(cliente.get("/api/despensa"))["pendencias"] == []


def test_compra_acima_do_saldo_e_recusada_com_o_valor_em_reais(cliente: TestClient) -> None:
    corpo = cliente.post("/api/despensa/itens", json={**CREME, "preco_pago": 90.0}).json()
    assert (corpo["ok"], corpo["categoria"]) == (False, "regra")
    assert "R$ 90,00" in corpo["erro"]
    assert "R$ 80,00" in corpo["erro"]


def test_informar_a_embalagem_pela_tela(cliente: TestClient) -> None:
    exemplo = contrato("despensa-escrita.json")["corrigir"]
    d = dados(cliente.patch("/api/despensa/itens/cobertura-de-chocolate", json=exemplo["pedido"]))
    conferir_contrato(exemplo["resposta"], d)
    assert d["texto"] == "Com 1 kg na embalagem, a cobertura de chocolate sai a R$ 79,90/kg."
    # O peso dela troca o estimado: não havia pergunta a resolver.
    assert d["pendencias_resolvidas"] == []
    assert d["item"]["confianca"] == "media"
    assert d["item"]["pendente"] is False
    lista = dados(cliente.get("/api/despensa"))
    assert lista["pendencias"] == []
    evento = dados(cliente.get("/api/despensa/eventos"))["eventos"][0]
    assert (evento["acao"], evento["canal"]) == ("informar_embalagem", "tela")


def test_o_nome_antigo_do_campo_da_embalagem_tambem_vale(cliente: TestClient) -> None:
    d = dados(
        cliente.patch(
            "/api/despensa/itens/cobertura-de-chocolate",
            json={"conteudo_por_embalagem": "500 g"},
        )
    )
    assert d["item"]["custo_unitario"]["texto"] == "R$ 159,80/kg"


def test_acabou_e_correcao_pela_tela(cliente: TestClient) -> None:
    exemplo = contrato("despensa-escrita.json")["acabou"]
    acabou = dados(cliente.patch("/api/despensa/itens/bacon", json=exemplo["pedido"]))
    conferir_contrato(exemplo["resposta"], acabou)
    assert acabou["texto"] == "Anotei que o bacon acabou."
    corrigido = dados(
        cliente.patch("/api/despensa/itens/bacon", json={"estoque": 0.4, "motivo": "achei mais"})
    )
    assert corrigido["texto"] == "Corrigi o bacon. Agora sai a R$ 23,90/kg."
    eventos = dados(cliente.get("/api/despensa/eventos"))["eventos"]
    assert [e["acao"] for e in eventos] == ["corrigir", "acabou"]
    assert eventos[0]["motivo"] == "achei mais"
    vazio = cliente.patch("/api/despensa/itens/bacon", json={}).json()
    assert (vazio["ok"], vazio["categoria"]) == (False, "uso")
    ausente = cliente.patch("/api/despensa/itens/caviar", json={"estoque": 1})
    assert ausente.status_code == 404


def test_tirar_o_que_comprou_devolve_com_a_forma_do_contrato(cliente: TestClient) -> None:
    item_id = dados(cliente.post("/api/despensa/itens", json=CREME))["item"]["id"]
    exemplo = contrato("despensa-escrita.json")["remover"]["resposta"]
    d = dados(cliente.delete(f"/api/despensa/itens/{item_id}", params={"motivo": "errei"}))
    conferir_contrato(exemplo, d)
    assert d["removido"] == item_id
    assert d["estorno"] == {"valor": 9.0, "texto": "R$ 9,00"}
    assert d["orcamento"]["restante"]["texto"] == "R$ 80,00"
    assert d["texto"] == (
        "Tirei o creme de leite e devolvi R$ 9,00 aos complementos; restam R$ 80,00."
    )
    assert cliente.get(f"/api/despensa/itens/{item_id}").status_code == 404
    assert cliente.delete(f"/api/despensa/itens/{item_id}").status_code == 404


def test_tirar_com_a_mesma_chave_devolve_o_mesmo_resultado(cliente: TestClient) -> None:
    item_id = dados(cliente.post("/api/despensa/itens", json=CREME))["item"]["id"]
    cabecalho = {"Idempotency-Key": "tirar-1"}
    primeira = dados(cliente.delete(f"/api/despensa/itens/{item_id}", headers=cabecalho))
    segunda = dados(cliente.delete(f"/api/despensa/itens/{item_id}", headers=cabecalho))
    assert segunda["repetida"] is True
    assert segunda["estorno"] == primeira["estorno"]
    assert segunda["orcamento"]["restante"]["texto"] == "R$ 80,00"
    pela_query = cliente.delete("/api/despensa/itens/bacon", params={"id_cliente": "tirar-bacon"})
    assert dados(pela_query)["removido"] == "bacon"


# --------------------------------------------------------------------------- #
# Desfazer e estornar
# --------------------------------------------------------------------------- #


def test_desfazer_pelo_historico(cliente: TestClient) -> None:
    dados(cliente.delete("/api/despensa/itens/alcaparras"))
    (evento,) = dados(cliente.get("/api/despensa/eventos"))["eventos"]
    assert evento["pode_desfazer"] is True
    assert evento["texto"] == "Tirado da despensa."
    volta = dados(cliente.post(f"/api/despensa/eventos/{evento['id']}/desfazer"))
    conferir_contrato(contrato("despensa-escrita.json")["desfazer"]["resposta"], volta)
    assert volta["texto"] == "Voltei as alcaparras para a despensa."
    assert volta["item"]["id"] == "alcaparras"
    de_novo = dados(
        cliente.post(f"/api/despensa/eventos/{evento['id']}/desfazer", json={"id_cliente": "x"})
    )
    assert de_novo["repetida"] is True
    historico = dados(cliente.get("/api/despensa/itens/alcaparras"))["historico"]
    assert [h["tipo"] for h in historico] == ["planilha", "remover", "restaurar"]
    assert [h["pode_desfazer"] for h in historico] == [False, False, True]


def test_desfazer_o_que_nao_existe_e_404(cliente: TestClient) -> None:
    assert cliente.post("/api/despensa/eventos/ev-0099/desfazer").status_code == 404
    assert cliente.post("/api/despensa/eventos/qualquer/desfazer").status_code == 404


def test_estornar_uma_compra_tem_a_forma_do_contrato(cliente: TestClient) -> None:
    compra = dados(cliente.post("/api/despensa/itens", json=CREME))
    compra_id = compra["orcamento"]["compras"][0]["id"]
    exemplo = contrato("despensa-escrita.json")["estorno"]["resposta"]
    d = dados(cliente.post(f"/api/compras/{compra_id}/estorno"))
    conferir_contrato(exemplo, d)
    assert d["compra_id"] == compra_id
    assert d["estorno"] == {"valor": 9.0, "texto": "R$ 9,00"}
    assert d["removido"] == compra["item"]["id"]
    assert d["texto"] == (
        "Devolvi R$ 9,00 aos complementos; restam R$ 80,00. O creme de leite saiu da despensa."
    )
    de_novo = dados(cliente.post(f"/api/compras/{compra_id}/estorno"))
    assert de_novo["estorno_id"] == d["estorno_id"]
    assert de_novo["removido"] is None
    devolucao = cliente.post(f"/api/compras/{d['estorno_id']}/estorno").json()
    assert (devolucao["ok"], devolucao["categoria"]) == (False, "uso")
    assert cliente.post("/api/compras/999/estorno").status_code == 404


# --------------------------------------------------------------------------- #
# Duas portas, um banco
# --------------------------------------------------------------------------- #


def test_a_mudanca_feita_pela_conversa_aparece_na_tela(cliente: TestClient, banco: Path) -> None:
    from mise.dossie import Canal
    from mise.mcp_server import abrir_sessao

    antes = dados(cliente.get("/api/despensa"))
    assert antes["pendencias"] == []
    conversa = abrir_sessao(planilha=PLANILHA, banco=banco)
    try:
        conversa.canal = Canal.CONVERSA
        conversa.mudar_despensa(lambda e: e.informar_embalagem("cobertura-de-chocolate", "1 kg"))
    finally:
        conversa.dossie.fechar()
    depois = dados(cliente.get("/api/despensa"))
    assert depois["pendencias"] == []
    evento = dados(cliente.get("/api/despensa/eventos"))["eventos"][0]
    assert evento["canal"] == "conversa"


def test_despensa_vazia_nao_derruba_a_tela_nem_a_prontidao(cliente: TestClient) -> None:
    for item in dados(cliente.get("/api/despensa"))["itens"]:
        dados(cliente.delete(f"/api/despensa/itens/{item['id']}"))
    vazia = dados(cliente.get("/api/despensa"))
    assert vazia["itens"] == []
    assert vazia["total_investido"]["texto"] == "R$ 0,00"
    parado = dados(cliente.get("/api/visao-geral"))["dinheiro_parado"]
    assert (parado["itens"], parado["dois_maiores"]["fracao"]) == ([], 0.0)
    pronto = cliente.get("/saude/pronto")
    assert pronto.status_code == 200
    assert pronto.json()["itens"] == 0


def test_o_nome_do_item_nao_muda_pela_tela(cliente: TestClient) -> None:
    corpo = cliente.patch("/api/despensa/itens/bacon", json={"nome": "Toucinho"}).json()
    assert (corpo["ok"], corpo["categoria"]) == (False, "uso")
    assert "o nome de um item não muda" in corpo["erro"]
    mesmo = dados(cliente.patch("/api/despensa/itens/bacon", json={"nome": "BACON", "estoque": 1}))
    assert mesmo["item"]["nome"] == "Bacon"


def test_o_item_comprado_tem_a_forma_do_contrato(cliente: TestClient) -> None:
    item_id = dados(cliente.post("/api/despensa/itens", json=CREME))["item"]["id"]
    d = dados(cliente.get(f"/api/despensa/itens/{item_id}"))
    conferir_contrato(contrato("despensa-item-comprado.json"), d)
    assert d["origem"] == "orcamento"
    assert d["historico"][0]["tipo"] == "adicionar"
    (compra,) = d["compras"]
    assert (compra["estornada"], compra["pode_estornar"]) == (False, True)
    assert compra["valor"]["texto"] == "R$ 9,00"


def test_os_eventos_tem_a_forma_do_contrato_e_vem_por_cursor(cliente: TestClient) -> None:
    dados(cliente.patch("/api/despensa/itens/bacon", json={"estoque": 0}))
    dados(
        cliente.patch(
            "/api/despensa/itens/cobertura-de-chocolate", json={"conteudo_da_embalagem": "1 kg"}
        )
    )
    dados(cliente.delete("/api/despensa/itens/alcaparras"))
    primeira = dados(cliente.get("/api/despensa/eventos", params={"limite": 2}))
    assert [e["item_id"] for e in primeira["eventos"]] == ["alcaparras", "cobertura-de-chocolate"]
    assert primeira["proximo_cursor"] == primeira["eventos"][-1]["id"]
    resto = dados(
        cliente.get(
            "/api/despensa/eventos", params={"limite": 2, "cursor": primeira["proximo_cursor"]}
        )
    )
    conferir_contrato(contrato("despensa-eventos.json"), resto)
    assert [e["item_id"] for e in resto["eventos"]] == ["bacon"]
    assert resto["proximo_cursor"] is None
    assert resto["total"] == 3
    ruim = cliente.get("/api/despensa/eventos", params={"cursor": "xyz"}).json()
    assert (ruim["ok"], ruim["categoria"]) == (False, "uso")
