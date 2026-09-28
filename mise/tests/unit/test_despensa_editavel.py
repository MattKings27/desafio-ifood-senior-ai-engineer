"""A despensa que ela edita: eventos sobre a planilha, os R$ 80,00 e duas portas no mesmo banco."""

from __future__ import annotations

import json
from contextlib import closing
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from mise.despensa import Confianca, OrigemDoItem, carregar_despensa
from mise.despensa_editavel import (
    Acao,
    DespensaEditavel,
    Evento,
    TipoDeEvento,
    chave_do_nome,
    id_do_rotulo,
    reconstruir,
    rotulo_do_evento,
    unidade_com_conteudo,
)
from mise.dinheiro import Dinheiro
from mise.dossie import Canal, Dossie
from mise.erros import Ausente, ErroDeUso, OrcamentoExcedido
from mise.mcp_server import Sessao
from mise.perfil import Gosto, PerfilCozinha, Posse
from mise.receita import ingrediente, receita

if TYPE_CHECKING:
    from collections.abc import Iterator

PLANILHA = Path(__file__).resolve().parents[3] / "dados" / "despensa_dona_maria.xlsx"


class RelogioFalso:
    """O tempo do dossiê anda quando o teste manda."""

    def __init__(self) -> None:
        self.momento = datetime(2026, 9, 25, 13, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.momento

    def andar(self, **quanto: float) -> None:
        self.momento += timedelta(**quanto)


@pytest.fixture
def relogio() -> RelogioFalso:
    return RelogioFalso()


def abrir(banco: Path, relogio: RelogioFalso | None = None) -> Sessao:
    return Sessao(
        planilha=carregar_despensa(PLANILHA),
        dossie=Dossie(banco, relogio=relogio),
        arquivo_txt=banco.parent / "despensa.txt",
    )


@pytest.fixture
def sessao(tmp_path: Path, relogio: RelogioFalso) -> Iterator[Sessao]:
    s = abrir(tmp_path / "dossie.db", relogio)
    yield s
    s.dossie.fechar()


@pytest.fixture
def editavel(sessao: Sessao) -> DespensaEditavel:
    return sessao.editavel


def _creme(editavel: DespensaEditavel, **extra: Any) -> Any:
    campos: dict[str, Any] = {
        "nome": "Creme de leite",
        "estoque": Decimal(2),
        "unidade": "un 200g",
        "quantidade_comprada": Decimal(2),
        "preco_pago": Decimal("9.00"),
        "origem": OrigemDoItem.ORCAMENTO,
        "canal": Canal.TELA,
    }
    return editavel.adicionar(**{**campos, **extra})


# --------------------------------------------------------------------------- #
# Sem mudança nenhuma, é a planilha
# --------------------------------------------------------------------------- #


def test_sem_eventos_a_despensa_e_a_propria_planilha(sessao: Sessao) -> None:
    assert sessao.despensa is sessao.planilha
    assert len(sessao.despensa) == 37
    assert sessao.despensa.total_investido == Dinheiro.de("663.39")
    estado = sessao.editavel.estado()
    assert estado.versao == 0
    assert estado.eventos == ()
    assert sessao.dossie.orcamento().restante == Dinheiro.de("80.00")


def test_sem_mudanca_no_banco_o_objeto_e_o_mesmo(sessao: Sessao) -> None:
    sessao.editavel.acabou("bacon")
    primeira = sessao.despensa
    assert sessao.despensa is primeira


# --------------------------------------------------------------------------- #
# A cobertura de chocolate
# --------------------------------------------------------------------------- #


def test_informar_a_embalagem_troca_o_peso_estimado_pelo_dela(sessao: Sessao) -> None:
    assert sessao.despensa["Cobertura de chocolate"].embalagem_estimada is not None
    mudanca = sessao.editavel.informar_embalagem("cobertura-de-chocolate", "1 kg", canal=Canal.TELA)
    assert mudanca.mudou
    # Não havia pergunta: o peso estimado dá lugar ao que ela disse.
    assert mudanca.pendencia_resolvida is None
    depois = sessao.despensa["Cobertura de chocolate"]
    assert depois.custo.valor == Dinheiro.de("79.90")
    assert depois.custo.confianca is Confianca.MEDIA
    assert depois.linha.unidade == "un 1kg"
    assert depois.linha.conteudo_informado
    assert sessao.despensa.pendencias == []
    # O total pago não muda: ela informou o peso, não pagou de novo.
    assert sessao.despensa.total_investido == Dinheiro.de("663.39")
    assert mudanca.evento is not None
    assert mudanca.evento.acao is Acao.INFORMAR_EMBALAGEM
    assert mudanca.evento.dados["antes"] == {"unidade": "un", "conteudo_informado": False}
    assert mudanca.evento.canal == "tela"


def test_informar_de_novo_o_mesmo_peso_nao_grava_nada(editavel: DespensaEditavel) -> None:
    editavel.informar_embalagem("cobertura-de-chocolate", "1 kg")
    de_novo = editavel.informar_embalagem("cobertura-de-chocolate", "1kg")
    assert de_novo.evento is None
    assert not de_novo.mudou
    assert len(editavel.eventos()) == 1


def test_receita_com_a_cobertura_usa_o_peso_estimado_e_o_dela_vale_mais(sessao: Sessao) -> None:
    perfil = PerfilCozinha.inicial()
    perfil = perfil.com_equipamentos((e, Posse.TEM) for e in perfil.equipamentos)
    perfil = perfil.com_tecnicas((t, Posse.TEM) for t in perfil.tecnicas)
    sessao.dossie.salvar_perfil(
        perfil.com_restricao("bocas_fogao", 4).com_restricao("tempo_max_por_fornada_min", 120)
    )
    sessao.dossie.registrar_gosto("Brigadeiro de colher", Gosto.GOSTA)
    sessao.guardar(
        receita(
            "Brigadeiro de colher",
            [ingrediente("200 g de cobertura de chocolate", "cobertura de chocolate", 200, "g")],
            rendimento_porcoes=4,
            modo_preparo=["Derreta a cobertura em fogo baixo por 10 minutos e sirva em potinhos."],
        )
    )
    antes = sessao.avaliar(sessao.candidatas["Brigadeiro de colher"])
    # O peso estimado (a embalagem de 1 kg da página do supermercado) já libera o prato.
    assert antes.veredito.permite_precificar
    assert str(antes.usos[0].custo.arredondado()) == "R$ 15,98"

    mudanca, afetadas = sessao.mudar_despensa(
        lambda e: e.informar_embalagem("cobertura-de-chocolate", "500 g")
    )
    assert mudanca.mudou
    depois = sessao.avaliar(sessao.candidatas["Brigadeiro de colher"])
    assert depois.veredito.permite_precificar
    # O peso que ela disse vale mais: 200 g de 500 g por R$ 79,90.
    assert str(depois.usos[0].custo.arredondado()) == "R$ 31,96"
    assert afetadas["liberadas"] == [] and afetadas["bloqueadas"] == []

    desfeito, afetadas = sessao.mudar_despensa(lambda e: e.desfazer(mudanca.evento.id))
    assert afetadas["bloqueadas"] == []
    assert desfeito.pendencia_depois is None
    assert sessao.despensa["Cobertura de chocolate"].embalagem_estimada is not None


# --------------------------------------------------------------------------- #
# Acrescentar: o que ela já tinha e o que comprou com os complementos
# --------------------------------------------------------------------------- #


def test_acrescentar_o_que_ja_tinha_nao_mexe_nos_80(sessao: Sessao) -> None:
    mudanca = sessao.editavel.adicionar(
        nome="  Farinha   de rosca ", estoque=Decimal("0.5"), unidade="kg", canal=Canal.TELA
    )
    item = sessao.despensa["Farinha de rosca"]
    assert item.id == mudanca.item_id
    assert item.id.startswith("item-")
    assert len(item.id) == len("item-") + 8
    assert item.origem is OrigemDoItem.JA_TINHA
    assert item.categoria == "graos"
    assert not item.preco_informado
    assert mudanca.compra is None
    assert mudanca.pendencia_depois is None, "sem o preço, nada vira pergunta a ela"
    assert sessao.dossie.orcamento().restante == Dinheiro.de("80.00")
    assert len(sessao.despensa) == 38
    assert sessao.despensa.total_investido == Dinheiro.de("663.39")


def test_comprar_com_os_80_debita_na_hora_e_tirar_devolve(sessao: Sessao) -> None:
    mudanca = _creme(sessao.editavel, prato="Frango com creme de milho")
    assert mudanca.compra is not None
    assert mudanca.compra.valor == Dinheiro.de("9.00")
    assert mudanca.compra.item_id == mudanca.item_id
    assert "Frango com creme de milho" in mudanca.compra.descricao
    assert sessao.dossie.orcamento().restante == Dinheiro.de("71.00")
    item = sessao.despensa["Creme de leite"]
    assert item.custo.valor.arredondado() == Dinheiro.de("22.50")
    assert item.categoria == "laticinios"
    # A compra da despensa não vira "comprado" do portão: o item já está na despensa.
    assert sessao.dossie.compras() == {}

    tirado = sessao.editavel.remover(mudanca.item_id, canal=Canal.TELA)
    assert tirado.depois is None
    assert tirado.estornado == Dinheiro.de("9.00")
    assert sessao.dossie.orcamento().restante == Dinheiro.de("80.00")
    assert "Creme de leite" not in sessao.despensa
    extrato = sessao.dossie.extrato()
    assert [linha.valor for linha in extrato] == [Dinheiro.de("9.00"), Dinheiro.de("-9.00")]
    assert extrato[0].estornada
    assert extrato[1].estorna == extrato[0].id


def test_comprar_sem_preco_ou_acima_do_saldo_e_recusado_sem_gravar(sessao: Sessao) -> None:
    with pytest.raises(ErroDeUso, match="diga quanto a senhora pagou"):
        _creme(sessao.editavel, preco_pago=None)
    with pytest.raises(OrcamentoExcedido):
        _creme(sessao.editavel, preco_pago=Decimal("90.00"))
    assert sessao.editavel.eventos() == ()
    assert sessao.dossie.extrato() == ()
    assert "Creme de leite" not in sessao.despensa


@pytest.mark.parametrize(
    ("campos", "mensagem"),
    [
        ({"nome": "   "}, "nome do ingrediente"),
        ({"nome": "x" * 81}, "longo demais"),
        ({"origem": OrigemDoItem.PLANILHA}, "a planilha não muda"),
        ({"estoque": Decimal(-1)}, "negativo"),
        ({"preco_pago": Decimal(-1)}, "negativo"),
        ({"quantidade_comprada": Decimal(0)}, "maior que zero"),
        ({"categoria": "joias"}, "categoria desconhecida"),
        ({"estoque": Decimal(0), "quantidade_comprada": None}, "quanto a senhora comprou"),
    ],
)
def test_item_novo_invalido_e_recusado(
    editavel: DespensaEditavel, campos: dict[str, Any], mensagem: str
) -> None:
    base: dict[str, Any] = {
        "nome": "Nata",
        "estoque": Decimal(1),
        "unidade": "kg",
        "preco_pago": Decimal(5),
        "origem": OrigemDoItem.JA_TINHA,
    }
    with pytest.raises(ErroDeUso, match=mensagem):
        editavel.adicionar(**{**base, **campos})


def test_unidade_que_ninguem_le_e_recusada(editavel: DespensaEditavel) -> None:
    with pytest.raises(ErroDeUso):
        editavel.adicionar(nome="Nata", estoque=Decimal(1), unidade="punhado")
    assert editavel.eventos() == ()


def test_nome_que_ja_esta_na_despensa_e_recusado_mesmo_sem_acento(
    editavel: DespensaEditavel,
) -> None:
    with pytest.raises(ErroDeUso, match="já está na despensa") as erro:
        editavel.adicionar(nome="oleo de SOJA", estoque=Decimal(1), unidade="L")
    assert erro.value.contexto["id"] == "oleo-de-soja"


def test_sem_quantidade_comprada_ela_comprou_o_que_tem(editavel: DespensaEditavel) -> None:
    mudanca = editavel.adicionar(
        nome="Nata", estoque=Decimal("0.3"), unidade="kg", preco_pago=Decimal("6.00")
    )
    assert mudanca.depois is not None
    assert mudanca.depois.quantidade_bruta == Decimal("0.3")
    assert mudanca.depois.custo.valor == Dinheiro.de("20.00")


# --------------------------------------------------------------------------- #
# Corrigir, acabou, tirar
# --------------------------------------------------------------------------- #


def test_corrigir_um_item_da_planilha_nao_mexe_nos_80(sessao: Sessao) -> None:
    mudanca = sessao.editavel.corrigir(
        "peito-de-frango", estoque=Decimal("1.5"), preco_pago=Decimal("30.00"), motivo="recontei"
    )
    item = sessao.despensa["Peito de frango"]
    assert item.estoque.valor == Decimal("1.5")
    assert item.custo.valor == Dinheiro.de("15.00")
    assert mudanca.evento is not None
    assert mudanca.evento.motivo == "recontei"
    assert mudanca.evento.dados["antes"] == {"estoque": "2", "preco_pago": "28"}
    assert sessao.dossie.extrato() == ()
    assert sessao.despensa.total_investido == Dinheiro.de("665.39")


def test_corrigir_o_preco_do_que_comprou_com_os_80_acompanha_o_orcamento(sessao: Sessao) -> None:
    item_id = _creme(sessao.editavel).item_id
    mudanca = sessao.editavel.corrigir(item_id, preco_pago=Decimal("12.00"))
    assert [e.valor for e in mudanca.estornos] == [Dinheiro.de("-9.00")]
    assert mudanca.compra is not None
    assert mudanca.compra.valor == Dinheiro.de("12.00")
    assert sessao.dossie.orcamento().restante == Dinheiro.de("68.00")
    assert [c.valor for c in sessao.dossie.compras_do_item(item_id)] == [Dinheiro.de("12.00")]

    desfeita = sessao.editavel.desfazer(mudanca.evento.id)
    assert desfeita.evento is not None
    assert desfeita.evento.desfaz == mudanca.evento.id
    assert sessao.dossie.orcamento().restante == Dinheiro.de("71.00")
    assert sessao.despensa["Creme de leite"].preco_pago == Dinheiro.de("9.00")


def test_o_que_comprou_com_os_80_nao_fica_sem_valor(editavel: DespensaEditavel) -> None:
    item_id = _creme(editavel).item_id
    with pytest.raises(ErroDeUso, match="valor pago"):
        editavel.corrigir(item_id, preco_pago=Decimal(0))


def test_corrigir_sem_dizer_o_que_mudou_e_erro(editavel: DespensaEditavel) -> None:
    with pytest.raises(ErroDeUso, match="diga o que mudou"):
        editavel.corrigir("bacon")
    with pytest.raises(ErroDeUso, match="maior que zero"):
        editavel.corrigir("bacon", quantidade_comprada=Decimal(0))
    with pytest.raises(ErroDeUso, match="categoria"):
        editavel.corrigir("bacon", categoria="joias")


def test_corrigir_categoria_e_unidade(editavel: DespensaEditavel) -> None:
    editavel.corrigir("aceto-balsamico", categoria="conservas")
    assert editavel.despensa["Aceto balsâmico"].categoria == "conservas"
    editavel.corrigir("aceto-balsamico", unidade="un 250ml", estoque=Decimal(2))
    aceto = editavel.despensa["Aceto balsâmico"]
    assert aceto.estoque.valor == Decimal("0.5")


def test_item_que_nao_existe_e_ausente(editavel: DespensaEditavel) -> None:
    with pytest.raises(Ausente):
        editavel.corrigir("caviar", estoque=Decimal(1))
    with pytest.raises(Ausente):
        editavel.item("caviar")
    with pytest.raises(Ausente):
        editavel.remover("caviar")


def test_acabou_zera_o_estoque_e_mantem_o_preco(sessao: Sessao) -> None:
    mudanca = sessao.editavel.acabou("bacon", motivo="usei tudo")
    bacon = sessao.despensa["Bacon"]
    assert bacon.estoque.valor == 0
    assert bacon.custo.valor == Dinheiro.de("23.90")
    assert mudanca.evento is not None
    assert mudanca.evento.acao is Acao.ACABOU
    # Acabou de novo: nada muda.
    assert sessao.editavel.acabou("bacon").evento is None


def test_tirar_um_item_da_planilha_nao_mexe_nos_80_e_nao_se_tira_duas_vezes(
    sessao: Sessao,
) -> None:
    mudanca = sessao.editavel.remover("alcaparras", motivo="joguei fora")
    assert mudanca.estornos == ()
    assert mudanca.pendencia_antes is None
    assert "Alcaparras" not in sessao.despensa
    assert len(sessao.despensa) == 36
    assert sessao.despensa.total_investido == Dinheiro.de("581.39")
    assert sessao.dossie.orcamento().restante == Dinheiro.de("80.00")
    with pytest.raises(Ausente):
        sessao.editavel.remover("alcaparras")


def test_tirar_a_cobertura_nao_deixa_pendencia(sessao: Sessao) -> None:
    mudanca = sessao.editavel.remover("cobertura-de-chocolate")
    assert mudanca.pendencia_antes is None
    assert sessao.despensa.pendencias == []


# --------------------------------------------------------------------------- #
# Desfazer
# --------------------------------------------------------------------------- #


def test_desfazer_um_acrescimo_com_os_80_tira_e_devolve(sessao: Sessao) -> None:
    acrescimo = _creme(sessao.editavel)
    desfeito = sessao.editavel.desfazer(acrescimo.evento.id)
    assert desfeito.evento is not None
    assert desfeito.evento.tipo is TipoDeEvento.REMOVER
    assert desfeito.evento.acao is Acao.DESFAZER
    assert desfeito.estornado == Dinheiro.de("9.00")
    assert "Creme de leite" not in sessao.despensa
    assert sessao.dossie.orcamento().restante == Dinheiro.de("80.00")


def test_desfazer_uma_remocao_traz_de_volta_e_debita_de_novo(sessao: Sessao) -> None:
    acrescimo = _creme(sessao.editavel)
    remocao = sessao.editavel.remover(acrescimo.item_id)
    volta = sessao.editavel.desfazer(remocao.evento.id)
    assert volta.evento is not None
    assert volta.evento.tipo is TipoDeEvento.RESTAURAR
    assert volta.compra is not None
    assert volta.compra.valor == Dinheiro.de("9.00")
    assert "Creme de leite" in sessao.despensa
    assert sessao.dossie.orcamento().restante == Dinheiro.de("71.00")
    # E desfazer a volta tira de novo, devolvendo.
    sessao.editavel.desfazer(volta.evento.id)
    assert "Creme de leite" not in sessao.despensa
    assert sessao.dossie.orcamento().restante == Dinheiro.de("80.00")


def test_desfazer_a_remocao_de_um_item_da_planilha_nao_debita(sessao: Sessao) -> None:
    remocao = sessao.editavel.remover("alcaparras")
    volta = sessao.editavel.desfazer(remocao.evento.id)
    assert volta.compra is None
    assert "Alcaparras" in sessao.despensa
    assert sessao.dossie.extrato() == ()


def test_desfazer_uma_correcao_volta_os_valores(sessao: Sessao) -> None:
    correcao = sessao.editavel.corrigir("peito-de-frango", estoque=Decimal("0.5"))
    desfeita = sessao.editavel.desfazer(correcao.evento.id)
    assert desfeita.evento is not None
    assert desfeita.evento.tipo is TipoDeEvento.CORRIGIR
    assert desfeita.evento.dados["campos"] == {"estoque": "2"}
    assert sessao.despensa["Peito de frango"].estoque.valor == Decimal(2)


def test_desfazer_duas_vezes_o_mesmo_evento_devolve_o_que_ja_foi_feito(
    editavel: DespensaEditavel,
) -> None:
    correcao = editavel.acabou("bacon")
    primeira = editavel.desfazer(correcao.evento.id)
    segunda = editavel.desfazer(correcao.evento.id)
    assert segunda.repetida
    assert segunda.evento == primeira.evento
    assert len(editavel.eventos()) == 2


def test_so_se_desfaz_a_ultima_mudanca_do_item(editavel: DespensaEditavel) -> None:
    primeira = editavel.corrigir("bacon", estoque=Decimal("0.3"))
    editavel.corrigir("bacon", estoque=Decimal("0.2"))
    with pytest.raises(ErroDeUso, match="última mudança"):
        editavel.desfazer(primeira.evento.id)
    with pytest.raises(Ausente):
        editavel.desfazer(999)


def test_nao_volta_um_item_quando_outro_tomou_o_nome(editavel: DespensaEditavel) -> None:
    remocao = editavel.remover("bacon")
    editavel.adicionar(nome="Bacon", estoque=Decimal("0.2"), unidade="kg")
    with pytest.raises(ErroDeUso, match="já há outro"):
        editavel.desfazer(remocao.evento.id)


# --------------------------------------------------------------------------- #
# Idempotência
# --------------------------------------------------------------------------- #


def test_a_mesma_chave_nao_grava_nem_debita_duas_vezes(sessao: Sessao) -> None:
    primeira = _creme(sessao.editavel, chave="c1f0e2d3")
    segunda = _creme(sessao.editavel, chave="c1f0e2d3")
    assert segunda.repetida
    assert segunda.evento == primeira.evento
    assert segunda.compra == primeira.compra
    assert len(sessao.editavel.eventos()) == 1
    assert sessao.dossie.orcamento().restante == Dinheiro.de("71.00")


def test_a_mesma_chave_para_outra_mudanca_e_erro(editavel: DespensaEditavel) -> None:
    editavel.acabou("bacon", chave="k1")
    assert editavel.acabou("bacon", chave="k1").repetida
    with pytest.raises(ErroDeUso, match="outra mudança"):
        editavel.remover("alcaparras", chave="k1")
    with pytest.raises(ErroDeUso, match="outra mudança"):
        editavel.adicionar(nome="Nata", estoque=Decimal(1), unidade="kg", chave="k1")


def test_remover_com_a_mesma_chave_devolve_a_mesma_remocao(sessao: Sessao) -> None:
    item_id = _creme(sessao.editavel).item_id
    primeira = sessao.editavel.remover(item_id, chave="r1")
    segunda = sessao.editavel.remover(item_id, chave="r1")
    assert segunda.repetida
    assert segunda.estornos == primeira.estornos
    assert sessao.dossie.orcamento().restante == Dinheiro.de("80.00")


# --------------------------------------------------------------------------- #
# Estorno de compra
# --------------------------------------------------------------------------- #


def test_estornar_a_compra_de_um_item_tira_o_item(sessao: Sessao) -> None:
    acrescimo = _creme(sessao.editavel)
    assert acrescimo.compra is not None
    estorno, mudanca = sessao.editavel.estornar_compra(acrescimo.compra.id)
    assert estorno.valor == Dinheiro.de("-9.00")
    assert mudanca is not None
    assert mudanca.evento is not None
    assert mudanca.evento.acao is Acao.ESTORNO
    assert "Creme de leite" not in sessao.despensa
    assert sessao.dossie.orcamento().restante == Dinheiro.de("80.00")
    # De novo: a mesma devolução, e nada a tirar.
    de_novo, sem_mudanca = sessao.editavel.estornar_compra(acrescimo.compra.id)
    assert de_novo == estorno
    assert sem_mudanca is None
    # Desfazer o estorno traz o item e debita de novo.
    sessao.editavel.desfazer(mudanca.evento.id)
    assert "Creme de leite" in sessao.despensa
    assert sessao.dossie.orcamento().restante == Dinheiro.de("71.00")


def test_estornar_uma_compra_para_prato_so_devolve(sessao: Sessao) -> None:
    sessao.dossie.registrar_compra("milho verde", Decimal(1), "lata", Dinheiro.de("6.00"))
    (compra,) = sessao.dossie.extrato()
    assert "milho verde" in sessao.dossie.compras()
    estorno, mudanca = sessao.editavel.estornar_compra(compra.id)
    assert mudanca is None
    assert estorno.estorna == compra.id
    assert sessao.dossie.compras() == {}
    assert sessao.dossie.orcamento().restante == Dinheiro.de("80.00")


def test_estorno_de_estorno_e_de_compra_que_nao_existe(sessao: Sessao) -> None:
    acrescimo = _creme(sessao.editavel)
    estorno, _ = sessao.editavel.estornar_compra(acrescimo.compra.id)
    with pytest.raises(ErroDeUso, match="já é uma devolução"):
        sessao.editavel.estornar_compra(estorno.id)
    with pytest.raises(Ausente):
        sessao.editavel.estornar_compra(999)


# --------------------------------------------------------------------------- #
# Reconstrução e duas portas
# --------------------------------------------------------------------------- #


def test_os_eventos_refazem_a_mesma_despensa_ao_reabrir(tmp_path: Path) -> None:
    banco = tmp_path / "dossie.db"
    primeira = abrir(banco)
    primeira.editavel.informar_embalagem("cobertura-de-chocolate", "400 g")
    item_id = _creme(primeira.editavel).item_id
    primeira.editavel.acabou("bacon")
    primeira.editavel.remover("alcaparras")
    esperada = {i.nome: (i.estoque, i.custo.valor, i.preco_pago) for i in primeira.despensa}
    primeira.dossie.fechar()

    reaberta = abrir(banco)
    try:
        assert {
            i.nome: (i.estoque, i.custo.valor, i.preco_pago) for i in reaberta.despensa
        } == esperada
        assert reaberta.despensa.por_id(item_id) is not None
        assert reaberta.dossie.orcamento().restante == Dinheiro.de("71.00")
        assert reaberta.editavel.estado().versao == 4
    finally:
        reaberta.dossie.fechar()


def test_duas_sessoes_no_mesmo_banco_veem_a_edicao_uma_da_outra(tmp_path: Path) -> None:
    banco = tmp_path / "dossie.db"
    tela, conversa = abrir(banco), abrir(banco)
    try:
        antes = conversa.despensa
        assert antes["Cobertura de chocolate"].embalagem_estimada is not None

        tela.editavel.informar_embalagem("cobertura-de-chocolate", "1 kg", canal=Canal.TELA)
        assert conversa.despensa is not antes
        assert conversa.despensa["Cobertura de chocolate"].linha.conteudo_informado
        assert conversa.despensa.pendencias == []

        conversa.editavel.adicionar(nome="Nata", estoque=Decimal("0.2"), unidade="kg")
        assert "Nata" in tela.despensa
        assert tela.editavel.estado().versao == conversa.editavel.estado().versao == 2
    finally:
        tela.dossie.fechar()
        conversa.dossie.fechar()


def test_gravacao_de_outra_tabela_por_outro_processo_nao_muda_a_despensa(tmp_path: Path) -> None:
    banco = tmp_path / "dossie.db"
    tela, conversa = abrir(banco), abrir(banco)
    try:
        tela.editavel.acabou("bacon")
        antes = {i.nome: i.estoque for i in tela.despensa}
        conversa.dossie.registrar_gosto("Arroz com frango", Gosto.GOSTA)
        assert {i.nome: i.estoque for i in tela.despensa} == antes
    finally:
        tela.dossie.fechar()
        conversa.dossie.fechar()


def _gravar_evento_cru(dossie: Dossie, **campos: Any) -> None:
    linha = {
        "chave": "cru:1",
        "item_id": "bacon",
        "tipo": "corrigir",
        "dados": json.dumps({"acao": "corrigir", "campos": {"unidade": "punhado"}}),
        "motivo": "",
        "canal": "tela",
        "registrado": datetime(2026, 9, 25, tzinfo=UTC).isoformat(),
        **campos,
    }
    with dossie.cursor() as cur:
        cur.execute(
            "INSERT INTO despensa_eventos (chave, item_id, tipo, dados, motivo, canal, registrado) "
            "VALUES (:chave, :item_id, :tipo, :dados, :motivo, :canal, :registrado)",
            linha,
        )


def test_evento_que_a_conta_de_hoje_recusa_fica_de_fora_sem_derrubar_a_despensa(
    sessao: Sessao, caplog: pytest.LogCaptureFixture
) -> None:
    _gravar_evento_cru(sessao.dossie)
    _gravar_evento_cru(sessao.dossie, chave="cru:2", item_id="caviar")
    _gravar_evento_cru(
        sessao.dossie, chave="cru:3", tipo="adicionar", item_id="bacon", dados=json.dumps({})
    )
    estado = sessao.editavel.estado()
    assert len(estado.ignorados) == 3
    assert len(sessao.despensa) == 37
    assert sessao.despensa["Bacon"].linha.unidade == "kg"
    assert not estado.pode_desfazer(estado.eventos[0])
    assert "ignorado" in caplog.text


def test_reconstruir_recusa_o_que_nao_cabe_no_estado(sessao: Sessao) -> None:
    agora = datetime(2026, 9, 25, tzinfo=UTC)

    def evento(id_: int, tipo: TipoDeEvento, item_id: str, dados: dict[str, Any]) -> Evento:
        return Evento(id_, f"k{id_}", item_id, tipo, dados, "", "tela", None, agora)

    linha_do_bacon = {
        "nome": "BACON",
        "estoque": "1",
        "unidade": "kg",
        "quantidade_comprada": "1",
        "preco_pago": None,
    }
    eventos = [
        evento(1, TipoDeEvento.RESTAURAR, "bacon", {}),  # já está na despensa
        evento(2, TipoDeEvento.REMOVER, "bacon", {}),
        evento(3, TipoDeEvento.REMOVER, "bacon", {}),  # já tinha sido tirado
        evento(4, TipoDeEvento.CORRIGIR, "bacon", {"campos": {"estoque": "1"}}),  # tirado
        evento(5, TipoDeEvento.ADICIONAR, "item-00000001", {"linha": linha_do_bacon}),
        evento(6, TipoDeEvento.RESTAURAR, "bacon", {}),  # outro tomou o nome
        evento(7, TipoDeEvento.ADICIONAR, "item-00000002", {"linha": linha_do_bacon}),  # nome
        evento(8, TipoDeEvento.ADICIONAR, "item-00000001", {"linha": linha_do_bacon}),  # id
    ]
    estado = reconstruir(sessao.planilha, eventos)
    assert estado.ignorados == (1, 3, 4, 6, 7, 8)
    assert estado.despensa.get("BACON") is not None
    assert estado.despensa.get("Bacon") is None


def test_escrita_que_falha_nao_deixa_o_cache_com_o_que_voltou(sessao: Sessao) -> None:
    sessao.editavel.estado()
    with pytest.raises(OrcamentoExcedido):
        _creme(sessao.editavel, preco_pago=Decimal("81.00"))
    assert sessao.editavel.estado().eventos == ()
    assert "Creme de leite" not in sessao.despensa


def test_tabela_nova_em_banco_antigo_e_criada_sem_perder_nada(tmp_path: Path) -> None:
    banco = tmp_path / "antigo.db"
    with Dossie(banco) as dossie:
        dossie.registrar_gasto("feira", Dinheiro.de("5.00"))
        with closing(dossie._conexao.cursor()) as cur:
            cur.execute("DROP TABLE IF EXISTS despensa_eventos")
    sessao = abrir(banco)
    try:
        sessao.editavel.acabou("bacon")
        assert sessao.dossie.orcamento().gasto == Dinheiro.de("5.00")
    finally:
        sessao.dossie.fechar()


# --------------------------------------------------------------------------- #
# Pequenas peças
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("unidade", "conteudo", "esperada"),
    [
        ("un", "1 kg", "un 1kg"),
        ("un", "400g", "un 400g"),
        ("un 400g", "380 g", "un 380g"),
        ("balde 2kg", "3 quilos", "balde 3kg"),
        ("un", "1,5 litro", "un 1,5L"),
        ("un", "1.5 L", "un 1,5L"),
        ("un", "500 ml", "un 500ml"),
        ("", "500 mg", "un 500mg"),
    ],
)
def test_unidade_com_o_conteudo_que_ela_informou(
    unidade: str, conteudo: str, esperada: str
) -> None:
    assert unidade_com_conteudo(unidade, conteudo) == esperada


@pytest.mark.parametrize(
    ("unidade", "conteudo", "mensagem"),
    [
        ("un", "meio quilo", "gramas, quilos"),
        ("un", "2 un", "gramas, quilos"),
        ("un", "0 g", "mais que zero"),
        ("kg", "1 kg", "direto em peso"),
    ],
)
def test_conteudo_que_nao_e_peso_nem_volume_e_recusado(
    unidade: str, conteudo: str, mensagem: str
) -> None:
    with pytest.raises(ErroDeUso, match=mensagem):
        unidade_com_conteudo(unidade, conteudo)


def test_informar_embalagem_sem_conteudo_e_erro(editavel: DespensaEditavel) -> None:
    with pytest.raises(ErroDeUso, match="quanto vem"):
        editavel.informar_embalagem("cobertura-de-chocolate", "  ")


def test_rotulo_do_evento_vai_e_volta() -> None:
    assert rotulo_do_evento(12) == "ev-0012"
    assert id_do_rotulo("ev-0012") == 12
    assert id_do_rotulo("7") == 7
    with pytest.raises(Ausente):
        id_do_rotulo("ev-abc")


def test_chave_do_nome_ignora_acento_caixa_e_espaco() -> None:
    assert chave_do_nome("  Óleo   de SOJA ") == chave_do_nome("oleo de soja")


def test_acao_desconhecida_no_evento_vira_correcao() -> None:
    evento = Evento(
        1,
        "k",
        "bacon",
        TipoDeEvento.CORRIGIR,
        {"acao": "outra"},
        "",
        "tela",
        None,
        datetime.now(UTC),
    )
    assert evento.acao is Acao.CORRIGIR
    assert evento.rotulo == "ev-0001"


def test_sinonimo_de_item_que_saiu_nao_casa_com_nada(sessao: Sessao) -> None:
    from mise.casamento import casar

    assert casar("frango", sessao.despensa).item is not None
    sessao.editavel.remover("peito-de-frango")
    casamento = casar("frango", sessao.despensa)
    assert casamento.item is None or casamento.item.nome != "Peito de frango"
    prato = receita(
        "Frango na chapa",
        [ingrediente("500 g de frango", "frango", 500, "g")],
        rendimento_porcoes=2,
    )
    avaliacao = sessao.avaliar(prato)
    assert [f.nome for f in avaliacao.faltantes] == ["frango"]


def test_prato_aceito_guarda_o_custo_daquele_momento(sessao: Sessao) -> None:
    perfil = PerfilCozinha.inicial()
    perfil = perfil.com_equipamentos((e, Posse.TEM) for e in perfil.equipamentos)
    perfil = perfil.com_tecnicas((t, Posse.TEM) for t in perfil.tecnicas)
    sessao.dossie.salvar_perfil(
        perfil.com_restricao("bocas_fogao", 4).com_restricao("tempo_max_por_fornada_min", 120)
    )
    sessao.dossie.registrar_gosto("Frango na chapa", Gosto.GOSTA)
    sessao.guardar(
        receita(
            "Frango na chapa",
            [ingrediente("500 g de frango", "frango", 500, "g")],
            rendimento_porcoes=2,
            modo_preparo=["Grelhe o frango na frigideira por 15 minutos."],
        )
    )
    registro, detalhes = sessao.decidir("Frango na chapa", "aceito", preco=25.0)
    assert detalhes["cmv_por_porcao"] == "R$ 3,50"
    sessao.editavel.corrigir("peito-de-frango", preco_pago=Decimal("40.00"))
    (guardado,) = sessao.dossie.historico("Frango na chapa")
    assert guardado.detalhes["cmv_por_porcao"] == "R$ 3,50"
    assert sessao.cmv_conferido("Frango na chapa").para_precificar == Dinheiro.de("5.00")
    assert registro.id == guardado.id
