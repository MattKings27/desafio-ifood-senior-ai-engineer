"""O dossiê: o que sobrevive entre sessões."""

from __future__ import annotations

import contextlib
import sqlite3
import threading
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mise.dinheiro import Dinheiro
from mise.dossie import ORCAMENTO_INICIAL, Canal, Decisao, Dossie, EstadoOrcamento
from mise.erros import ErroDeUso, OrcamentoExcedido
from mise.perfil import PerfilCozinha, Posse

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def dossie(tmp_path: Path) -> Dossie:
    with Dossie(tmp_path / "estado" / "dossie.db") as d:
        yield d


def test_cria_o_diretorio_se_faltar(tmp_path: Path) -> None:
    caminho = tmp_path / "fundo" / "do" / "poco" / "d.db"
    with Dossie(caminho):
        assert caminho.exists()


def test_orcamento_inicial_e_o_do_enunciado() -> None:
    assert ORCAMENTO_INICIAL == Dinheiro.de("80.00")


# --------------------------------------------------------------------------- #
# Perfil
# --------------------------------------------------------------------------- #


def test_perfil_vazio_quando_nao_ha_nada(dossie: Dossie) -> None:
    assert dossie.carregar_perfil().tem_equipamento("forno") is Posse.DESCONHECIDO


def test_perfil_sobrevive_ao_fechamento(tmp_path: Path) -> None:
    caminho = tmp_path / "d.db"
    with Dossie(caminho) as primeiro:
        primeiro.salvar_perfil(
            PerfilCozinha.inicial()
            .com_equipamento("forno", Posse.TEM)
            .com_restricao("bocas_fogao", 4)
        )
    with Dossie(caminho) as segundo:
        perfil = segundo.carregar_perfil()
        assert perfil.tem_equipamento("forno") is Posse.TEM
        assert perfil.restricoes.bocas_fogao == 4


def test_salvar_perfil_sobrescreve(dossie: Dossie) -> None:
    dossie.salvar_perfil(PerfilCozinha.inicial().com_equipamento("forno", Posse.TEM))
    dossie.salvar_perfil(PerfilCozinha.inicial().com_equipamento("forno", Posse.NAO_TEM))
    assert dossie.carregar_perfil().tem_equipamento("forno") is Posse.NAO_TEM


# --------------------------------------------------------------------------- #
# Decisões: append-only e idempotentes
# --------------------------------------------------------------------------- #


def test_registra_decisao(dossie: Dossie) -> None:
    registro = dossie.registrar_decisao("Parmegiana", Decisao.ACEITO, "gostou")
    assert registro.prato == "Parmegiana"
    assert registro.decisao is Decisao.ACEITO
    assert "Parmegiana" in str(registro)
    assert "aceito" in str(registro)


def test_decisao_repetida_nao_duplica(dossie: Dossie) -> None:
    """Retry de rede não pode virar dois registros."""
    dossie.registrar_decisao("Parmegiana", Decisao.ACEITO, "gostou")
    dossie.registrar_decisao("Parmegiana", Decisao.ACEITO, "outro motivo")
    assert len(dossie.historico("Parmegiana")) == 1
    assert dossie.historico("Parmegiana")[0].motivo == "gostou", "o primeiro registro prevalece"


def test_mudar_de_ideia_nao_apaga_o_passado(dossie: Dossie) -> None:
    """Aceitar e depois recusar são dois eventos: a trilha é o produto."""
    dossie.registrar_decisao("Lasanha", Decisao.ACEITO)
    dossie.registrar_decisao("Lasanha", Decisao.RECUSADO, "deu trabalho demais")

    historico = dossie.historico("Lasanha")
    assert len(historico) == 2
    assert [r.decisao for r in historico] == [Decisao.ACEITO, Decisao.RECUSADO]
    assert dossie.decisao_atual("Lasanha") is Decisao.RECUSADO


def test_chave_explicita_permite_varios_registros(dossie: Dossie) -> None:
    dossie.registrar_decisao("X", Decisao.ADIADO, chave="x-1")
    dossie.registrar_decisao("X", Decisao.ADIADO, chave="x-2")
    assert len(dossie.historico("X")) == 2


def test_decisao_atual_de_prato_desconhecido(dossie: Dossie) -> None:
    assert dossie.decisao_atual("Nunca visto") is None


def test_cardapio_so_tem_aceitos_vigentes(dossie: Dossie) -> None:
    dossie.registrar_decisao("Parmegiana", Decisao.ACEITO)
    dossie.registrar_decisao("Escondidinho", Decisao.ACEITO)
    dossie.registrar_decisao("Lasanha", Decisao.ACEITO)
    dossie.registrar_decisao("Lasanha", Decisao.RECUSADO, "mudou de ideia")
    dossie.registrar_decisao("Pudim", Decisao.ADIADO)

    assert dossie.cardapio == ("Escondidinho", "Parmegiana")


def test_detalhes_sobrevivem(dossie: Dossie) -> None:
    dossie.registrar_decisao(
        "X", Decisao.ACEITO, detalhes={"cmv": "R$ 8,68", "preco_escolhido": "R$ 24,80"}
    )
    assert dossie.historico("X")[0].detalhes["preco_escolhido"] == "R$ 24,80"


def test_historico_completo_em_ordem(dossie: Dossie) -> None:
    for nome in ("A", "B", "C"):
        dossie.registrar_decisao(nome, Decisao.ACEITO)
    assert [r.prato for r in dossie.historico()] == ["A", "B", "C"]


def test_str_de_registro_sem_motivo(dossie: Dossie) -> None:
    assert "—" not in str(dossie.registrar_decisao("X", Decisao.ACEITO))


# --------------------------------------------------------------------------- #
# Orçamento
# --------------------------------------------------------------------------- #


def test_orcamento_comeca_intacto(dossie: Dossie) -> None:
    estado = dossie.orcamento()
    assert estado.restante == Dinheiro.de("80.00")
    assert estado.fracao_usada == 0.0


def test_registrar_gasto_desconta(dossie: Dossie) -> None:
    estado = dossie.registrar_gasto("linguiça", Dinheiro.de("22.00"))
    assert estado.gasto == Dinheiro.de("22.00")
    assert estado.restante == Dinheiro.de("58.00")
    assert estado.fracao_usada == pytest.approx(0.275)


def test_gasto_repetido_nao_debita_duas_vezes(dossie: Dossie) -> None:
    dossie.registrar_gasto("embalagem", Dinheiro.de("55.00"))
    dossie.registrar_gasto("embalagem", Dinheiro.de("55.00"))
    assert dossie.orcamento().gasto == Dinheiro.de("55.00")


def test_estouro_do_orcamento_e_recusado(dossie: Dossie) -> None:
    dossie.registrar_gasto("embalagem", Dinheiro.de("55.00"))
    with pytest.raises(OrcamentoExcedido) as exc:
        dossie.registrar_gasto("trufa", Dinheiro.de("50.00"))
    assert exc.value.faltam == pytest.approx(25.0)
    assert dossie.orcamento().gasto == Dinheiro.de("55.00"), "nada foi debitado"


def test_gasto_exato_do_restante_passa(dossie: Dossie) -> None:
    dossie.registrar_gasto("a", Dinheiro.de("80.00"))
    assert dossie.orcamento().restante == Dinheiro.zero()


def test_gasto_negativo_e_recusado(dossie: Dossie) -> None:
    with pytest.raises(ErroDeUso, match="negativo"):
        dossie.registrar_gasto("estorno", Dinheiro.de("-10.00"))


def test_lista_de_gastos(dossie: Dossie) -> None:
    dossie.registrar_gasto("linguiça", Dinheiro.de("22.00"))
    dossie.registrar_gasto("cenoura", Dinheiro.de("4.50"))
    gastos = list(dossie.gastos())
    assert [g[0] for g in gastos] == ["linguiça", "cenoura"]
    assert gastos[1][1] == Dinheiro.de("4.50")


def test_orcamento_customizado(tmp_path: Path) -> None:
    with Dossie(tmp_path / "d.db", orcamento=Dinheiro.de("200.00")) as d:
        assert d.orcamento().restante == Dinheiro.de("200.00")


def test_estado_orcamento_com_inicial_zero() -> None:
    estado = EstadoOrcamento(inicial=Dinheiro.zero(), gasto=Dinheiro.zero())
    assert estado.fracao_usada == 0.0
    assert estado.cabe(Dinheiro.zero())


def test_str_do_estado(dossie: Dossie) -> None:
    assert "restam" in str(dossie.orcamento())


# --------------------------------------------------------------------------- #
# Panorama
# --------------------------------------------------------------------------- #


def test_resumo_junta_tudo(dossie: Dossie) -> None:
    dossie.salvar_perfil(PerfilCozinha.inicial().com_equipamento("forno", Posse.TEM))
    dossie.registrar_decisao("Parmegiana", Decisao.ACEITO)
    dossie.registrar_gasto("embalagem", Dinheiro.de("55.00"))

    resumo = dossie.resumo()
    assert "1 respondido por ela" in resumo
    assert "1 prato no cardápio" in resumo
    assert "R$ 55,00" in resumo


def test_gosto_de_prato_sem_nome_e_recusado(tmp_path) -> None:
    """Prato sem nome não tem onde ser guardado nem como ser consultado depois."""
    from mise.dossie import Dossie
    from mise.erros import ErroDeUso
    from mise.perfil import Gosto

    with Dossie(tmp_path / "d.db") as d, pytest.raises(ErroDeUso, match="sem nome"):
        d.registrar_gosto("   ", Gosto.GOSTA)


def test_gosto_casa_pelo_nome_sem_caixa_nem_acento(tmp_path) -> None:
    from mise.perfil import Gosto

    with Dossie(tmp_path / "d.db") as d:
        d.registrar_gosto("strogonoff de frango", Gosto.GOSTA)
        opiniao = d.gosto_por("  Strogonoff de Frângo ")
        assert opiniao is not None
        assert opiniao.gosto is Gosto.GOSTA
        assert d.gosto_por("Strogonoff de carne") is None


# --------------------------------------------------------------------------- #
# Esquema de cada módulo, transação, relógio e canal
# --------------------------------------------------------------------------- #

DDL_NOTAS = """
CREATE TABLE IF NOT EXISTS notas_de_teste (
    id    INTEGER PRIMARY KEY,
    texto TEXT NOT NULL
);
"""

CANAL_NAS_NOTAS = ("notas_de_teste", "canal", "TEXT NOT NULL DEFAULT 'tela'")


def _textos(dossie: Dossie) -> list[str]:
    with dossie.cursor() as cur:
        return [linha["texto"] for linha in cur.execute("SELECT texto FROM notas_de_teste")]


def test_modulo_cria_a_propria_tabela_e_repetir_nao_estraga(dossie: Dossie) -> None:
    dossie.garantir_esquema(DDL_NOTAS)
    with dossie.cursor() as cur:
        cur.execute("INSERT INTO notas_de_teste (texto) VALUES ('a')")
    dossie.garantir_esquema(DDL_NOTAS, [CANAL_NAS_NOTAS])
    dossie.garantir_esquema(DDL_NOTAS, [CANAL_NAS_NOTAS])
    with dossie.cursor() as cur:
        linha = cur.execute("SELECT texto, canal FROM notas_de_teste").fetchone()
    assert tuple(linha) == ("a", "tela"), "a coluna nova chegou sem apagar a linha"


@pytest.mark.parametrize(
    "coluna", [("x; DROP TABLE gastos", "c", "TEXT"), ("gastos", "c d", "TEXT")]
)
def test_nome_de_tabela_ou_coluna_estranho_e_recusado(
    dossie: Dossie, coluna: tuple[str, str, str]
) -> None:
    with pytest.raises(ErroDeUso, match="inválido"):
        dossie.garantir_esquema("", [coluna])


def test_esquema_nao_roda_dentro_de_transacao(dossie: Dossie) -> None:
    """O `executescript` fecharia a transação em aberto sem ninguém perceber."""
    with dossie.transacao(), pytest.raises(ErroDeUso, match="transação"):
        dossie.garantir_esquema(DDL_NOTAS)


def test_banco_antigo_ganha_as_colunas_sem_perder_o_que_ela_fez(tmp_path: Path) -> None:
    caminho = tmp_path / "antigo.db"
    with closing(sqlite3.connect(caminho)) as antigo:
        antigo.executescript(
            "CREATE TABLE decisoes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "chave TEXT NOT NULL UNIQUE, prato TEXT NOT NULL, decisao TEXT NOT NULL, "
            "motivo TEXT NOT NULL DEFAULT '', detalhes TEXT NOT NULL DEFAULT '{}', "
            "registrado TEXT NOT NULL);"
            "INSERT INTO decisoes (chave, prato, decisao, registrado) "
            "VALUES ('Lasanha:aceito', 'Lasanha', 'aceito', '2026-09-01T12:00:00+00:00');"
            "CREATE TABLE gastos (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "chave TEXT NOT NULL UNIQUE, descricao TEXT NOT NULL, centavos INTEGER NOT NULL, "
            "registrado TEXT NOT NULL);"
            "INSERT INTO gastos (chave, descricao, centavos, registrado) "
            "VALUES ('embalagem:500', 'embalagem', 500, '2026-09-01T12:00:00+00:00');"
        )
    with Dossie(caminho) as d:
        (registro,) = d.historico("Lasanha")
        assert (registro.canal, registro.id) == ("conversa", 1)
        assert d.cardapio == ("Lasanha",)
        assert d.orcamento().gasto == Dinheiro.de("5.00")
        with d.cursor() as cur:
            assert cur.execute("SELECT canal FROM gastos").fetchone()["canal"] == "conversa"


def test_transacao_grava_tudo_ou_nada(dossie: Dossie) -> None:
    dossie.garantir_esquema(DDL_NOTAS)
    with pytest.raises(RuntimeError), dossie.transacao() as cur:
        cur.execute("INSERT INTO notas_de_teste (texto) VALUES ('pela metade')")
        raise RuntimeError("caiu no meio")
    with dossie.transacao() as cur:
        cur.execute("INSERT INTO notas_de_teste (texto) VALUES ('inteira')")
    assert _textos(dossie) == ["inteira"]


def test_transacao_de_dentro_desfaz_so_o_que_ela_fez(dossie: Dossie) -> None:
    dossie.garantir_esquema(DDL_NOTAS)
    with dossie.transacao() as fora:
        fora.execute("INSERT INTO notas_de_teste (texto) VALUES ('fora')")
        with contextlib.suppress(RuntimeError), dossie.transacao() as dentro:
            dentro.execute("INSERT INTO notas_de_teste (texto) VALUES ('dentro')")
            raise RuntimeError
        with dossie.transacao() as de_novo:
            de_novo.execute("INSERT INTO notas_de_teste (texto) VALUES ('de novo')")
    assert _textos(dossie) == ["fora", "de novo"]


def test_transacao_toma_a_escrita_do_arquivo_ja_no_comeco(tmp_path: Path) -> None:
    """Outra porta não escreve no meio de uma sequência de conferir e gravar."""
    caminho = tmp_path / "d.db"
    with (
        Dossie(caminho) as dossie,
        dossie.transacao(),
        closing(sqlite3.connect(caminho, timeout=0, isolation_level=None)) as outra,
        pytest.raises(sqlite3.OperationalError, match="locked"),
    ):
        outra.execute("BEGIN IMMEDIATE")


def test_duas_portas_nao_gastam_o_mesmo_saldo(tmp_path: Path) -> None:
    """A tela e a conversa gravam no mesmo arquivo, cada uma com a sua conexão.

    A primeira confere o saldo e demora; a segunda tenta gastar nesse meio
    tempo. Com a conferência e a gravação na mesma transação, a segunda só
    confere depois que a primeira gravou, e é recusada. Antes, as duas viam
    R$ 80,00 livres e gastavam R$ 100,00.
    """
    caminho = tmp_path / "d.db"
    tela, conversa = Dossie(caminho), Dossie(caminho)
    conferiu = threading.Event()
    original = tela.orcamento

    def orcamento_demorado() -> EstadoOrcamento:
        estado = original()
        if not conferiu.is_set():
            conferiu.set()
            time.sleep(0.3)
        return estado

    tela.orcamento = orcamento_demorado  # type: ignore[method-assign]
    resultado: dict[str, object] = {}

    def gastar(nome: str, dossie: Dossie) -> None:
        try:
            resultado[nome] = dossie.registrar_gasto(nome, Dinheiro.de("50.00"))
        except OrcamentoExcedido as erro:
            resultado[nome] = erro

    primeira = threading.Thread(target=gastar, args=("tela", tela))
    try:
        primeira.start()
        assert conferiu.wait(5)
        gastar("conversa", conversa)
        primeira.join(5)
        assert isinstance(resultado["tela"], EstadoOrcamento)
        assert isinstance(resultado["conversa"], OrcamentoExcedido)
        assert conversa.orcamento().gasto == Dinheiro.de("50.00")
    finally:
        tela.fechar()
        conversa.fechar()


def test_relogio_do_dossie_e_injetavel(tmp_path: Path) -> None:
    momento = datetime(2026, 9, 25, 15, 2, tzinfo=UTC)
    with Dossie(tmp_path / "d.db", relogio=lambda: momento) as d:
        assert d.registrar_decisao("Bolo", Decisao.ADIADO).registrado == momento
        assert d.agora() == momento
        d.registrar_gasto("embalagem", Dinheiro.de("5.00"))
        assert [quando for *_, quando in d.gastos()] == [momento]


def test_decisao_guarda_por_onde_chegou(dossie: Dossie) -> None:
    assert dossie.registrar_decisao("Bolo", Decisao.ADIADO).canal == "conversa"
    registro = dossie.registrar_decisao("Pudim", Decisao.ACEITO, canal=Canal.TELA)
    assert registro.canal == "tela"
    assert registro.id is not None
    assert dossie.historico("Pudim")[0].canal == "tela"


def test_canal_desconhecido_e_recusado_sem_gravar(dossie: Dossie) -> None:
    with pytest.raises(ErroDeUso, match="canal desconhecido"):
        dossie.registrar_decisao("Bolo", Decisao.ADIADO, canal="planilha")
    with pytest.raises(ErroDeUso, match="canal desconhecido"):
        dossie.registrar_gasto("x", Dinheiro.de("1.00"), canal="pombo")
    assert dossie.historico() == ()
    assert dossie.orcamento().gasto == Dinheiro.zero()


def test_compra_grava_ingrediente_e_canal_na_mesma_linha(dossie: Dossie) -> None:
    dossie.registrar_compra("milho verde", Decimal(1), "lata", Dinheiro.de("6.00"), canal="tela")
    with dossie.cursor() as cur:
        linha = cur.execute("SELECT ingrediente, quantidade, unidade, canal FROM gastos").fetchone()
    assert tuple(linha) == ("milho verde", "1", "lata", "tela")


def test_compra_que_estoura_nao_grava_nada(dossie: Dossie) -> None:
    dossie.registrar_gasto("embalagem", Dinheiro.de("75.00"))
    with pytest.raises(OrcamentoExcedido):
        dossie.registrar_compra("milho verde", Decimal(1), "lata", Dinheiro.de("6.00"))
    assert dossie.compras() == {}
    assert dossie.orcamento().gasto == Dinheiro.de("75.00")


def test_compra_negativa_e_recusada(dossie: Dossie) -> None:
    with pytest.raises(ErroDeUso, match="negativo"):
        dossie.registrar_compra("milho verde", Decimal(1), "lata", Dinheiro.de("-6.00"))


def test_transacao_que_o_sqlite_ja_desfez_nao_quebra_na_saida(dossie: Dossie) -> None:
    """Um erro grave faz o SQLite desfazer sozinho; a saída não tenta desfazer de novo."""
    with pytest.raises(RuntimeError), dossie.transacao() as cur:
        cur.execute("ROLLBACK")
        raise RuntimeError("erro de disco")
    dossie.registrar_gasto("depois", Dinheiro.de("1.00"))
    assert dossie.orcamento().gasto == Dinheiro.de("1.00"), "a conexão continua usável"


# --------------------------------------------------------------------------- #
# Decisões: repetição é só a do último evento do prato
# --------------------------------------------------------------------------- #

A_12 = {"preco": "R$ 12,00"}


def test_aceitar_recusar_e_aceitar_de_novo_volta_ao_cardapio(dossie: Dossie) -> None:
    """Antes, o terceiro evento batia na chave do primeiro e sumia; o prato ficava fora."""
    dossie.registrar_decisao("Arroz com frango", Decisao.ACEITO, detalhes=A_12)
    dossie.registrar_decisao("Arroz com frango", Decisao.RECUSADO, "caro demais")
    dossie.registrar_decisao("Arroz com frango", Decisao.ACEITO, "pensou melhor", detalhes=A_12)

    historico = dossie.historico("Arroz com frango")
    assert [r.decisao for r in historico] == [Decisao.ACEITO, Decisao.RECUSADO, Decisao.ACEITO]
    assert dossie.cardapio == ("Arroz com frango",)


def test_repetir_o_ultimo_evento_nao_grava_de_novo(dossie: Dossie) -> None:
    primeiro = dossie.registrar_decisao("Bolo", Decisao.ACEITO, "gostou", detalhes=A_12)
    repetido = dossie.registrar_decisao("Bolo", Decisao.ACEITO, "retry", detalhes=A_12)
    assert repetido == primeiro
    assert len(dossie.historico("Bolo")) == 1


def test_mudar_o_preco_e_uma_decisao_nova(dossie: Dossie) -> None:
    dossie.registrar_decisao("Bolo", Decisao.ACEITO, detalhes=A_12)
    dossie.registrar_decisao("Bolo", Decisao.ACEITO, detalhes={"preco": "R$ 14,00"})
    assert [r.detalhes["preco"] for r in dossie.historico("Bolo")] == ["R$ 12,00", "R$ 14,00"]


def test_o_ultimo_evento_e_o_do_prato_e_nao_o_da_trilha(dossie: Dossie) -> None:
    dossie.registrar_decisao("Bolo", Decisao.ACEITO, detalhes=A_12)
    dossie.registrar_decisao("Pudim", Decisao.RECUSADO)
    dossie.registrar_decisao("Bolo", Decisao.ACEITO, detalhes=A_12)
    assert len(dossie.historico("Bolo")) == 1


def test_mesma_chave_de_quem_chama_devolve_o_mesmo_registro(dossie: Dossie) -> None:
    """O reenvio atrasado de um clique não aceita de novo depois de uma recusa."""
    aceite = dossie.registrar_decisao("Bolo", Decisao.ACEITO, detalhes=A_12, chave="clique-1")
    dossie.registrar_decisao("Bolo", Decisao.RECUSADO, chave="clique-2")
    reenvio = dossie.registrar_decisao("Bolo", Decisao.ACEITO, detalhes=A_12, chave="clique-1")
    assert reenvio == aceite
    assert dossie.decisao_atual("Bolo") is Decisao.RECUSADO


def test_mesma_chave_para_outra_decisao_e_erro(dossie: Dossie) -> None:
    dossie.registrar_decisao("Bolo", Decisao.ACEITO, detalhes=A_12, chave="clique-1")
    with pytest.raises(ErroDeUso, match="outra decisão"):
        dossie.registrar_decisao("Bolo", Decisao.RECUSADO, chave="clique-1")
    assert len(dossie.historico("Bolo")) == 1


def test_desfazer_aponta_a_decisao_desfeita(dossie: Dossie) -> None:
    aceite = dossie.registrar_decisao("Bolo", Decisao.ACEITO, detalhes=A_12)
    recusa = dossie.registrar_decisao("Bolo", Decisao.RECUSADO)
    assert recusa.id is not None
    volta = dossie.registrar_decisao("Bolo", Decisao.ACEITO, detalhes=A_12, desfaz=recusa.id)
    assert volta.desfaz == recusa.id
    assert aceite.desfaz is None
    assert dossie.historico("Bolo")[-1].desfaz == recusa.id
    assert dossie.cardapio == ("Bolo",)


@pytest.mark.parametrize("prato_do_alvo", ["Pudim", None])
def test_desfazer_o_que_nao_existe_ou_e_de_outro_prato_e_recusado(
    dossie: Dossie, prato_do_alvo: str | None
) -> None:
    alvo = dossie.registrar_decisao(prato_do_alvo, Decisao.RECUSADO).id if prato_do_alvo else 999
    with pytest.raises(ErroDeUso, match="desfazer"):
        dossie.registrar_decisao("Bolo", Decisao.ACEITO, detalhes=A_12, desfaz=alvo)
    assert dossie.historico("Bolo") == ()


def test_banco_com_chaves_do_formato_antigo_continua_aceitando(tmp_path: Path) -> None:
    """As chaves `prato:decisao:preco` que ficaram gravadas não travam decisões novas."""
    caminho = tmp_path / "d.db"
    with Dossie(caminho) as d:
        d.registrar_decisao("Bolo", Decisao.ACEITO, detalhes=A_12, chave="Bolo:aceito:R$ 12,00")
        d.registrar_decisao("Bolo", Decisao.RECUSADO, chave="Bolo:recusado:")
    with Dossie(caminho) as d:
        d.registrar_decisao("Bolo", Decisao.ACEITO, detalhes=A_12)
        assert d.cardapio == ("Bolo",)
        assert len(d.historico("Bolo")) == 3


# --------------------------------------------------------------------------- #
# Compras: repetição pela chave, ou a mesma compra em poucos minutos
# --------------------------------------------------------------------------- #


class RelogioFalso:
    """O tempo do dossiê anda quando o teste manda."""

    def __init__(self) -> None:
        self.momento = datetime(2026, 9, 25, 10, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.momento

    def andar(self, **quanto: float) -> None:
        self.momento += timedelta(**quanto)


@pytest.fixture
def relogio() -> RelogioFalso:
    return RelogioFalso()


@pytest.fixture
def no_relogio(tmp_path: Path, relogio: RelogioFalso) -> Iterator[Dossie]:
    with Dossie(tmp_path / "d.db", relogio=relogio) as d:
        yield d


MILHO = ("milho verde", Decimal(1), "lata", Dinheiro.de("6.00"))


def test_a_mesma_compra_repetida_em_minutos_conta_uma_vez(
    no_relogio: Dossie, relogio: RelogioFalso
) -> None:
    """O agente chamou duas vezes, ou a rede repetiu: é uma lata só."""
    no_relogio.registrar_compra(*MILHO)
    relogio.andar(minutes=9, seconds=59)
    no_relogio.registrar_compra(*MILHO)
    assert no_relogio.orcamento().gasto == Dinheiro.de("6.00")


def test_a_segunda_compra_igual_depois_da_janela_conta(
    no_relogio: Dossie, relogio: RelogioFalso
) -> None:
    """A chave vinha do conteúdo, e a segunda lata de verdade era descartada para sempre."""
    no_relogio.registrar_compra(*MILHO)
    relogio.andar(minutes=10, seconds=1)
    no_relogio.registrar_compra(*MILHO)
    assert no_relogio.orcamento().gasto == Dinheiro.de("12.00")
    assert no_relogio.compras()["milho verde"].valor == Dinheiro.de("12.00")


def test_compra_diferente_nao_e_repeticao(no_relogio: Dossie) -> None:
    no_relogio.registrar_compra(*MILHO)
    no_relogio.registrar_compra("milho verde", Decimal(2), "lata", Dinheiro.de("12.00"))
    no_relogio.registrar_compra("milho verde", Decimal(1), "lata", Dinheiro.de("6.50"))
    no_relogio.registrar_compra("ervilha", Decimal(1), "lata", Dinheiro.de("6.00"))
    assert no_relogio.orcamento().gasto == Dinheiro.de("30.50")


def test_a_grafia_do_nome_e_da_quantidade_nao_faz_outra_compra(no_relogio: Dossie) -> None:
    no_relogio.registrar_compra(*MILHO)
    no_relogio.registrar_compra("Milho Verde", Decimal("1.0"), "lata", Dinheiro.de("6.00"))
    assert no_relogio.orcamento().gasto == Dinheiro.de("6.00")


def test_gasto_sem_ingrediente_nao_conta_como_a_mesma_compra(no_relogio: Dossie) -> None:
    no_relogio.registrar_gasto("milho verde: 1 lata", Dinheiro.de("6.00"))
    no_relogio.registrar_compra(*MILHO)
    assert no_relogio.orcamento().gasto == Dinheiro.de("12.00")


def test_com_chave_duas_compras_iguais_sao_duas(no_relogio: Dossie) -> None:
    """Dois cliques dela na tela, cada um com a sua chave: duas latas, no mesmo minuto."""
    no_relogio.registrar_compra(*MILHO, chave="clique-1")
    no_relogio.registrar_compra(*MILHO, chave="clique-2")
    assert no_relogio.orcamento().gasto == Dinheiro.de("12.00")


def test_a_mesma_chave_nao_desconta_duas_vezes(no_relogio: Dossie, relogio: RelogioFalso) -> None:
    no_relogio.registrar_compra(*MILHO, chave="clique-1")
    relogio.andar(days=1)
    no_relogio.registrar_compra(*MILHO, chave="clique-1")
    assert no_relogio.orcamento().gasto == Dinheiro.de("6.00")
    assert no_relogio.tem_gasto("clique-1")
    assert not no_relogio.tem_gasto("clique-2")


@pytest.mark.parametrize(
    "outra",
    [
        ("ervilha", Decimal(1), "lata", Dinheiro.de("6.00")),
        ("milho verde", Decimal(1), "lata", Dinheiro.de("7.00")),
    ],
)
def test_a_mesma_chave_para_outra_compra_e_erro(
    no_relogio: Dossie, outra: tuple[str, Decimal, str, Dinheiro]
) -> None:
    no_relogio.registrar_compra(*MILHO, chave="clique-1")
    with pytest.raises(ErroDeUso, match="outra compra"):
        no_relogio.registrar_compra(*outra, chave="clique-1")
    assert no_relogio.orcamento().gasto == Dinheiro.de("6.00")


def test_a_chave_de_um_gasto_sem_ingrediente_nao_vira_compra(no_relogio: Dossie) -> None:
    no_relogio.registrar_gasto("embalagem", Dinheiro.de("6.00"), chave="clique-1")
    with pytest.raises(ErroDeUso, match="outra compra"):
        no_relogio.registrar_compra(*MILHO, chave="clique-1")
