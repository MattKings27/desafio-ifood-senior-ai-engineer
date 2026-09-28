"""A grade, o detalhe, o custo e a avaliação das receitas, como a tela e o agente leem."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import receitas_de_teste as rt

from mise import receitas_json as rj
from mise.catalogo import OrigemNoCatalogo
from mise.compras import Medida
from mise.erros import Ausente, ErroDeUso
from mise.mcp_server import Sessao
from mise.perfil import Gosto
from mise.receita import Origem, Receita
from mise.receita import ingrediente as ing
from mise.unidades import Dimensao, Quantidade

RISOTO_URL = "https://www.panelinha.com.br/receita/risoto-de-trufa"
RISOTO = rt.pagina(
    "Risoto de trufa",
    ["1 xícara de arroz", "20 g de trufa branca"],
    ["Cozinhe o arroz na panela por 20 minutos e finalize com a trufa."],
    site="Panelinha",
)
FAROFA_URL = "https://www.tudogostoso.com.br/receita/farofa"
FAROFA = rt.pagina(
    "Farofa de bacon",
    ["200 g de bacon", "2 xícaras de farinha de mandioca"],
    ["Frite o bacon na frigideira por 10 minutos e junte a farinha."],
)
SOPA: dict[str, Any] = {
    "nome": "Sopa de cebola",
    "rendimento_porcoes": 4,
    "tempo_preparo_min": 50,
    "modo_preparo": ["Refogue a cebola na panela por 30 minutos."],
    "ingredientes": [
        {"texto": "2 kg de cebola", "nome": "cebola", "quantidade": 2, "medida": "kg"},
        {"texto": "sal a gosto", "nome": "sal"},
    ],
}


@pytest.fixture
def sessao(tmp_path: Path) -> Sessao:
    sessao = rt.sessao_nova(tmp_path)
    rt.cozinha_confirmada(sessao)
    rt.da_web(sessao, rt.CARNE_URL, rt.CARNE)
    rt.da_web(sessao, rt.MILHO_URL, rt.MILHO, OrigemNoCatalogo.CONVERSA)
    rt.da_web(sessao, RISOTO_URL, RISOTO)
    rt.da_web(sessao, FAROFA_URL, FAROFA)
    rt.ditada(sessao, **rt.ARROZ_COM_FRANGO)
    rt.ditada(sessao, **SOPA)
    sessao.cotar("milho verde", 6.0, 1, "lata")
    sessao.cotar("trufa branca", 95.0)
    sessao.dossie.registrar_gosto("Farofa de bacon", Gosto.NAO_GOSTA)
    return sessao


def _nomes(dados: dict[str, Any]) -> list[str]:
    return [item["nome"] for item in dados["itens"]]


def _lista(sessao: Sessao, **filtros: Any) -> dict[str, Any]:
    return rj.lista(sessao, rj.Filtros(**filtros))


# --------------------------------------------------------------------------- #
# As abas                                                                      #
# --------------------------------------------------------------------------- #


def test_so_aparece_o_que_ela_consegue_fazer(sessao: Sessao) -> None:
    pode = _lista(sessao)
    assert pode["aba"] == "pode_fazer"
    # "Temperos de sua preferência" vai a gosto: a carne moída dá, comprando o milho.
    assert set(_nomes(pode)) == {
        "Arroz com frango",
        "Frango com milho verde",
        "Sopa de cebola",
        "Carne moída com arroz na panela",
    }
    assert pode["contagens"] == {
        "pode_fazer": 4,
        "falta_resposta": 0,
        "ranking": 0,
        "nao_quer": 1,
    }
    # O risoto não cabe no orçamento: não é falta de preço na internet.
    assert pode["sem_preco_na_internet"] is None
    todas = {n for aba in rj.ABAS for n in _nomes(_lista(sessao, aba=aba))}
    assert "Risoto de trufa" not in todas, "a compra não cabe: não aparece em aba nenhuma"
    assert _nomes(_lista(sessao, aba="nao_quer")) == ["Farofa de bacon"]


def test_o_card_da_grade(sessao: Sessao) -> None:
    itens = {i["nome"]: i for i in _lista(sessao)["itens"]}
    milho = itens["Frango com milho verde"]
    assert milho["selo"] == {"codigo": "comprando", "texto": "Comprando R$ 6,00, cabe nos R$ 80,00"}
    assert milho["site"] == "TudoGostoso"
    assert milho["imagem"]["url"].startswith("/motor/imagens/")
    assert milho["usa_texto"] == "usa 3 de 4 ingredientes que a senhora tem"
    assert milho["falta_texto"] == "falta comprar milho verde"
    assert milho["tempo_texto"] == "35 min"
    assert milho["pergunta"] is None and milho["pontuacao"] is None
    arroz = itens["Arroz com frango"]
    assert arroz["selo"] == {"codigo": "com_o_que_tem", "texto": "Com o que a senhora tem"}
    assert (arroz["site"], arroz["imagem"], arroz["rota"]) == (
        None,
        None,
        "/receitas/arroz-com-frango",
    )
    sopa = itens["Sopa de cebola"]
    assert sopa["usa_texto"] == "usa 1 de 1 ingrediente que a senhora tem"


def test_a_que_espera_resposta_traz_a_pergunta(sessao: Sessao) -> None:
    """Só a cozinha dela segura uma receita: a técnica que ela ainda não disse."""
    sessao.dossie.salvar_perfil(sessao.perfil.sem_resposta("refogar"))
    esperam = _lista(sessao, aba="falta_resposta")["itens"]
    assert {i["nome"] for i in esperam} == {
        "Arroz com frango",
        "Frango com milho verde",
        "Sopa de cebola",
        "Carne moída com arroz na panela",
    }
    for item in esperam:
        assert item["selo"]["codigo"] == "falta_resposta"
        assert (item["pergunta"]["tipo"], item["pergunta"]["campo"]) == ("tecnica", "refogar")
        assert [o["rotulo"] for o in item["pergunta"]["opcoes"]] == ["Faço", "Não faço", "Não sei"]


def test_ranking_nao_gosta_por_ultimo_e_depois_a_pontuacao(sessao: Sessao) -> None:
    sessao.registrar_avaliacao(
        "arroz-com-frango", estrelas={"sabor": 5}, muda_o_gosto=True, gosta=True
    )
    milho = sessao.catalogo.por_nome("Frango com milho verde")
    assert milho is not None
    sessao.registrar_avaliacao(milho.slug, estrelas={"sabor": 5})
    farofa = sessao.catalogo.por_nome("Farofa de bacon")
    assert farofa is not None
    sessao.registrar_avaliacao(farofa.slug, estrelas={"sabor": 5})
    carne = sessao.catalogo.por_nome("Carne moída com arroz na panela")
    assert carne is not None
    sessao.registrar_avaliacao(carne.slug, estrelas={"sabor": 5})
    ranking = _lista(sessao, aba="ranking")
    assert _nomes(ranking) == [
        "Arroz com frango",
        "Carne moída com arroz na panela",
        "Frango com milho verde",
        "Farofa de bacon",
    ]
    assert ranking["itens"][0]["pontuacao"] == {"valor": 100.0, "texto": "100,0"}
    assert ranking["contagens"]["ranking"] == 4
    empate = [le for le in rj.ler(sessao, rj.guardadas(sessao)) if le.no_ranking]
    assert [le.nome for le in rj.ranking(empate)][-1] == "Farofa de bacon"


# --------------------------------------------------------------------------- #
# Os filtros e as ordens                                                       #
# --------------------------------------------------------------------------- #


def test_busca_sem_acento_no_nome_no_site_e_nos_ingredientes(sessao: Sessao) -> None:
    assert _nomes(_lista(sessao, q="FRANGO COM MILHO")) == ["Frango com milho verde"]
    assert set(_nomes(_lista(sessao, q="cebolá"))) == {
        "Frango com milho verde",
        "Sopa de cebola",
        "Carne moída com arroz na panela",
    }
    assert _lista(sessao, q="milho")["contagens"]["pode_fazer"] == 2
    assert set(_nomes(_lista(sessao, q="tudogostoso"))) == {
        "Frango com milho verde",
        "Carne moída com arroz na panela",
    }
    assert _lista(sessao, q="   ")["contagens"]["pode_fazer"] == 4


def test_usa_um_item_da_despensa(sessao: Sessao) -> None:
    assert set(_nomes(_lista(sessao, usa="peito-de-frango"))) == {
        "Arroz com frango",
        "Frango com milho verde",
    }
    assert _nomes(_lista(sessao, usa="alcaparras")) == []


def test_tempo_maximo_so_com_o_que_tenho_e_nota_minima(sessao: Sessao) -> None:
    assert set(_nomes(_lista(sessao, tempo_max=40))) == {
        "Arroz com frango",
        "Frango com milho verde",
    }
    assert set(_nomes(_lista(sessao, so_com_o_que_tenho=True))) == {"Arroz com frango"}
    assert _nomes(_lista(sessao, nota_min=Decimal(50))) == []
    sessao.registrar_avaliacao("arroz-com-frango", estrelas={"sabor": 5})
    assert _nomes(_lista(sessao, nota_min=Decimal(80))) == ["Arroz com frango"]
    assert _nomes(_lista(sessao, nota_min=Decimal(95))) == []


def test_as_ordens(sessao: Sessao) -> None:
    assert _nomes(_lista(sessao, ordem="compra"))[0] == "Arroz com frango"
    assert _nomes(_lista(sessao, ordem="tempo")) == [
        "Frango com milho verde",
        "Arroz com frango",
        "Carne moída com arroz na panela",
        "Sopa de cebola",
    ]
    assert _nomes(_lista(sessao, ordem="recentes"))[0] == "Sopa de cebola"
    assert _nomes(_lista(sessao, ordem="aproveitamento"))[0] == "Carne moída com arroz na panela"
    assert set(_nomes(_lista(sessao, ordem="pontuacao"))) == {
        "Arroz com frango",
        "Frango com milho verde",
        "Sopa de cebola",
        "Carne moída com arroz na panela",
    }


@pytest.mark.parametrize(("campo", "valor"), [("aba", "todas"), ("ordem", "preco")])
def test_aba_e_ordem_que_nao_existem(campo: str, valor: str) -> None:
    with pytest.raises(ErroDeUso, match="não existe"):
        rj.Filtros(**{campo: valor})


# --------------------------------------------------------------------------- #
# O detalhe                                                                    #
# --------------------------------------------------------------------------- #


def test_o_detalhe_diz_quanto_ela_tem_de_cada_ingrediente(sessao: Sessao) -> None:
    carne = sessao.catalogo.por_nome("Carne moída com arroz na panela")
    assert carne is not None
    d = rj.detalhe(sessao, carne.slug)
    # Só o gosto falta para o preço; a cozinha e a despensa dão, comprando o milho.
    assert (d["veredito"], d["veredito_rotulo"]) == ("FALTA INFO", "Falta saber")
    assert d["veredito_da_cozinha"] == {
        "codigo": "comprando",
        "rotulo": "Dá, comprando o que falta",
        "motivo": "Falta comprar milho verde, R$ 6,00; cabe nos R$ 80,00 que restam.",
    }
    linhas = {i["nome"]: i for i in d["ingredientes"]}
    assert linhas["Arroz branco tipo 1"] == {
        "nome": "Arroz branco tipo 1",
        "item_id": "arroz-branco-tipo-1",
        "precisa": {"texto": "2 xícaras (cerca de 408 g)"},
        "tem": {"texto": "5 kg"},
        "sobra": {"texto": "4,59 kg"},
        "situacao": "tem",
        "compra": None,
        "medida_de_referencia": None,
    }
    assert linhas["Óleo de soja"]["precisa"] == {"texto": "2 colheres de sopa (30 ml)"}
    assert linhas["milho verde"]["compra"] == {"texto": "1 lata, R$ 6,00", "cabe": True}
    assert linhas["Sal"]["situacao"] == "a_gosto" and linhas["Sal"]["sobra"] is None
    assert linhas["Salsinha (cheiro-verde)"]["situacao"] == "opcional"
    temperos = linhas["temperos de sua preferência"]
    # O tempero que a receita não diz quanto vai é a gosto: nunca pergunta.
    assert (temperos["situacao"], temperos["precisa"]) == ("a_gosto", {"texto": "a gosto"})
    assert d["linhas_nao_entendidas"] == []
    assert not [p for p in d["perguntas"] if p["tipo"] == "ingrediente"]
    assert d["opcionais"] == [
        {"nome": "Salsinha (cheiro-verde)", "texto": "cheiro-verde a gosto (opcional)"}
    ]
    assert d["falta_comprar"]["texto"] == (
        "falta comprar milho verde, R$ 6,00; cabe nos R$ 80,00 que restam"
    )
    (milho,) = d["falta_comprar"]["itens"]
    assert milho["origem_preco"] == "informado pela senhora"
    assert (d["custo_porcao"], d["pode_precificar"]) == (None, False)
    assert d["fonte"] == {"site": "TudoGostoso", "url": rt.CARNE_URL, "autor": "Leuda"}
    assert d["tempos"] == {
        "preparo_min": 15,
        "cozimento_min": 30,
        "total_min": 45,
        "ativo_min": 30,
    }
    assert (d["tempo_texto"], d["rendimento_texto"], d["origem"]) == (
        "45 min",
        "4 porções",
        "descoberta",
    )
    assert d["avisos"] == []
    assert d["rascunho_chat"] == "Vale a pena eu fazer carne moída com arroz na panela para vender?"
    assert d["posicao_no_ranking"] is None
    assert d["avaliacao"]["estrelas"] == dict.fromkeys(
        ("sabor", "facilidade", "tempo", "entrega", "apelo")
    )
    assert d["passos"][0]["ordem"] == 1


def test_estoque_parcial_compra_o_resto(sessao: Sessao) -> None:
    d = rj.detalhe(sessao, "sopa-de-cebola")
    (cebola, sal) = d["ingredientes"]
    assert (cebola["situacao"], cebola["tem"], cebola["sobra"]) == (
        "tem_parte",
        {"texto": "1 kg"},
        {"texto": "nada"},
    )
    assert cebola["compra"]["texto"].startswith("1 kg, R$ ")
    assert cebola["compra"]["cabe"] is True
    (item,) = d["falta_comprar"]["itens"]
    assert item["origem_preco"] == "pelo preço que a senhora pagou na despensa"
    assert "o preço que a senhora pagou" in item["derivacao"]
    assert d["veredito_da_cozinha"]["codigo"] == "comprando"
    assert d["veredito_da_cozinha"]["motivo"].startswith("Falta comprar cebola, R$ ")
    assert sal["situacao"] == "a_gosto"


def test_a_que_nao_da_diz_por_que(sessao: Sessao) -> None:
    risoto = sessao.catalogo.por_nome("Risoto de trufa")
    assert risoto is not None
    d = rj.detalhe(sessao, risoto.slug)
    assert d["veredito_da_cozinha"]["codigo"] == "nao_da"
    assert (
        d["veredito_da_cozinha"]["motivo"]
        == "A compra sai R$ 95,00 e restam R$ 80,00 do orçamento."
    )
    assert d["falta_comprar"]["cabe_no_orcamento"] is False
    assert "não cabe nos R$ 80,00" in d["falta_comprar"]["texto"]
    assert d["rascunho_chat"] == "Por que eu não consigo fazer risoto de trufa?"


@pytest.mark.usefixtures("sem_precos_de_referencia")
def test_preco_desconhecido_do_que_falta(sessao: Sessao, tmp_path: Path) -> None:
    sem_preco = rt.sessao_nova(tmp_path / "outra")
    rt.cozinha_confirmada(sem_preco)
    milho = rt.da_web(sem_preco, rt.MILHO_URL, rt.MILHO)
    d = rj.detalhe(sem_preco, milho.slug)
    assert d["falta_comprar"]["custo"] is None and d["falta_comprar"]["cabe_no_orcamento"] is None
    assert d["falta_comprar"]["texto"] == (
        "falta comprar milho verde; falta saber o preço de milho verde"
    )
    (item,) = d["falta_comprar"]["itens"]
    assert (item["origem_preco"], item["cabe_no_orcamento"], item["derivacao"]) == (
        None,
        None,
        "falta saber o preço",
    )
    linhas = {i["nome"]: i for i in d["ingredientes"]}
    assert linhas["milho verde"]["compra"] == {
        "texto": "1 lata, preço ainda não informado",
        "cabe": None,
    }
    # Sem preço na internet a receita fica de fora, sem pergunta, e a grade diz quantas.
    grade = rj.lista(sem_preco, rj.Filtros())
    assert grade["contagens"] == {"pode_fazer": 0, "falta_resposta": 0, "ranking": 0, "nao_quer": 0}
    assert grade["sem_preco_na_internet"] == {
        "receitas": 1,
        "nomes": ["Frango com milho verde"],
        "slugs": [milho.slug],
        "texto": (
            "1 receita ficou de fora porque não achei em página de supermercado o preço de "
            "algum ingrediente; se a senhora souber o preço, eu confiro de novo."
        ),
    }
    assert d["veredito_da_cozinha"]["codigo"] == "nao_da"
    assert not [p for p in d["perguntas"] if p["tipo"] == "ingrediente"]
    sem_preco.dossie.fechar()


def test_receita_que_nao_existe(sessao: Sessao) -> None:
    with pytest.raises(Ausente):
        rj.detalhe(sessao, "lasanha")


def test_receita_em_avaliacao_de_antes_do_catalogo(sessao: Sessao) -> None:
    antiga = Receita(
        nome="Pudim antigo",
        ingredientes=(ing("3 ovos", "ovos", 3, "ovo"),),
        modo_preparo=("Asse no forno por 40 minutos.",),
        url="https://exemplo.com.br/pudim",
        fonte="exemplo.com.br",
        origem=Origem.WEB,
    ).com_exigencias_detectadas()
    sessao.guardar(antiga)
    ditada_antes = Receita(
        nome="Arroz doce", ingredientes=(ing("1 xícara de arroz", "arroz", 1, "xicara"),)
    )
    sessao.guardar(ditada_antes)
    guardadas = {g.nome: g for g in rj.guardadas(sessao)}
    assert guardadas["Pudim antigo"].origem is OrigemNoCatalogo.CONVERSA
    assert guardadas["Pudim antigo"].site == "exemplo.com.br"
    assert guardadas["Arroz doce"].origem is OrigemNoCatalogo.DITA
    slug = guardadas["Pudim antigo"].slug
    d = rj.detalhe(sessao, slug)
    assert d["fonte"]["url"] == "https://exemplo.com.br/pudim"
    assert rj.guardada_por_slug(sessao, "arroz-doce").nome == "Arroz doce"


# --------------------------------------------------------------------------- #
# O custo                                                                      #
# --------------------------------------------------------------------------- #


def test_custo_so_de_receita_liberada_com_o_gosto(sessao: Sessao) -> None:
    with pytest.raises(rj.CustoRecusado, match="antes preciso saber uma coisa"):
        rj.custo(sessao, "arroz-com-frango")
    sessao.dossie.registrar_gosto("Arroz com frango", Gosto.GOSTA)
    custo = rj.custo(sessao, "arroz-com-frango")
    assert custo["total"] == {"valor": 3.0, "texto": "R$ 3,00"}
    assert [linha["quantidade"] for linha in custo["linhas"]] == ["0,125 kg", "0,25 kg"]
    assert custo["itens_a_gosto"] == ["sal"]
    assert rj.detalhe(sessao, "arroz-com-frango")["custo_porcao"] == {
        "valor": 3.0,
        "texto": "R$ 3,00",
    }
    assert rj.detalhe(sessao, "arroz-com-frango")["rascunho_chat"] == (
        "Quanto eu cobro por uma porção de arroz com frango?"
    )
    risoto = sessao.catalogo.por_nome("Risoto de trufa")
    assert risoto is not None
    with pytest.raises(rj.CustoRecusado, match="esse prato não dá"):
        rj.custo(sessao, risoto.slug)


def test_custo_com_preco_que_sumiu(sessao: Sessao, monkeypatch: pytest.MonkeyPatch) -> None:
    from mise import cmv
    from mise.erros import CustoIndeterminado

    sessao.dossie.registrar_gosto("Arroz com frango", Gosto.GOSTA)

    def sem_preco(*_a: Any, **_c: Any) -> Any:
        raise CustoIndeterminado("Arroz com frango", ("Peito de frango",))

    monkeypatch.setattr(cmv, "calcular", sem_preco)
    with pytest.raises(rj.CustoRecusado, match="falta o preço de peito de frango"):
        rj.custo(sessao, "arroz-com-frango")
    assert rj.detalhe(sessao, "arroz-com-frango")["custo_porcao"] is None


# --------------------------------------------------------------------------- #
# A avaliação e as notas                                                       #
# --------------------------------------------------------------------------- #


def test_resposta_da_avaliacao_diz_a_posicao(sessao: Sessao) -> None:
    nada = rj.resposta_da_avaliacao(sessao, "arroz-com-frango", anotou=False)
    assert nada["atualizado_texto"] == "a senhora ainda não avaliou"
    assert nada["texto"] == "Quando a senhora der as estrelas, arroz com frango entra no ranking."
    feita = sessao.registrar_avaliacao("arroz-com-frango", estrelas={"sabor": 4})
    assert (
        feita["texto"] == "Anotei. Arroz com frango está em primeiro lugar no ranking da senhora."
    )
    assert feita["posicao_no_ranking"] == 1
    assert feita["atualizado_texto"].startswith("hoje, ")
    risoto = sessao.catalogo.por_nome("Risoto de trufa")
    assert risoto is not None
    fora = sessao.registrar_avaliacao(risoto.slug, estrelas={"sabor": 4})
    assert fora["texto"].endswith(
        "entra no ranking quando der para fazer com o que a senhora tem ou pode comprar."
    )
    assert fora["posicao_no_ranking"] is None


def test_gosto_pela_avaliacao_e_o_da_conferencia(sessao: Sessao) -> None:
    sessao.dossie.registrar_gosto("arroz com FRANGO", Gosto.DESCONHECIDO, "meu filho não come")
    sessao.registrar_avaliacao("arroz-com-frango", gosta=False, muda_o_gosto=True)
    (opiniao,) = [o for o in sessao.dossie.gostos() if o.prato.lower() == "arroz com frango"]
    assert opiniao.gosto is Gosto.NAO_GOSTA
    assert opiniao.impedimento == "meu filho não come", "não gostar mantém o impedimento"
    sessao.registrar_avaliacao("arroz-com-frango", gosta=None, muda_o_gosto=True)
    opiniao = sessao.dossie.gosto_por("Arroz com frango")
    assert opiniao is not None and opiniao.gosto is Gosto.DESCONHECIDO
    assert opiniao.impedimento == "meu filho não come", "voltar a não disse também mantém"
    assert _nomes(_lista(sessao, aba="nao_quer")) == ["Arroz com frango", "Farofa de bacon"]
    with pytest.raises(ErroDeUso, match="até"):
        sessao.registrar_avaliacao("arroz-com-frango", notas="x" * 3000)


def test_mudei_de_ideia_tira_o_impedimento_e_diz(sessao: Sessao) -> None:
    """Dizer que gosta de novo é mudar de ideia: o impedimento que ela apontou deixa de segurar."""
    sessao.dossie.registrar_gosto("Arroz com frango", Gosto.NAO_GOSTA, "meu filho não come.")
    resposta = sessao.registrar_avaliacao("arroz-com-frango", gosta=True, muda_o_gosto=True)
    opiniao = sessao.dossie.gosto_por("Arroz com frango")
    assert opiniao is not None
    assert (opiniao.gosto, opiniao.impedimento) == (Gosto.GOSTA, "")
    assert resposta["texto"].startswith(
        "Anotei que a senhora gosta de fazer arroz com frango. O impedimento que a senhora "
        "tinha apontado (meu filho não come) não segura mais a receita. "
    )
    assert resposta["avaliacao"]["gosta"] is True
    assert _nomes(_lista(sessao, aba="nao_quer")) == ["Farofa de bacon"]
    sem_impedimento = sessao.registrar_avaliacao("arroz-com-frango", gosta=True, muda_o_gosto=True)
    assert sem_impedimento["texto"].startswith("Anotei. ")


def test_notas(sessao: Sessao) -> None:
    gravadas = sessao.avaliacoes.gravar("arroz-com-frango", notas="Testar com açafrão.")
    resposta = rj.resposta_das_notas(sessao, "arroz-com-frango", gravadas)
    assert (resposta["notas"], resposta["texto"]) == ("Testar com açafrão.", "Guardei a anotação.")
    apagadas = sessao.avaliacoes.gravar("arroz-com-frango", notas="")
    assert (
        rj.resposta_das_notas(sessao, "arroz-com-frango", apagadas)["texto"]
        == "Apaguei a anotação."
    )
    sem_data = rj.resposta_das_notas(sessao, "arroz-com-frango", rj._vazias("arroz-com-frango"))
    assert sem_data["atualizado_texto"] == "agora"


def test_posicoes_por_extenso() -> None:
    assert rj._posicao_texto(1) == "em primeiro lugar"
    assert rj._posicao_texto(10) == "em décimo lugar"
    assert rj._posicao_texto(11) == "na posição 11"


# --------------------------------------------------------------------------- #
# A descoberta e as quantidades escritas                                        #
# --------------------------------------------------------------------------- #


def test_descoberta_parada_diz_o_que_ja_trouxe(sessao: Sessao, tmp_path: Path) -> None:
    estado = rj.estado_da_descoberta(sessao)
    assert (estado["estado"], estado["encontradas"]) == ("parada", 3)
    assert estado["texto"] == "Trouxe 3 receitas da internet que usam a despensa da senhora."
    vazia = rt.sessao_nova(tmp_path / "vazia")
    assert rj.estado_da_descoberta(vazia)["texto"].startswith("Ainda não procurei receitas")
    vazia.dossie.fechar()


@pytest.mark.parametrize(
    ("linha", "esperado"),
    [
        (ing("4 ovos", "ovos", 4, "ovo"), "4 ovos"),
        (ing("1 ovo", "ovo", 1, "ovo"), "1 ovo"),
        (ing("2 pimentões", "pimentões", 2, ""), "2 unidades"),
        (ing("1 pimentão", "pimentão", 1, ""), "1 unidade"),
        (ing("1 litro de leite", "leite", 1, "litro"), "1 L"),
        (ing("250 ml de leite", "leite", 250, "ml"), "250 ml"),
        (ing("2 ramos de alecrim", "alecrim", 2, "ramo"), "2 ramo"),
        (ing("1,5 xícara de arroz", "arroz", Decimal("1.5"), "xicara"), "1,5 xícara"),
        (ing("sal a gosto", "sal"), "a gosto"),
    ],
)
def test_quanto_a_receita_pede_com_as_palavras_dela(linha: Any, esperado: str) -> None:
    assert rj.na_receita(linha) == esperado


def test_quantidades_curtas_e_embalagens() -> None:
    assert rj.quantidade_curta(Quantidade(Decimal("4.5921"), Dimensao.MASSA)) == "4,59 kg"
    assert rj.quantidade_curta(Quantidade(Decimal("0.0035"), Dimensao.MASSA)) == "3,5 g"
    assert rj.quantidade_curta(Quantidade(Decimal("0.4081"), Dimensao.VOLUME)) == "408 ml"
    assert rj.quantidade_curta(Quantidade(Decimal("2.333"), Dimensao.CONTAGEM)) == "2,33 unidades"
    assert rj.medida_texto(Medida(Quantidade(Decimal(2), Dimensao.CONTAGEM), "lata")) == "2 latas"
    assert rj.tempo_texto(None) is None
    assert rj.tempo_texto(0) is None
    assert rj.tempo_texto(60) == "1 h"
    assert rj.tempo_texto(90) == "1 h 30 min"


def test_o_que_ela_respondeu_aparece_no_detalhe(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    pure = rt.da_web(
        sessao,
        "https://blog.exemplo.com.br/pure",
        rt.pagina(
            "Purê",
            ["1 kg de batata", "manteiga de sua escolha"],
            [],
            rende="",
            tempos=None,
        ),
    )
    sessao.responder_sobre_a_receita(pure.slug, "rendimento_porcoes", "4")
    sessao.responder_sobre_a_receita(pure.slug, "modo_preparo", "Cozinhe a batata e amasse.")
    sessao.responder_sobre_a_receita(pure.slug, "tempo_cozimento_min", "30 min")
    sessao.responder_sobre_a_receita(pure.slug, "manteiga de sua escolha", "2 colheres de sopa")
    textos = [r["texto"] for r in rj.detalhe(sessao, pure.slug)["respostas"]]
    assert textos == [
        "A senhora disse que rende 4 porções.",
        "A senhora contou o modo de preparo.",
        "A senhora disse que fica 30 min no fogo.",
        "A senhora disse quanto vai de “manteiga de sua escolha”: 2 colheres de sopa.",
    ]
    sessao.dossie.fechar()


def test_o_que_ela_comprou_entra_no_que_ela_tem(sessao: Sessao) -> None:
    sessao.dossie.registrar_gosto("Frango com milho verde", Gosto.GOSTA)
    sessao.dossie.registrar_compra("milho verde", Decimal(2), "lata", rt_dinheiro(12))
    milho = sessao.catalogo.por_nome("Frango com milho verde")
    assert milho is not None
    linhas = {i["nome"]: i for i in rj.detalhe(sessao, milho.slug)["ingredientes"]}
    assert linhas["milho verde"]["situacao"] == "tem"
    assert linhas["milho verde"]["tem"] == {"texto": "2 latas que a senhora comprou"}
    assert linhas["milho verde"]["sobra"] == {"texto": "1 lata"}


def rt_dinheiro(valor: int) -> Any:
    from mise.dinheiro import Dinheiro

    return Dinheiro.de(valor)
