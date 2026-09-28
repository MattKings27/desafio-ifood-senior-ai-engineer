"""O checklist de produção: cada item com o estado e a origem, pelas regras do portão.

O checklist não decide nada: lê a conferência e diz, item por item, de onde vem
a certeza. Estes testes conferem que ele diz o mesmo que o portão, em cada um dos
cinco grupos, e que o aceite só libera com tudo confirmado.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from mise.checklist import (
    NAO_PRECISA,
    ItemDaLista,
    Origem,
    Status,
    _Perguntas,
    _pesos,
    _porcoes,
    _precos,
    lista_de_producao,
    o_que_falta_para_aceitar,
)
from mise.dinheiro import Dinheiro
from mise.dossie import EstadoOrcamento
from mise.perfil import Gosto, PerfilCozinha, Posse
from mise.receita import Receita, receita
from mise.receita import ingrediente as ing
from mise.taxonomia import EQUIPAMENTOS, TECNICAS
from mise.viabilidade import PesoPedido, avaliar

OITENTA = EstadoOrcamento(Dinheiro.de(80), Dinheiro.zero())


def _dita() -> PerfilCozinha:
    """Toda a cozinha respondida por ela, e a rotina folgada."""
    perfil = PerfilCozinha.inicial()
    perfil = perfil.com_equipamentos((e.id, Posse.TEM) for e in EQUIPAMENTOS)
    perfil = perfil.com_tecnicas((t.id, Posse.TEM) for t in TECNICAS)
    for campo, valor in (
        ("bocas_fogao", 4),
        ("tempo_max_por_fornada_min", 240),
        ("porcoes_por_fornada", 20),
        ("tem_gas_sobrando", True),
        ("espaco_geladeira_litros", 30),
        ("energia_aparelhos_simultaneos", 3),
    ):
        perfil = perfil.com_restricao(campo, valor)
    return perfil


def _com_o_basico_suposto() -> PerfilCozinha:
    """A rotina e o resto respondidos; o que toda cozinha tem, suposto."""
    perfil = _dita()
    base = PerfilCozinha.inicial()
    return PerfilCozinha(
        equipamentos={
            **perfil.equipamentos,
            **{e.id: Posse.TEM for e in EQUIPAMENTOS if e.pressuposto},
        },
        tecnicas={**perfil.tecnicas, **{t.id: Posse.TEM for t in TECNICAS if t.pressuposta}},
        restricoes=perfil.restricoes,
        confirmados=frozenset(i for i in perfil.confirmados if not base.suposto(i)),
    )


def _arroz() -> Receita:
    return receita(
        "Arroz refogado",
        [
            ing("1 xícara de arroz", "arroz", 1, "xicara"),
            ing("1 cebola", "cebola", 1, ""),
            ing("sal a gosto", "sal"),
        ],
        rendimento_porcoes=4,
        modo_preparo=("Refogue a cebola no óleo.", "Junte o arroz e cozinhe por 20 minutos."),
        tempo_total_min=30,
    )


def _lista(
    r: Receita,
    perfil: PerfilCozinha,
    despensa: Any,
    *,
    gosto: Gosto = Gosto.GOSTA,
    respondidos: tuple[str, ...] = (),
    **kw: Any,
) -> dict[str, Any]:
    avaliacao = avaliar(r, perfil, despensa, orcamento_restante=Dinheiro.de(80), gosto=gosto, **kw)
    return lista_de_producao(r, perfil, avaliacao, OITENTA, respondidos=respondidos)


def _grupo(lista: dict[str, Any], id_: str) -> dict[str, Any]:
    return next(g for g in lista["grupos"] if g["id"] == id_)


def _item(lista: dict[str, Any], grupo: str, id_: str) -> dict[str, Any]:
    return next(i for i in _grupo(lista, grupo)["itens"] if i["id"] == id_)


# --------------------------------------------------------------------------- #
# O todo: o que falta, a pergunta e o aceite
# --------------------------------------------------------------------------- #


def test_o_basico_suposto_segura_o_aceite_com_uma_pergunta(despensa: Any) -> None:
    lista = _lista(_arroz(), _com_o_basico_suposto(), despensa)
    assert [g["id"] for g in lista["grupos"]] == [
        "equipamentos",
        "tecnicas",
        "rotina",
        "ingredientes",
        "pre_determinados",
    ]
    assert lista["titulo"] == "Checklist de produção"
    assert lista["pode_aceitar"] is False
    assert lista["resumo"] == "Antes de aceitar, falta 1 coisa."
    assert lista["falta_para_aceitar"] == ["Confirmar que a senhora tem fogão e que sabe refogar."]
    assert lista["confirmar_a_cozinha"]["pergunta"] == (
        "Antes de aceitar, a senhora confirma que tem fogão e que sabe refogar?"
    )
    fogao = _item(lista, "equipamentos", "fogao")
    assert (fogao["status"], fogao["status_texto"], fogao["origem_texto"]) == (
        "suposto",
        "suposto: confirme",
        "suposto",
    )
    assert [o["rotulo"] for o in fogao["pergunta"]["opcoes"]] == ["Tenho", "Não tenho", "Não sei"]
    refogar = _item(lista, "tecnicas", "refogar")
    assert refogar["status"] == "suposto"
    assert refogar["pergunta"]["motivo"] == "Arroz refogado pede refogar"
    assert _grupo(lista, "equipamentos")["status"] == "suposto"


def test_com_tudo_confirmado_ela_pode_aceitar(despensa: Any) -> None:
    lista = _lista(_arroz(), _dita(), despensa)
    assert lista["pode_aceitar"] is True
    assert lista["falta_para_aceitar"] == []
    assert lista["confirmar_a_cozinha"] is None
    assert lista["resumo"] == "Está tudo certo para a senhora aceitar este prato."
    fogao = _item(lista, "equipamentos", "fogao")
    assert (fogao["status"], fogao["status_texto"], fogao["origem_texto"]) == (
        "confirmado",
        "confirmado pela senhora",
        "a senhora disse",
    )


def test_o_gosto_e_as_perguntas_entram_no_que_falta(despensa: Any) -> None:
    perfil = _com_o_basico_suposto().com_restricao("tempo_max_por_fornada_min", None)
    lista = _lista(_arroz(), perfil, despensa, gosto=Gosto.DESCONHECIDO)
    faltam = lista["falta_para_aceitar"]
    assert faltam[0].startswith("Responder: Quanto tempo a senhora consegue ficar cozinhando")
    assert faltam[1] == "Dizer se a senhora gosta de fazer arroz refogado."
    assert faltam[2] == "Confirmar que a senhora tem fogão e que sabe refogar."
    assert lista["resumo"] == "Antes de aceitar, faltam 3 coisas."


def test_receita_que_nao_da_diz_so_por_que(despensa: Any) -> None:
    perfil = _dita().com_equipamento("fogao", Posse.NAO_TEM)
    lista = _lista(_arroz(), perfil, despensa)
    assert lista["resumo"] == "Pelo que a senhora me disse, esta receita não dá."
    assert lista["falta_para_aceitar"] == ["A receita precisa de fogão e a senhora não tem."]
    fogao = _item(lista, "equipamentos", "fogao")
    assert (fogao["status"], fogao["detalhe"]) == (
        "nao_da",
        "A receita precisa de fogão e a senhora não tem.",
    )
    assert _grupo(lista, "equipamentos")["status"] == "nao_da"


# --------------------------------------------------------------------------- #
# Equipamentos e técnicas
# --------------------------------------------------------------------------- #


def _assado() -> Receita:
    return receita(
        "Frango assado",
        [ing("500 g de peito de frango", "peito de frango", 500, "g")],
        rendimento_porcoes=4,
        modo_preparo=("Leve ao forno a 200 °C por 40 minutos.",),
    )


def test_forno_sem_resposta_substituto_e_nao_tem(despensa: Any) -> None:
    sem_saber = (
        _dita().sem_resposta("forno").sem_resposta("air_fryer").sem_resposta("forno_eletrico")
    )
    forno = _item(_lista(_assado(), sem_saber, despensa), "equipamentos", "forno")
    assert (forno["status"], forno["pergunta"]["campo"]) == ("falta_saber", "forno")

    sem_forno = sem_saber.com_equipamento("forno", Posse.NAO_TEM)
    forno = _item(_lista(_assado(), sem_forno, despensa), "equipamentos", "forno")
    assert (forno["status"], forno["pergunta"]["campo"]) == ("falta_saber", "air_fryer")
    assert forno["detalhe"].startswith("Sem forno, air fryer resolve")

    com_air_fryer = sem_forno.com_equipamento("air_fryer", Posse.TEM)
    forno = _item(_lista(_assado(), com_air_fryer, despensa), "equipamentos", "forno")
    assert (forno["status"], forno["detalhe"]) == ("confirmado", "A senhora resolve com air fryer.")

    nada = sem_forno.com_equipamento("air_fryer", Posse.NAO_TEM).com_equipamento(
        "forno_eletrico", Posse.NAO_TEM
    )
    forno = _item(_lista(_assado(), nada, despensa), "equipamentos", "forno")
    assert forno["status"] == "nao_da"


def test_o_substituto_suposto_pede_a_confirmacao_dele(despensa: Any) -> None:
    omelete = receita(
        "Omelete",
        [ing("3 ovos", "ovos", 3, "")],
        modo_preparo=("Bata os ovos.",),
        equipamentos=("frigideira_antiaderente",),
    )
    perfil = _com_o_basico_suposto().sem_resposta("frigideira_antiaderente")
    lista = _lista(omelete, perfil, despensa)
    item = _item(lista, "equipamentos", "frigideira_antiaderente")
    assert item["status"] == "suposto"
    assert item["detalhe"] == "A senhora resolve com frigideira, que toda cozinha tem; confirme."
    assert [i["id"] for i in lista["confirmar_a_cozinha"]["itens"]] == ["frigideira"]


def test_sem_modo_de_preparo_pergunta_como_ela_faz(despensa: Any) -> None:
    colado = receita("Bolo", [ing("3 ovos", "ovos", 3, "")], rendimento_porcoes=8)
    lista = _lista(colado, _dita(), despensa)
    grupo = _grupo(lista, "equipamentos")
    (item,) = grupo["itens"]
    assert (item["id"], item["status"]) == ("modo_preparo", "falta_saber")
    assert item["pergunta"]["texto"].startswith("Como a senhora faz bolo?")
    tecnicas = _grupo(lista, "tecnicas")
    assert (tecnicas["itens"], tecnicas["vazio_texto"]) == (
        [],
        "Esta receita não pede técnica especial.",
    )
    assert tecnicas["status"] == "confirmado"


def test_tecnica_que_ninguem_perguntou_e_a_que_ela_nao_faz(despensa: Any) -> None:
    massa = receita(
        "Talharim",
        [ing("300 g de farinha de trigo", "farinha de trigo", 300, "g")],
        rendimento_porcoes=4,
        modo_preparo=("Faça a massa fresca e abra com o rolo.",),
        tecnicas=("massa_fresca",),
    )
    sem_saber = _dita().sem_resposta("massa_fresca")
    item = _item(_lista(massa, sem_saber, despensa), "tecnicas", "massa_fresca")
    assert (item["status"], item["pergunta"]["campo"]) == ("falta_saber", "massa_fresca")
    nao_faz = _dita().com_tecnica("massa_fresca", Posse.NAO_TEM)
    item = _item(_lista(massa, nao_faz, despensa), "tecnicas", "massa_fresca")
    assert item["status"] == "nao_da"
    assert item["detalhe"] == "A receita pede massa fresca, que a senhora disse não fazer."


# --------------------------------------------------------------------------- #
# Rotina: o portão diz do que a receita depende
# --------------------------------------------------------------------------- #


def _feijoada() -> Receita:
    return receita(
        "Feijoada",
        [ing("1 kg de feijão preto", "feijão preto", 1, "kg")],
        rendimento_porcoes=8,
        modo_preparo=(
            "Cozinhe o feijão na panela de pressão por 90 minutos.",
            "Em outra panela, refogue o bacon por 10 minutos.",
            "Deixe esfriar e leve à geladeira por 2 horas.",
        ),
    )


def test_a_rotina_de_quem_respondeu(despensa: Any) -> None:
    lista = _lista(_feijoada(), _dita(), despensa)
    tempo = _item(lista, "rotina", "tempo_max_por_fornada_min")
    assert tempo["status"] == "confirmado"
    assert tempo["detalhe"].endswith("; a senhora tem 4 horas por cozinhada.")
    gas = _item(lista, "rotina", "tem_gas_sobrando")
    assert (gas["status"], gas["origem_texto"]) == ("confirmado", "a senhora disse")
    assert gas["detalhe"].startswith("A receita fica ")
    assert gas["detalhe"].endswith("; a senhora tem botijão de reserva.")
    geladeira = _item(lista, "rotina", "espaco_geladeira_litros")
    assert geladeira["detalhe"].endswith("; a senhora tem 30 litros livres na geladeira.")
    bocas = _item(lista, "rotina", "bocas_fogao")
    assert bocas["detalhe"].endswith("; o fogão tem 4 bocas.")
    energia = _item(lista, "rotina", "energia_aparelhos_simultaneos")
    assert (energia["status_texto"], energia["origem"]) == (NAO_PRECISA, "receita")


def test_a_rotina_em_aberto_pergunta_e_a_que_nao_cabe_nao_da(despensa: Any) -> None:
    aberta = _dita()
    for campo in ("tem_gas_sobrando", "espaco_geladeira_litros", "bocas_fogao"):
        aberta = aberta.com_restricao(campo, None)
    lista = _lista(_feijoada(), aberta, despensa)
    for campo in ("tem_gas_sobrando", "espaco_geladeira_litros", "bocas_fogao"):
        item = _item(lista, "rotina", campo)
        assert (item["status"], item["pergunta"]["campo"]) == ("falta_saber", campo), campo
    assert _grupo(lista, "rotina")["status"] == "falta_saber"

    apertada = (
        _dita()
        .com_restricao("tem_gas_sobrando", False)
        .com_restricao("espaco_geladeira_litros", 0)
        .com_restricao("tempo_max_por_fornada_min", 30)
    )
    lista = _lista(_feijoada(), apertada, despensa)
    for campo in ("tem_gas_sobrando", "espaco_geladeira_litros", "tempo_max_por_fornada_min"):
        assert _item(lista, "rotina", campo)["status"] == "nao_da", campo


def test_uma_boca_so_e_aviso_e_a_energia(despensa: Any) -> None:
    uma_boca = _dita().com_restricao("bocas_fogao", 1)
    bocas = _item(_lista(_feijoada(), uma_boca, despensa), "rotina", "bocas_fogao")
    assert bocas["status"] == "confirmado"
    assert "Com uma boca, a senhora faz uma parte depois da outra" in bocas["detalhe"]

    bolo = receita(
        "Bolo batido",
        [ing("3 ovos", "ovos", 3, "")],
        rendimento_porcoes=8,
        modo_preparo=("Bata no liquidificador e depois na batedeira.",),
    )
    item = _item(
        _lista(bolo, _dita().com_restricao("energia_aparelhos_simultaneos", None), despensa),
        "rotina",
        "energia_aparelhos_simultaneos",
    )
    assert item["status"] == "falta_saber"
    item = _item(
        _lista(bolo, _dita().com_restricao("energia_aparelhos_simultaneos", 1), despensa),
        "rotina",
        "energia_aparelhos_simultaneos",
    )
    assert item["status"] == "nao_da"
    item = _item(_lista(bolo, _dita(), despensa), "rotina", "energia_aparelhos_simultaneos")
    assert item["detalhe"].endswith("; a instalação aguenta 3 aparelhos fortes juntos.")


def test_o_tempo_que_a_receita_nao_diz(despensa: Any) -> None:
    """O tempo no fogo que a receita não diz não é pergunta: não dá, e ela corrige se quiser."""
    sem_tempo = receita(
        "Risoto",
        [ing("1 xícara de arroz", "arroz", 1, "xicara")],
        rendimento_porcoes=2,
        modo_preparo=("Refogue o arroz e cozinhe mexendo até ficar cremoso.",),
    )
    curta = _dita().com_restricao("tempo_max_por_fornada_min", 60)
    item = _item(_lista(sem_tempo, curta, despensa), "rotina", "tempo_max_por_fornada_min")
    assert item["status"] == "nao_da"
    assert item["pergunta"] is None
    assert item["editar"]["campo"] == "tempo_cozimento_min"


# --------------------------------------------------------------------------- #
# Ingredientes: o que tem, o que compra e se cabe
# --------------------------------------------------------------------------- #


def _com_milho() -> Receita:
    return receita(
        "Frango com milho",
        [
            ing("500 g de peito de frango", "peito de frango", 500, "g"),
            ing("1 lata de milho", "milho verde", 1, "lata"),
            ing("temperos de sua preferência", "temperos", None, "", entendida=False),
        ],
        rendimento_porcoes=4,
        modo_preparo=("Refogue o frango e junte o milho por 10 minutos.",),
    )


def test_o_que_tem_o_que_compra_e_a_linha_nao_lida(despensa: Any) -> None:
    lista = _lista(_com_milho(), _dita(), despensa)
    tem = _item(lista, "ingredientes", "na_despensa")
    assert (tem["status"], tem["status_texto"], tem["detalhe"]) == (
        "confirmado",
        "tem",
        "Peito de frango.",
    )
    milho = _item(lista, "ingredientes", "compra:milho verde")
    # Sem preço em fonte nenhuma (aqui, sem as referências): não é pergunta, não dá,
    # e ela corrige o preço se quiser.
    assert (milho["status"], milho["detalhe"]) == (
        "nao_da",
        "Comprar 1 lata; não achei o preço em página de supermercado, e sem ele não dá "
        "para confirmar que cabe.",
    )
    assert milho["pergunta"] is None
    assert milho["editar"]["assunto"] == "preco_de_compra"
    assert _item(lista, "ingredientes", "orcamento")["status"] == "nao_da"
    # O tempero que a receita não diz qual é vai a gosto: nada a perguntar.
    assert not [
        i
        for g in lista["grupos"]
        for i in g["itens"]
        if i["status"] == "falta_saber" and g["id"] == "ingredientes"
    ]


def test_compra_com_preco_cabe_ou_nao_cabe(despensa: Any) -> None:
    precos = {"milho verde": Dinheiro.de(6)}
    lista = _lista(_com_milho(), _dita(), despensa, precos=precos)
    milho = _item(lista, "ingredientes", "compra:milho verde")
    assert (milho["status"], milho["status_texto"], milho["origem_texto"]) == (
        "confirmado",
        "vai comprar",
        "a senhora disse",
    )
    orcamento = _item(lista, "ingredientes", "orcamento")
    assert (orcamento["nome"], orcamento["status_texto"]) == ("Cabe nos R$ 80,00", "cabe")
    assert orcamento["detalhe"] == "A compra dá R$ 6,00; restam R$ 80,00."

    caro = {"milho verde": Dinheiro.de(95)}
    lista = _lista(_com_milho(), _dita(), despensa, precos=caro)
    assert _item(lista, "ingredientes", "orcamento")["status"] == "nao_da"


def test_nada_a_comprar(despensa: Any) -> None:
    orcamento = _item(_lista(_arroz(), _dita(), despensa), "ingredientes", "orcamento")
    assert (orcamento["status_texto"], orcamento["detalhe"]) == (
        NAO_PRECISA,
        "Nada a comprar; restam R$ 80,00.",
    )


# --------------------------------------------------------------------------- #
# Pré-determinados: porções, pesos e preços de referência
# --------------------------------------------------------------------------- #


def test_as_porcoes_da_receita_e_as_que_ela_disse(despensa: Any) -> None:
    porcoes = _item(_lista(_arroz(), _dita(), despensa), "pre_determinados", "porcoes")
    assert (porcoes["status"], porcoes["origem"], porcoes["detalhe"]) == (
        "pre_determinado",
        "receita",
        "Rende 4 porções, como a receita diz.",
    )
    assert porcoes["editar"]["campo"] == "rendimento_porcoes"
    assert porcoes["editar"]["entrada"]["tipo"] == "inteiro"
    dita = _item(
        _lista(_arroz(), _dita(), despensa, respondidos=("rendimento_porcoes",)),
        "pre_determinados",
        "porcoes",
    )
    assert (dita["status"], dita["origem_texto"], dita["detalhe"]) == (
        "confirmado",
        "a senhora disse",
        "Rende 4 porções.",
    )


def test_porcoes_estimadas_quando_a_conferencia_traz_o_rendimento() -> None:
    """A conferência que estima o rendimento (pelo peso) diz de onde veio a estimativa."""
    avaliacao = SimpleNamespace(
        checagens=(),
        rendimento=SimpleNamespace(
            porcoes=3,
            estimado=True,
            derivacao="cerca de 1,05 kg de ingredientes ÷ 350 g por porção = 3 porções",
            texto="cerca de 3 porções",
            porcao_g=Decimal(350),
        ),
    )
    item = _porcoes(_arroz(), avaliacao, (), _Perguntas(None)).para_json()  # type: ignore[arg-type]
    assert (item["status"], item["origem_texto"]) == (
        "pre_determinado",
        "referência de porções de 350 g",
    )
    assert item["detalhe"].startswith("Cerca de 1,05 kg de ingredientes")
    assert item["editar"]["assunto"] == "rendimento"


def test_o_peso_de_referencia_e_o_que_ela_disse() -> None:
    linha = ing("1 peito de frango", "peito de frango", 1, "")
    corrigir = PesoPedido(Decimal(1), "", "um peito de frango")
    do_ibge = SimpleNamespace(
        ingrediente=linha,
        item=None,
        conversao="1 peito = 180 g",
        medida_de_referencia=SimpleNamespace(gramas=Decimal(180)),
        corrigir_peso=corrigir,
    )
    dela = SimpleNamespace(
        ingrediente=ing("2 colheres de alcaparras", "alcaparras", 2, "colher"),
        item=SimpleNamespace(nome="Alcaparras"),
        conversao="2 colheres = 20 g (a senhora disse)",
    )
    sem_nada = SimpleNamespace(ingrediente=ing("sal a gosto", "sal"), item=None, conversao="")
    itens = [
        i.para_json()
        for i in _pesos(
            SimpleNamespace(ajustes=(do_ibge, dela, sem_nada)),  # type: ignore[arg-type]
            _Perguntas(None),
        )
    ]
    assert [(i["nome"], i["status"], i["origem_texto"]) for i in itens] == [
        ("Peito de frango", "pre_determinado", "referência de medidas do IBGE"),
        ("Alcaparras", "confirmado", "a senhora disse"),
    ]
    assert itens[0]["detalhe"] == "Um peito de frango pesa cerca de 180 g."
    assert itens[0]["editar"]["assunto"] == "medida"
    assert itens[0]["editar"]["entrada"] == {"tipo": "peso", "unidade": "g", "peso_de": None}
    assert itens[1]["detalhe"] == "2 colheres = 20 g."


def test_o_preco_de_referencia_com_a_fonte() -> None:
    quatro = Dinheiro.de(4)

    def faltante(origem: str, referencia: Any = None, custo: Any = quatro) -> Any:
        return SimpleNamespace(
            nome="creme de leite",
            quantidade_texto="1 caixinha",
            custo_estimado=custo,
            origem_do_preco=origem,
            referencia=referencia,
            premissa="",
            derivacao="1 caixinha × R$ 4,00",
            falta=None,
        )

    savegnago = SimpleNamespace(
        site="Savegnago", preco_texto="R$ 3,99 pela caixinha de 200 g no Savegnago, 27/09/2026"
    )
    ajustes = (
        SimpleNamespace(faltante=faltante("referencia", savegnago), falta=None),
        SimpleNamespace(faltante=faltante("pesquisado_na_web"), falta=None),
        SimpleNamespace(faltante=faltante("informado_por_ela"), falta=None),
        SimpleNamespace(faltante=faltante("estimado", custo=None), falta=None),
        SimpleNamespace(faltante=None, falta=None),
    )
    itens = [
        i.para_json()
        for i in _precos(SimpleNamespace(ajustes=ajustes), _Perguntas(None))  # type: ignore[arg-type]
    ]
    assert [(i["status"], i["origem_texto"]) for i in itens] == [
        ("pre_determinado", "referência de preço no Savegnago"),
        ("pre_determinado", "referência de preço na internet"),
    ]
    assert itens[0]["detalhe"] == "R$ 3,99 pela caixinha de 200 g no Savegnago, 27/09/2026."
    assert itens[0]["editar"]["assunto"] == "preco_de_compra"
    assert itens[0]["editar"]["texto"].startswith("Quanto a senhora paga em creme de leite?")


def test_o_que_falta_para_aceitar_de_receita_liberada_e_vazio(despensa: Any) -> None:
    avaliacao = avaliar(_arroz(), _dita(), despensa, gosto=Gosto.GOSTA)
    assert o_que_falta_para_aceitar(_arroz(), avaliacao, ()) == []


@pytest.mark.parametrize("status", list(Status))
def test_todo_estado_tem_a_frase_dele(status: Status) -> None:
    item = ItemDaLista("x", "rotina", "X", status, Origem.REFERENCIA).para_json()
    assert item["status_texto"]
    assert item["origem_texto"] == "referência"
