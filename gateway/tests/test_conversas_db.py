"""O banco das conversas: o histórico que a tela mostra, e que sobrevive ao backend."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from gateway import conversas_db as cdb
from gateway.conversas_db import (
    TITULO_PADRAO,
    BancoDeConversas,
    EstadoDoTurno,
    Papel,
    caminho_do_banco,
    fuso_dela,
    quando_texto,
    titulo_automatico,
)

SAO_PAULO = timezone(timedelta(hours=-3))


class Relogio:
    """Um relógio que anda à mão."""

    def __init__(self) -> None:
        self.agora = datetime(2026, 9, 25, 17, 30, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.agora

    def andar(self, **quanto: float) -> None:
        self.agora += timedelta(**quanto)


@pytest.fixture
def relogio() -> Relogio:
    return Relogio()


@pytest.fixture
def banco(tmp_path: Path, relogio: Relogio) -> BancoDeConversas:
    return BancoDeConversas(tmp_path / "estado" / "conversas.db", relogio)


# --------------------------------------------------------------------------- #
# Onde mora                                                                    #
# --------------------------------------------------------------------------- #


def test_mora_ao_lado_do_dossie() -> None:
    assert caminho_do_banco({"MISE_DOSSIE": "/x/.estado/dossie.db"}) == Path(
        "/x/.estado/conversas.db"
    )


def test_variavel_propria_vence() -> None:
    assert caminho_do_banco({"MISE_DOSSIE": "/x/dossie.db", "MISE_CONVERSAS": "/y/c.db"}) == Path(
        "/y/c.db"
    )


def test_sem_dossie_usa_a_pasta_padrao_do_motor() -> None:
    assert caminho_do_banco({}) == Path("~/.mise/conversas.db").expanduser()


def test_do_ambiente_cria_a_pasta(tmp_path: Path) -> None:
    banco = BancoDeConversas.do_ambiente({"MISE_DOSSIE": str(tmp_path / "novo" / "dossie.db")})
    assert banco.caminho == tmp_path / "novo" / "conversas.db"
    assert banco.caminho.parent.is_dir()
    antes = datetime.now(UTC)
    assert banco.criar_conversa().criada >= antes, "sem relógio injetado, vale o agora de verdade"
    banco.fechar()


# --------------------------------------------------------------------------- #
# Conversas                                                                    #
# --------------------------------------------------------------------------- #


def test_conversa_nova_vira_a_atual(banco: BancoDeConversas) -> None:
    primeira = banco.criar_conversa()
    segunda = banco.criar_conversa("Receitas com alcaparras")
    assert primeira.id.startswith("cv-") and primeira.titulo == TITULO_PADRAO
    assert banco.atual() == segunda.id
    assert segunda.titulo_dela is True
    anterior = banco.conversa(primeira.id)
    assert anterior is not None and anterior.atual is False


def test_conversa_sem_virar_atual(banco: BancoDeConversas) -> None:
    atual = banco.criar_conversa()
    banco.criar_conversa(atual=False)
    assert banco.atual() == atual.id


def test_lista_da_mais_recente(banco: BancoDeConversas, relogio: Relogio) -> None:
    a = banco.criar_conversa()
    relogio.andar(minutes=1)
    b = banco.criar_conversa()
    relogio.andar(minutes=1)
    banco.tocar(a.id)
    assert [c.id for c in banco.conversas()] == [a.id, b.id]


def test_marcar_atual(banco: BancoDeConversas) -> None:
    a = banco.criar_conversa()
    banco.criar_conversa()
    banco.marcar_atual(a.id)
    assert banco.atual() == a.id
    assert sum(c.atual for c in banco.conversas()) == 1


def test_renomear_e_o_automatico_nao_troca_mais(banco: BancoDeConversas) -> None:
    conversa = banco.criar_conversa()
    banco.dar_titulo_automatico(conversa.id, "quero vender arroz com frango")
    assert (c := banco.conversa(conversa.id)) is not None
    assert c.titulo == "Quero vender arroz com frango"
    banco.renomear(conversa.id, "  Arroz\n com   frango ")
    banco.dar_titulo_automatico(conversa.id, "outra coisa")
    assert (c := banco.conversa(conversa.id)) is not None
    assert (c.titulo, c.titulo_dela) == ("Arroz com frango", True)
    banco.renomear(conversa.id, "   ")
    assert (c := banco.conversa(conversa.id)) is not None
    assert c.titulo == TITULO_PADRAO


def test_titulo_automatico_so_na_primeira(banco: BancoDeConversas) -> None:
    conversa = banco.criar_conversa()
    banco.dar_titulo_automatico(conversa.id, "Primeira pergunta")
    banco.dar_titulo_automatico(conversa.id, "Segunda pergunta")
    assert (c := banco.conversa(conversa.id)) is not None
    assert c.titulo == "Primeira pergunta"


def test_titulo_automatico_corta_na_palavra() -> None:
    texto = "oi! quanto eu já gastei na despensa e o que tem de mais caro parado lá?"
    titulo = titulo_automatico(texto)
    assert titulo is not None and titulo.endswith("…")
    assert titulo.startswith("Oi! quanto eu já gastei")
    assert len(titulo) <= cdb.TAMANHO_DO_TITULO_AUTOMATICO + 1
    assert titulo_automatico("\n\n  ?!  \n") is None
    assert titulo_automatico("\n bolo de cenoura\nsegunda linha") == "Bolo de cenoura"


def test_titulo_automatico_vazio_nao_mexe(banco: BancoDeConversas) -> None:
    conversa = banco.criar_conversa()
    banco.dar_titulo_automatico(conversa.id, "   ")
    assert (c := banco.conversa(conversa.id)) is not None
    assert c.titulo == TITULO_PADRAO


def test_apagar_leva_mensagens_e_turnos_e_passa_a_atual(
    banco: BancoDeConversas, relogio: Relogio
) -> None:
    antiga = banco.criar_conversa()
    relogio.andar(minutes=1)
    atual = banco.criar_conversa()
    mensagem = banco.inserir_mensagem(
        atual.id, Papel.SENHORA, [{"tipo": "texto", "texto": "oi"}], estado="enviada"
    )
    turno = banco.criar_turno(atual.id, mensagem, "u-1")
    assert banco.apagar(atual.id) == antiga.id
    assert banco.conversa(atual.id) is None
    assert banco.mensagem(mensagem) is None
    assert banco.turno(turno.id) is None


def test_apagar_a_que_nao_e_atual_mantem_a_atual(banco: BancoDeConversas) -> None:
    outra = banco.criar_conversa()
    atual = banco.criar_conversa()
    assert banco.apagar(outra.id) == atual.id
    assert banco.apagar("cv-nao-existe") == atual.id


def test_apagar_a_ultima_fica_sem_atual(banco: BancoDeConversas) -> None:
    unica = banco.criar_conversa()
    assert banco.apagar(unica.id) is None


def test_sessao_do_hermes_e_tokens(banco: BancoDeConversas) -> None:
    conversa = banco.criar_conversa()
    banco.usar_sessao_hermes(conversa.id, "api_1", nova=True)
    banco.registrar_tokens(conversa.id, 90_000)
    banco.usar_sessao_hermes(conversa.id, "api_1_filha", nova=False)
    assert (c := banco.conversa(conversa.id)) is not None
    assert (c.hermes_session_id, c.sessoes_hermes, c.tokens_prompt_ultimo) == (
        "api_1_filha",
        1,
        90_000,
    )
    banco.usar_sessao_hermes(conversa.id, "api_2", nova=True)
    assert (c := banco.conversa(conversa.id)) is not None
    assert (c.sessoes_hermes, c.tokens_prompt_ultimo) == (2, 0)
    banco.registrar_tokens(conversa.id, -5)
    assert (c := banco.conversa(conversa.id)) is not None
    assert c.tokens_prompt_ultimo == 0


# --------------------------------------------------------------------------- #
# Mensagens                                                                    #
# --------------------------------------------------------------------------- #


def test_mensagens_na_ordem_e_o_limite(banco: BancoDeConversas) -> None:
    conversa = banco.criar_conversa()
    ids = [
        banco.inserir_mensagem(
            conversa.id, Papel.SENHORA, [{"tipo": "texto", "texto": f"m{i}"}], estado="enviada"
        )
        for i in range(5)
    ]
    assert [m.id for m in banco.mensagens(conversa.id)] == ids
    assert [m.id for m in banco.mensagens(conversa.id, limite=2)] == ids[-2:]
    assert banco.contar_mensagens(conversa.id) == 5


def test_mensagem_da_consultora_guarda_tudo(banco: BancoDeConversas) -> None:
    conversa = banco.criar_conversa()
    mensagem_id = banco.inserir_mensagem(
        conversa.id,
        Papel.CONSULTORA,
        [{"tipo": "texto", "texto": "Dá pra fazer, R$ 2,47."}],
        estado="concluido",
        turno_id="t-1",
        texto_final="Dá pra fazer, R$ 2,47.",
        retirados=1,
        extras={"atividades": [{"rotulo_feito": "olhei sua despensa"}]},
    )
    mensagem = banco.mensagem(mensagem_id)
    assert mensagem is not None
    assert mensagem.papel is Papel.CONSULTORA
    assert (mensagem.turno_id, mensagem.retirados, mensagem.estado) == ("t-1", 1, "concluido")
    assert mensagem.extras["atividades"][0]["rotulo_feito"] == "olhei sua despensa"
    assert banco.textos_finais(conversa.id) == ["Dá pra fazer, R$ 2,47."]


def test_falas_dela_so_o_texto_dela(banco: BancoDeConversas) -> None:
    conversa = banco.criar_conversa()
    banco.inserir_mensagem(
        conversa.id,
        Papel.SENHORA,
        [{"tipo": "texto", "texto": "a lata sai R$ 6"}, {"tipo": "outra"}, "lixo"],  # type: ignore[list-item]
        estado="enviada",
    )
    banco.inserir_mensagem(
        conversa.id, Papel.CONSULTORA, [{"tipo": "texto", "texto": "R$ 9"}], estado="concluido"
    )
    assert banco.falas_dela(conversa.id) == ["a lata sai R$ 6"]


def test_json_quebrado_no_banco_nao_derruba_a_leitura(banco: BancoDeConversas) -> None:
    conversa = banco.criar_conversa()
    mensagem_id = banco.inserir_mensagem(conversa.id, Papel.SENHORA, [], estado="enviada")
    turno = banco.criar_turno(conversa.id, mensagem_id, None)
    with sqlite3.connect(banco.caminho) as conexao:
        conexao.execute(
            "UPDATE mensagens SET partes = '{', extras = '[1]' WHERE id = ?", (mensagem_id,)
        )
        conexao.execute("UPDATE turnos SET valores = 'x' WHERE id = ?", (turno.id,))
    mensagem = banco.mensagem(mensagem_id)
    assert mensagem is not None and (mensagem.partes, mensagem.extras) == ([], {})
    assert banco.falas_dela(conversa.id) == []
    assert banco.valores_conferidos(conversa.id) == set()


# --------------------------------------------------------------------------- #
# Turnos                                                                       #
# --------------------------------------------------------------------------- #


def test_turno_do_comeco_ao_fim(banco: BancoDeConversas, relogio: Relogio) -> None:
    conversa = banco.criar_conversa()
    turno = banco.criar_turno(conversa.id, "m-1", "u-5e1d")
    assert turno.estado is EstadoDoTurno.EM_ANDAMENTO
    assert banco.turno_em_andamento(conversa.id) == turno
    banco.registrar_run(turno.id, "run_1")
    relogio.andar(seconds=20)
    banco.terminar_turno(
        turno.id,
        EstadoDoTurno.CONCLUIDO,
        ultimo_seq=9,
        valores=(Decimal("663.39"), Decimal("82.00")),
    )
    fim = banco.turno(turno.id)
    assert fim is not None
    assert (fim.estado, fim.run_id, fim.ultimo_seq) == (EstadoDoTurno.CONCLUIDO, "run_1", 9)
    assert fim.terminado == relogio.agora
    assert fim.estado.terminado
    assert banco.turno_em_andamento(conversa.id) is None
    assert banco.valores_conferidos(conversa.id) == {Decimal("663.39"), Decimal("82.00")}


def test_turno_que_falhou_guarda_o_motivo(banco: BancoDeConversas) -> None:
    conversa = banco.criar_conversa()
    turno = banco.criar_turno(conversa.id, None, None)
    banco.terminar_turno(
        turno.id,
        EstadoDoTurno.FALHOU,
        ultimo_seq=3,
        erro_categoria="rede",
        erro_mensagem="O agente está fora do ar agora.",
    )
    fim = banco.turno(turno.id)
    assert fim is not None
    assert (fim.erro_categoria, fim.erro_mensagem) == (
        "rede",
        "O agente está fora do ar agora.",
    )


def test_turno_do_cliente_pega_o_mais_recente(banco: BancoDeConversas, relogio: Relogio) -> None:
    conversa = banco.criar_conversa()
    primeiro = banco.criar_turno(conversa.id, "m-1", "u-1")
    banco.terminar_turno(primeiro.id, EstadoDoTurno.FALHOU, ultimo_seq=2)
    segundo = banco.criar_turno(conversa.id, "m-1", "u-1")
    achado = banco.turno_do_cliente(conversa.id, "u-1")
    assert achado is not None and achado.id == segundo.id
    assert banco.turno_do_cliente(conversa.id, "u-2") is None


def test_arranque_marca_o_que_estava_em_andamento(tmp_path: Path, relogio: Relogio) -> None:
    caminho = tmp_path / "conversas.db"
    antes = BancoDeConversas(caminho, relogio)
    conversa = antes.criar_conversa()
    vivo = antes.criar_turno(conversa.id, None, "u-1")
    feito = antes.criar_turno(conversa.id, None, "u-2")
    antes.terminar_turno(feito.id, EstadoDoTurno.CONCLUIDO, ultimo_seq=4)
    antes.fechar()

    depois = BancoDeConversas(caminho, relogio)
    assert depois.marcar_interrompidos() == [vivo.id]
    turno = depois.turno(vivo.id)
    assert turno is not None and turno.estado is EstadoDoTurno.INTERROMPIDO
    assert turno.terminado is not None
    concluido = depois.turno(feito.id)
    assert concluido is not None and concluido.estado is EstadoDoTurno.CONCLUIDO
    assert depois.marcar_interrompidos() == []


def test_transacao_que_falha_desfaz(banco: BancoDeConversas) -> None:
    """Mensagem de conversa que não existe: a chave estrangeira recusa, nada fica gravado."""
    with pytest.raises(sqlite3.IntegrityError):
        banco.inserir_mensagem("cv-nao-existe", Papel.SENHORA, [], estado="enviada")
    assert banco.mensagens("cv-nao-existe") == []


# --------------------------------------------------------------------------- #
# Datas prontas                                                                #
# --------------------------------------------------------------------------- #


AGORA = datetime(2026, 9, 25, 18, 0, tzinfo=UTC)  # 15:00 em São Paulo, sexta


@pytest.mark.parametrize(
    ("quando", "com_hora", "esperado"),
    [
        (AGORA - timedelta(minutes=5), True, "hoje, 14:55"),
        (AGORA + timedelta(minutes=5), True, "hoje, 15:05"),
        (AGORA - timedelta(days=1), True, "ontem, 15:00"),
        (AGORA - timedelta(days=1), False, "ontem"),
        (AGORA - timedelta(days=3), True, "terça, 15:00"),
        (AGORA - timedelta(days=3), False, "terça"),
        (AGORA - timedelta(days=12), True, "13/09, 15:00"),
        (AGORA - timedelta(days=400), True, "21/08/2025"),
        (AGORA - timedelta(minutes=5), False, "hoje, 14:55"),
    ],
)
def test_quando_texto(quando: datetime, com_hora: bool, esperado: str) -> None:
    assert quando_texto(quando, AGORA, com_hora=com_hora, fuso=SAO_PAULO) == esperado


def test_meia_noite_de_sao_paulo_e_nao_a_de_utc() -> None:
    """02:00 UTC ainda é ontem, 23:00, em São Paulo."""
    agora = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    quando = datetime(2026, 9, 25, 2, 0, tzinfo=UTC)
    assert quando_texto(quando, agora, fuso=SAO_PAULO) == "ontem, 23:00"


def test_fuso_padrao_e_o_dela() -> None:
    fuso = fuso_dela({})
    assert datetime(2026, 9, 25, 12, tzinfo=UTC).astimezone(fuso).hour == 9


def test_fuso_desconhecido_cai_para_menos_tres() -> None:
    fuso = fuso_dela({"MISE_FUSO": "Marte/Olimpo"})
    assert fuso.utcoffset(None) == timedelta(hours=-3)


def test_quando_texto_sem_fuso_usa_o_do_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISE_FUSO", "UTC")
    assert quando_texto(AGORA, AGORA) == "hoje, 18:00"
