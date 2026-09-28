"""O histórico da cozinha: cada mudança, com o valor de antes, o de depois e o canal."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mise import perfil_historico as historico
from mise.dossie import Canal, Dossie
from mise.erros import ErroDeUso, VocabularioDesconhecido
from mise.perfil import Gosto, PerfilCozinha, Posse
from mise.perfil_historico import (
    FUSO_DELA,
    DaGrade,
    EventoDoPerfil,
    Impacto,
    MudancaNoPerfil,
    TipoDeItem,
    calcular_impacto,
    quando_texto,
)
from mise.receita import IngredienteReceita, Receita
from mise.viabilidade import avaliar

if TYPE_CHECKING:
    from collections.abc import Iterator

    from mise.despensa import Despensa


@dataclass
class Relogio:
    """Relógio falso: o tempo anda só quando o teste manda."""

    agora: datetime = field(default_factory=lambda: datetime(2026, 9, 25, 12, 0, tzinfo=UTC))

    def __call__(self) -> datetime:
        return self.agora


@pytest.fixture
def relogio() -> Relogio:
    return Relogio()


@pytest.fixture
def dossie(tmp_path: Path, relogio: Relogio) -> Iterator[Dossie]:
    with Dossie(tmp_path / "dossie.db", relogio=relogio) as d:
        yield d


# --------------------------------------------------------------------------- #
# Mudanças e eventos
# --------------------------------------------------------------------------- #


def test_resposta_de_equipamento_vira_evento_com_antes_depois_e_canal(dossie: Dossie) -> None:
    mudanca = historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, "forno", Posse.TEM, Canal.TELA)

    assert mudanca.mudou
    assert dossie.carregar_perfil().tem_equipamento("forno") is Posse.TEM
    (evento,) = historico.eventos(dossie)
    assert evento == mudanca.evento
    assert (evento.tipo, evento.campo, evento.canal) == (
        TipoDeItem.EQUIPAMENTO,
        "forno",
        Canal.TELA,
    )
    assert evento.antes == {"estado": "desconhecido", "suposto": False}
    assert evento.depois == {"estado": "tem", "suposto": False}
    assert not evento.nao_sei
    assert evento.texto == "a senhora disse que tem forno"


def test_confirmar_o_que_era_suposto_e_mudanca(dossie: Dossie) -> None:
    """O fogão passa de suposto a dito por ela: mesmo "tem", outra coisa na tela."""
    mudanca = historico.mudar_item(
        dossie, TipoDeItem.EQUIPAMENTO, "fogao", Posse.TEM, Canal.CONVERSA
    )
    assert mudanca.evento is not None
    assert mudanca.evento.antes == {"estado": "tem", "suposto": True}
    assert mudanca.evento.depois == {"estado": "tem", "suposto": False}


def test_repetir_a_mesma_resposta_nao_enche_o_historico(dossie: Dossie) -> None:
    historico.mudar_item(dossie, TipoDeItem.TECNICA, "bechamel", Posse.TEM, Canal.TELA)
    repetida = historico.mudar_item(
        dossie, TipoDeItem.TECNICA, "bechamel", Posse.TEM, Canal.CONVERSA
    )
    assert not repetida.mudou
    assert repetida.antes == repetida.depois
    (evento,) = historico.eventos(dossie)
    assert evento.canal is Canal.TELA, "o 'atualizado por' continua sendo quem mudou"


def test_nao_sei_apaga_a_resposta_e_fica_marcado(dossie: Dossie) -> None:
    historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, "forno", Posse.NAO_TEM, Canal.TELA)
    mudanca = historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, "forno", None, Canal.CONVERSA)

    perfil = dossie.carregar_perfil()
    assert perfil.tem_equipamento("forno") is Posse.DESCONHECIDO
    assert "forno" not in perfil.confirmados
    assert mudanca.nao_sei
    assert mudanca.evento is not None
    assert mudanca.evento.nao_sei
    assert mudanca.evento.antes == {"estado": "nao_tem", "suposto": False}
    assert mudanca.evento.texto == "a senhora disse que não sabe se tem forno"


def test_nao_sei_do_fogao_deixa_de_ser_suposto(dossie: Dossie) -> None:
    """ "Não sei se tenho fogão": o fogão sai do suposto e fica em aberto, com o evento."""
    mudanca = historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, "fogao", None, Canal.CONVERSA)
    assert mudanca.evento is not None
    assert mudanca.evento.antes == {"estado": "tem", "suposto": True}
    assert mudanca.evento.depois == {"estado": "desconhecido", "suposto": False}
    assert mudanca.evento.texto == "a senhora disse que não sabe se tem fogão"
    assert dossie.carregar_perfil().tem_equipamento("fogao") is Posse.DESCONHECIDO
    assert historico.ela_disse_que_nao_sabe(dossie, "equipamento", "fogao")


def test_nao_tenho_fogao_vira_evento_com_o_texto_dela(dossie: Dossie) -> None:
    mudanca = historico.mudar_item(
        dossie, TipoDeItem.EQUIPAMENTO, "fogao", Posse.NAO_TEM, Canal.TELA
    )
    assert mudanca.evento is not None
    assert mudanca.evento.antes == {"estado": "tem", "suposto": True}
    assert mudanca.evento.depois == {"estado": "nao_tem", "suposto": False}
    assert mudanca.evento.texto == "a senhora disse que não tem fogão"


def test_nao_sei_sem_resposta_anterior_fica_registrado_uma_vez(dossie: Dossie) -> None:
    """De "ninguém perguntou" para "perguntei, e ela não sabe": é o que impede insistir."""
    mudanca = historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, "forno", None, Canal.CONVERSA)
    assert mudanca.mudou
    assert mudanca.antes == mudanca.depois == PerfilCozinha.inicial()
    (evento,) = historico.eventos(dossie)
    assert evento.nao_sei
    assert evento.antes == evento.depois == {"estado": "desconhecido", "suposto": False}
    assert historico.ela_disse_que_nao_sabe(dossie, "equipamento", "forno")

    de_novo = historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, "forno", None, Canal.TELA)
    assert not de_novo.mudou, "dois 'não sei' seguidos são um só"
    assert len(historico.eventos(dossie)) == 1

    historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, "forno", Posse.TEM, Canal.TELA)
    historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, "forno", None, Canal.TELA)
    assert [e.nao_sei for e in historico.eventos(dossie)] == [True, False, True]


def test_nao_sei_de_restricao_em_aberto_tambem_fica_registrado(dossie: Dossie) -> None:
    mudanca = historico.mudar_restricao(dossie, "bocas_fogao", None, Canal.TELA)
    assert mudanca.mudou
    assert mudanca.evento is not None
    assert mudanca.evento.texto == "a senhora disse que não sabe quantas bocas o fogão tem"


@pytest.mark.parametrize(
    ("posse", "texto"),
    [
        (Posse.TEM, "a senhora disse que tem prática com molho béchamel"),
        (Posse.NAO_TEM, "a senhora disse que não tem prática com molho béchamel"),
    ],
)
def test_texto_da_tecnica(dossie: Dossie, posse: Posse, texto: str) -> None:
    mudanca = historico.mudar_item(dossie, TipoDeItem.TECNICA, "bechamel", posse, Canal.TELA)
    assert mudanca.evento is not None
    assert mudanca.evento.texto == texto


def test_texto_da_tecnica_que_ela_nao_sabe(dossie: Dossie) -> None:
    historico.mudar_item(dossie, TipoDeItem.TECNICA, "bechamel", Posse.TEM, Canal.TELA)
    mudanca = historico.mudar_item(dossie, TipoDeItem.TECNICA, "bechamel", None, Canal.TELA)
    assert mudanca.evento is not None
    assert mudanca.evento.texto == "a senhora disse que não sabe se tem prática com molho béchamel"


def test_equipamento_negado_no_texto(dossie: Dossie) -> None:
    mudanca = historico.mudar_item(
        dossie, TipoDeItem.EQUIPAMENTO, "air_fryer", Posse.NAO_TEM, Canal.TELA
    )
    assert mudanca.evento is not None
    assert mudanca.evento.texto == "a senhora disse que não tem air fryer"


@pytest.mark.parametrize(
    ("campo", "valor", "texto"),
    [
        ("bocas_fogao", 4, "a senhora disse que o fogão tem 4 bocas"),
        ("bocas_fogao", 1, "a senhora disse que o fogão tem 1 boca"),
        (
            "tempo_max_por_fornada_min",
            90,
            "a senhora disse que consegue cozinhar 1,5 hora de uma vez",
        ),
        ("porcoes_por_fornada", 20, "a senhora disse que monta 20 marmitas numa leva"),
        (
            "espaco_geladeira_litros",
            12,
            "a senhora disse que cabem 12 litros de preparo na geladeira",
        ),
        ("espaco_geladeira_litros", 0, "a senhora disse que não sobra espaço na geladeira"),
        (
            "energia_aparelhos_simultaneos",
            2,
            "a senhora disse que liga 2 aparelhos fortes ao mesmo tempo",
        ),
        (
            "energia_aparelhos_simultaneos",
            1,
            "a senhora disse que liga 1 aparelho forte de cada vez",
        ),
        ("bocas_fogao", 0, "a senhora disse que o fogão tem 0 bocas"),
        (
            "tempo_max_por_fornada_min",
            100,
            "a senhora disse que consegue cozinhar 1 hora e 40 minutos de uma vez",
        ),
        ("porcoes_por_fornada", 1, "a senhora disse que monta 1 marmita numa leva"),
        (
            "espaco_geladeira_litros",
            1,
            "a senhora disse que cabe 1 litro de preparo na geladeira",
        ),
        (
            "energia_aparelhos_simultaneos",
            0,
            "a senhora disse que não consegue ligar nenhum aparelho forte",
        ),
        ("tem_gas_sobrando", True, "a senhora disse que tem botijão de gás de reserva"),
        ("tem_gas_sobrando", False, "a senhora disse que não tem botijão de gás de reserva"),
    ],
)
def test_restricao_vira_evento_em_palavras(
    dossie: Dossie, campo: str, valor: int | bool, texto: str
) -> None:
    mudanca = historico.mudar_restricao(dossie, campo, valor, Canal.TELA)
    assert mudanca.evento is not None
    assert mudanca.evento.antes == {"valor": None}
    assert mudanca.evento.depois == {"valor": valor}
    assert mudanca.evento.texto == texto
    assert getattr(dossie.carregar_perfil().restricoes, campo) == valor


@pytest.mark.parametrize(
    ("campo", "trecho"),
    [
        ("bocas_fogao", "quantas bocas o fogão tem"),
        ("tempo_max_por_fornada_min", "quanto tempo consegue cozinhar de uma vez"),
        ("porcoes_por_fornada", "quantas marmitas monta numa leva"),
        ("espaco_geladeira_litros", "quanto espaço sobra na geladeira"),
        ("energia_aparelhos_simultaneos", "quantos aparelhos fortes liga ao mesmo tempo"),
        ("tem_gas_sobrando", "se tem botijão de gás de reserva"),
    ],
)
def test_restricao_que_ela_nao_sabe(dossie: Dossie, campo: str, trecho: str) -> None:
    historico.mudar_restricao(dossie, campo, True if campo == "tem_gas_sobrando" else 3, Canal.TELA)
    mudanca = historico.mudar_restricao(dossie, campo, None, Canal.CONVERSA)
    assert mudanca.evento is not None
    assert mudanca.evento.nao_sei
    assert mudanca.evento.texto == f"a senhora disse que não sabe {trecho}"
    assert getattr(dossie.carregar_perfil().restricoes, campo) is None


def test_vocabulario_errado_e_recusado_sem_gravar(dossie: Dossie) -> None:
    with pytest.raises(VocabularioDesconhecido):
        historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, "bechamel", Posse.TEM, Canal.TELA)
    with pytest.raises(VocabularioDesconhecido):
        historico.mudar_item(dossie, TipoDeItem.TECNICA, "forno", None, Canal.TELA)
    with pytest.raises(ErroDeUso, match="desconhecida"):
        historico.mudar_restricao(dossie, "inventada", 3, Canal.TELA)
    with pytest.raises(ErroDeUso, match="mudar_restricao"):
        historico.mudar_item(dossie, TipoDeItem.OPERACIONAL, "bocas_fogao", Posse.TEM, Canal.TELA)
    assert historico.eventos(dossie) == ()
    assert dossie.carregar_perfil() == PerfilCozinha.inicial()


def test_canal_desconhecido_e_recusado_sem_gravar(dossie: Dossie) -> None:
    with pytest.raises(ErroDeUso, match="canal"):
        historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, "forno", Posse.TEM, "telepatia")
    assert dossie.carregar_perfil().tem_equipamento("forno") is Posse.DESCONHECIDO


def test_canal_em_texto_vale(dossie: Dossie) -> None:
    mudanca = historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, "forno", Posse.TEM, "conversa")
    assert mudanca.evento is not None
    assert mudanca.evento.canal is Canal.CONVERSA


def test_eventos_do_mais_recente_ao_mais_antigo(dossie: Dossie, relogio: Relogio) -> None:
    for i, item in enumerate(("forno", "air_fryer", "batedeira")):
        relogio.agora += timedelta(minutes=i + 1)
        historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, item, Posse.TEM, Canal.TELA)
    todos = historico.eventos(dossie)
    assert [e.campo for e in todos] == ["batedeira", "air_fryer", "forno"]
    assert [e.campo for e in historico.eventos(dossie, limite=2)] == ["batedeira", "air_fryer"]
    assert todos[0].registrado == relogio.agora


def test_ultimo_por_item_e_o_que_diz_quem_mudou(dossie: Dossie) -> None:
    historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, "forno", Posse.TEM, Canal.TELA)
    historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, "forno", Posse.NAO_TEM, Canal.CONVERSA)
    historico.mudar_restricao(dossie, "bocas_fogao", 4, Canal.TELA)

    ultimos = historico.ultimos_por_item(dossie)
    assert set(ultimos) == {
        (TipoDeItem.EQUIPAMENTO, "forno"),
        (TipoDeItem.OPERACIONAL, "bocas_fogao"),
    }
    assert ultimos[(TipoDeItem.EQUIPAMENTO, "forno")].canal is Canal.CONVERSA
    assert ultimos[(TipoDeItem.EQUIPAMENTO, "forno")].depois["estado"] == "nao_tem"


def test_ela_disse_que_nao_sabe(dossie: Dossie) -> None:
    assert not historico.ela_disse_que_nao_sabe(dossie, "equipamento", "forno")
    historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, "forno", Posse.TEM, Canal.TELA)
    assert not historico.ela_disse_que_nao_sabe(dossie, "equipamento", "forno")
    historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, "forno", None, Canal.TELA)
    assert historico.ela_disse_que_nao_sabe(dossie, "equipamento", "forno")
    assert not historico.ela_disse_que_nao_sabe(dossie, "gosto", "Feijoada"), (
        "gosto não tem histórico"
    )
    assert [e.campo for e in historico.itens_que_ela_nao_sabe(historico.eventos(dossie))] == [
        "forno"
    ]


def test_tabela_nasce_uma_vez_e_banco_antigo_ganha_a_tabela(tmp_path: Path) -> None:
    """Um dossiê de antes desta tabela abre, ganha `perfil_eventos` e continua com o perfil."""
    caminho = tmp_path / "antigo.db"
    with Dossie(caminho) as antigo:
        antigo.salvar_perfil(PerfilCozinha.inicial().com_equipamento("forno", Posse.TEM))
    with closing(sqlite3.connect(caminho)) as cru:
        tabelas = {n for (n,) in cru.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "perfil_eventos" not in tabelas

    with Dossie(caminho) as d:
        historico.garantir(d)
        historico.garantir(d)
        assert historico.eventos(d) == ()
        assert d.carregar_perfil().tem_equipamento("forno") is Posse.TEM


def test_duas_portas_no_mesmo_arquivo_nao_apagam_a_resposta_da_outra(tmp_path: Path) -> None:
    """A tela e a conversa gravam no mesmo dossiê: cada uma lê o que a outra gravou."""
    caminho = tmp_path / "dossie.db"
    with Dossie(caminho) as tela, Dossie(caminho) as conversa:
        historico.mudar_item(tela, TipoDeItem.EQUIPAMENTO, "forno", Posse.TEM, Canal.TELA)
        historico.mudar_item(
            conversa, TipoDeItem.EQUIPAMENTO, "batedeira", Posse.NAO_TEM, Canal.CONVERSA
        )
        perfil = tela.carregar_perfil()
        assert perfil.tem_equipamento("forno") is Posse.TEM
        assert perfil.tem_equipamento("batedeira") is Posse.NAO_TEM
        assert [(e.campo, e.canal) for e in historico.eventos(tela)] == [
            ("batedeira", Canal.CONVERSA),
            ("forno", Canal.TELA),
        ]


def test_falha_no_meio_nao_grava_nem_o_perfil_nem_o_evento(
    dossie: Dossie, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Perfil e evento vão juntos: sem o evento, a tela diria que ninguém mudou o forno."""

    def quebra(*_: object, **__: object) -> EventoDoPerfil:
        raise sqlite3.OperationalError("disco cheio")

    historico.garantir(dossie)
    monkeypatch.setattr(historico, "_inserir", quebra)
    with pytest.raises(sqlite3.OperationalError):
        historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, "forno", Posse.TEM, Canal.TELA)
    monkeypatch.undo()
    assert dossie.carregar_perfil().tem_equipamento("forno") is Posse.DESCONHECIDO
    assert historico.eventos(dossie) == ()


# --------------------------------------------------------------------------- #
# Datas como ela lê
# --------------------------------------------------------------------------- #


AGORA = datetime(2026, 9, 25, 15, 0, tzinfo=UTC)  # 12:00 em Brasília


@pytest.mark.parametrize(
    ("momento", "texto"),
    [
        (datetime(2026, 9, 25, 12, 12, tzinfo=UTC), "hoje, 09:12"),
        (datetime(2026, 9, 25, 2, 30, tzinfo=UTC), "ontem, 23:30"),
        (datetime(2026, 9, 24, 21, 40, tzinfo=UTC), "ontem, 18:40"),
        (datetime(2026, 9, 12, 17, 32, tzinfo=UTC), "12/09, 14:32"),
        (datetime(2025, 12, 31, 13, 0, tzinfo=UTC), "31/12/2025, 10:00"),
        (datetime(2026, 9, 25, 12, 12), "hoje, 09:12"),  # sem fuso é UTC, como o dossiê grava
    ],
)
def test_data_como_ela_le(momento: datetime, texto: str) -> None:
    assert quando_texto(momento, AGORA) == texto


def test_fuso_dela_e_brasilia() -> None:
    assert FUSO_DELA.utcoffset(None) == timedelta(hours=-3)


# --------------------------------------------------------------------------- #
# Impacto nas receitas
# --------------------------------------------------------------------------- #


def _frango_assado() -> Receita:
    return Receita(
        nome="Frango assado",
        ingredientes=(
            IngredienteReceita("500 g de peito de frango", "peito de frango", Decimal(500), "g"),
        ),
        rendimento_porcoes=4,
        modo_preparo=("Leve ao forno a 180 C por 40 minutos.",),
    ).com_exigencias_detectadas()


def _arroz() -> Receita:
    return Receita(
        nome="Arroz simples",
        ingredientes=(IngredienteReceita("1 xícara de arroz", "arroz", Decimal(1), "xicara"),),
        rendimento_porcoes=2,
        modo_preparo=("Refogue o arroz e cozinhe na panela por 20 minutos.",),
    ).com_exigencias_detectadas()


def _mudanca(
    antes: PerfilCozinha,
    depois: PerfilCozinha,
    tipo: TipoDeItem,
    campo: str,
    *,
    nao_sei: bool = False,
) -> MudancaNoPerfil:
    evento = EventoDoPerfil(
        1, tipo, campo, {}, {}, nao_sei, Canal.TELA, datetime(2026, 9, 25, tzinfo=UTC)
    )
    return MudancaNoPerfil(tipo, campo, antes, depois, nao_sei, evento)


@pytest.fixture
def avaliador(despensa: Despensa):
    def avaliar_com(receita: Receita, perfil: PerfilCozinha):
        return avaliar(receita, perfil, despensa, gosto=Gosto.GOSTA)

    return avaliar_com


def _completo() -> PerfilCozinha:
    p = PerfilCozinha.inicial()
    p = p.com_equipamentos((e, Posse.TEM) for e in p.equipamentos)
    p = p.com_tecnicas((t, Posse.TEM) for t in p.tecnicas)
    for campo, valor in (
        ("bocas_fogao", 4),
        ("tempo_max_por_fornada_min", 240),
        ("porcoes_por_fornada", 20),
        ("tem_gas_sobrando", True),
        ("espaco_geladeira_litros", 30),
        ("energia_aparelhos_simultaneos", 3),
    ):
        p = p.com_restricao(campo, valor)
    return p


def _forno_por_decidir() -> PerfilCozinha:
    """Cozinha completa, menos o forno e os dois que o substituem: ninguém perguntou."""
    p = _completo()
    for item in ("forno", "air_fryer", "forno_eletrico"):
        p = p.sem_resposta(item)
    return p


def test_ter_o_forno_libera_o_frango_assado(avaliador) -> None:
    sem = _forno_por_decidir()
    com = sem.com_equipamento("forno", Posse.TEM)
    impacto = calcular_impacto(
        _mudanca(sem, com, TipoDeItem.EQUIPAMENTO, "forno"), [_frango_assado(), _arroz()], avaliador
    )
    assert impacto.liberadas == ("Frango assado",)
    assert impacto.bloqueadas == impacto.pendentes == ()
    assert impacto.texto == "Com forno, Frango assado passa a dar."


def test_sem_forno_nem_substituto_bloqueia(avaliador) -> None:
    antes = _completo()
    depois = (
        antes.com_equipamento("forno", Posse.NAO_TEM)
        .com_equipamento("air_fryer", Posse.NAO_TEM)
        .com_equipamento("forno_eletrico", Posse.NAO_TEM)
    )
    impacto = calcular_impacto(
        _mudanca(antes, depois, TipoDeItem.EQUIPAMENTO, "forno"), [_frango_assado()], avaliador
    )
    assert impacto.bloqueadas == ("Frango assado",)
    assert impacto.texto == "Sem forno, Frango assado deixa de dar."


def test_sem_forno_com_air_fryer_por_perguntar_fica_dependendo(avaliador) -> None:
    """ "Não tenho forno" abre a pergunta da air fryer: o prato ainda pode dar."""
    antes = _forno_por_decidir()
    depois = antes.com_equipamento("forno", Posse.NAO_TEM)
    impacto = calcular_impacto(
        _mudanca(antes, depois, TipoDeItem.EQUIPAMENTO, "forno"), [_frango_assado()], avaliador
    )
    assert impacto.pendentes == ("Frango assado",)
    assert impacto.texto == "Sem forno, Frango assado fica dependendo de uma resposta da senhora."


def test_nao_sei_volta_a_depender_de_resposta(avaliador) -> None:
    antes = _forno_por_decidir().com_equipamento("forno", Posse.TEM)
    depois = antes.sem_resposta("forno")
    impacto = calcular_impacto(
        _mudanca(antes, depois, TipoDeItem.EQUIPAMENTO, "forno", nao_sei=True),
        [_frango_assado(), _arroz()],
        avaliador,
    )
    assert impacto.pendentes == ("Frango assado",)
    assert impacto.texto == "Frango assado fica dependendo de uma resposta da senhora."


def test_sem_fogao_a_receita_de_fogao_deixa_de_dar(avaliador) -> None:
    antes = _completo()
    depois = antes.com_equipamento("fogao", Posse.NAO_TEM)
    impacto = calcular_impacto(
        _mudanca(antes, depois, TipoDeItem.EQUIPAMENTO, "fogao"), [_arroz()], avaliador
    )
    assert impacto.bloqueadas == ("Arroz simples",)
    assert impacto.texto == "Sem fogão, Arroz simples deixa de dar."


def test_nao_sei_do_fogao_deixa_a_receita_esperando_resposta(avaliador) -> None:
    antes = _completo()
    depois = antes.sem_resposta("fogao")
    impacto = calcular_impacto(
        _mudanca(antes, depois, TipoDeItem.EQUIPAMENTO, "fogao", nao_sei=True),
        [_arroz()],
        avaliador,
    )
    assert impacto.pendentes == ("Arroz simples",)
    assert impacto.texto == "Arroz simples fica dependendo de uma resposta da senhora."


def test_restricao_sem_causa_no_texto(avaliador) -> None:
    antes = _completo()
    # Uma hora por cozinhada: as 2 h da feijoada não cabem; os 20 min do arroz, sim.
    depois = antes.com_restricao("tempo_max_por_fornada_min", 60)
    receita = Receita(
        nome="Feijoada",
        ingredientes=(IngredienteReceita("1 kg de feijão", "feijão", Decimal(1), "kg"),),
        modo_preparo=("Cozinhe na panela de pressão.",),
        tempo_cozimento_min=120,
    ).com_exigencias_detectadas()
    impacto = calcular_impacto(
        _mudanca(antes, depois, TipoDeItem.OPERACIONAL, "tempo_max_por_fornada_min"),
        [receita, _arroz()],
        avaliador,
    )
    assert impacto.bloqueadas == ("Feijoada",)
    assert impacto.texto == "Feijoada deixa de dar."


def test_tecnica_nao_leva_causa_no_texto(avaliador) -> None:
    receita = Receita(
        nome="Lasanha",
        ingredientes=(IngredienteReceita("500 g de macarrão", "macarrão", Decimal(500), "g"),),
        rendimento_porcoes=6,
        modo_preparo=("Faça o molho branco (béchamel) e monte em camadas.",),
    ).com_exigencias_detectadas()
    antes = _completo().com_tecnica("bechamel", Posse.TEM)
    depois = antes.com_tecnica("bechamel", Posse.NAO_TEM)
    impacto = calcular_impacto(
        _mudanca(antes, depois, TipoDeItem.TECNICA, "bechamel"), [receita], avaliador
    )
    assert impacto.bloqueadas == ("Lasanha",)
    assert impacto.texto == "Lasanha deixa de dar."


def test_varias_receitas_no_plural_e_com_mais_n(avaliador) -> None:
    receitas = [
        Receita(
            nome=nome,
            ingredientes=(
                IngredienteReceita("500 g de frango", "peito de frango", Decimal(500), "g"),
            ),
            rendimento_porcoes=4,
            modo_preparo=("Asse no forno por 40 minutos.",),
        ).com_exigencias_detectadas()
        for nome in ("Frango assado", "Coxa assada", "Sobrecoxa", "Peito recheado", "Asinha")
    ]
    sem = _forno_por_decidir()
    com = sem.com_equipamento("forno", Posse.TEM)
    impacto = calcular_impacto(
        _mudanca(sem, com, TipoDeItem.EQUIPAMENTO, "forno"), receitas[:2], avaliador
    )
    assert impacto.texto == "Com forno, Frango assado e Coxa assada passam a dar."
    impacto = calcular_impacto(
        _mudanca(sem, com, TipoDeItem.EQUIPAMENTO, "forno"), receitas, avaliador
    )
    assert impacto.texto == (
        "Com forno, Frango assado, Coxa assada, Sobrecoxa e mais 2 receitas passam a dar."
    )
    assert len(impacto.liberadas) == 5
    impacto = calcular_impacto(
        _mudanca(sem, com, TipoDeItem.EQUIPAMENTO, "forno"), receitas[:4], avaliador
    )
    assert impacto.texto == (
        "Com forno, Frango assado, Coxa assada, Sobrecoxa e mais 1 receita passam a dar."
    )


def test_quando_nada_muda_o_texto_diz(avaliador) -> None:
    antes = _completo()
    depois = antes.com_equipamento("batedeira", Posse.NAO_TEM)
    impacto = calcular_impacto(
        _mudanca(antes, depois, TipoDeItem.EQUIPAMENTO, "batedeira"), [_arroz()], avaliador
    )
    assert impacto == Impacto("Anotado. Nenhuma receita em avaliação muda com isso.")


def test_sem_receita_em_avaliacao(avaliador) -> None:
    antes = _completo()
    impacto = calcular_impacto(
        _mudanca(
            antes, antes.com_equipamento("forno", Posse.NAO_TEM), TipoDeItem.EQUIPAMENTO, "forno"
        ),
        [],
        avaliador,
    )
    assert "Ainda não há receita em avaliação" in impacto.texto


def test_resposta_repetida_nem_reavalia(avaliador) -> None:
    p = _completo()
    chamadas: list[str] = []

    def contar(receita: Receita, perfil: PerfilCozinha):
        chamadas.append(receita.nome)
        return avaliador(receita, perfil)

    sem_mudanca = MudancaNoPerfil(TipoDeItem.EQUIPAMENTO, "forno", p, p, False, None)
    impacto = calcular_impacto(sem_mudanca, [_frango_assado()], contar)
    assert impacto.texto == "Isso já estava anotado assim; nada muda nas receitas."
    assert chamadas == []


def test_impacto_em_json() -> None:
    impacto = Impacto("Texto.", ("A",), ("B",), ("C",))
    assert impacto.para_json() == {
        "liberadas": ["A"],
        "bloqueadas": ["B"],
        "pendentes": ["C"],
        "texto": "Texto.",
    }


# --------------------------------------------------------------------------- #
# As receitas do catálogo: contam as que mudam de aba na grade
# --------------------------------------------------------------------------- #


def test_receita_do_catalogo_que_muda_de_aba_entra_no_impacto(avaliador) -> None:
    """A do catálogo passa de "falta uma resposta" para "dá para fazer": entra no texto."""
    sem = _forno_por_decidir()
    com = sem.com_equipamento("forno", Posse.TEM)
    impacto = calcular_impacto(
        _mudanca(sem, com, TipoDeItem.EQUIPAMENTO, "forno"),
        [],
        avaliador,
        do_catalogo=[DaGrade(_frango_assado()), DaGrade(_arroz())],
    )
    assert impacto.liberadas == ("Frango assado",)
    assert impacto.texto == "Com forno, Frango assado passa a dar."


def test_receita_do_catalogo_que_sai_da_grade_deixa_de_dar(avaliador) -> None:
    antes = _completo()
    depois = antes.com_equipamento("fogao", Posse.NAO_TEM)
    impacto = calcular_impacto(
        _mudanca(antes, depois, TipoDeItem.EQUIPAMENTO, "fogao"),
        [],
        avaliador,
        do_catalogo=[DaGrade(_arroz(), nao_quer=True)],
    )
    assert impacto.bloqueadas == ("Arroz simples",)


def test_receita_do_catalogo_que_ela_nao_quer_continua_na_mesma_aba(avaliador) -> None:
    """Liberar a cozinha não tira da aba "não quer" a receita que ela recusou."""
    sem = _forno_por_decidir()
    com = sem.com_equipamento("forno", Posse.TEM)
    impacto = calcular_impacto(
        _mudanca(sem, com, TipoDeItem.EQUIPAMENTO, "forno"),
        [],
        avaliador,
        do_catalogo=[DaGrade(_frango_assado(), nao_quer=True)],
    )
    assert impacto.liberadas == impacto.bloqueadas == impacto.pendentes == ()
    assert impacto.texto == "Anotado. Nenhuma receita muda com isso."


def test_receita_do_catalogo_que_passa_a_pedir_resposta(avaliador) -> None:
    antes = _forno_por_decidir().com_equipamento("forno", Posse.TEM)
    depois = antes.sem_resposta("forno")
    impacto = calcular_impacto(
        _mudanca(antes, depois, TipoDeItem.EQUIPAMENTO, "forno", nao_sei=True),
        [],
        avaliador,
        do_catalogo=[DaGrade(_frango_assado())],
    )
    assert impacto.pendentes == ("Frango assado",)
