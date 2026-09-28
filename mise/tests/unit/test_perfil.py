"""A lógica de três valores: o que permite ao agente perguntar em vez de chutar."""

from __future__ import annotations

import pytest

from mise.erros import VocabularioDesconhecido
from mise.perfil import PERGUNTAS_OPERACIONAIS, PerfilCozinha, Posse, RestricoesOperacionais
from mise.taxonomia import EQUIPAMENTOS, TECNICAS


def test_tres_estados_distintos() -> None:
    assert Posse.TEM.resolvido
    assert Posse.NAO_TEM.resolvido
    assert not Posse.DESCONHECIDO.resolvido
    assert Posse.NAO_TEM.bloqueia
    assert not Posse.TEM.bloqueia
    assert not Posse.DESCONHECIDO.bloqueia, "não saber não é o mesmo que não ter"


def test_perfil_inicial_pressupoe_o_obvio() -> None:
    p = PerfilCozinha.inicial()
    assert p.tem_equipamento("faca") is Posse.TEM
    assert p.tem_equipamento("fogao") is Posse.TEM
    assert p.tem_equipamento("forno") is Posse.DESCONHECIDO
    assert p.domina_tecnica("refogar") is Posse.TEM
    assert p.domina_tecnica("bechamel") is Posse.DESCONHECIDO


def test_todo_equipamento_e_tecnica_tem_estado_inicial() -> None:
    p = PerfilCozinha.inicial()
    assert set(p.equipamentos) == {e.id for e in EQUIPAMENTOS}
    assert set(p.tecnicas) == {t.id for t in TECNICAS}


def test_perfil_e_imutavel_nas_atualizacoes() -> None:
    antes = PerfilCozinha.inicial()
    depois = antes.com_equipamento("forno", Posse.TEM)
    assert antes.tem_equipamento("forno") is Posse.DESCONHECIDO
    assert depois.tem_equipamento("forno") is Posse.TEM


def test_atualizacao_em_lote() -> None:
    p = PerfilCozinha.inicial().com_equipamentos(
        [("forno", Posse.TEM), ("batedeira", Posse.NAO_TEM)]
    )
    assert p.tem_equipamento("forno") is Posse.TEM
    assert p.tem_equipamento("batedeira") is Posse.NAO_TEM

    p = p.com_tecnicas([("bechamel", Posse.TEM), ("temperagem", Posse.NAO_TEM)])
    assert p.domina_tecnica("bechamel") is Posse.TEM
    assert p.domina_tecnica("temperagem") is Posse.NAO_TEM


@pytest.mark.parametrize("metodo", ["com_equipamento", "tem_equipamento"])
def test_vocabulario_controlado_e_validado_em_equipamentos(metodo: str) -> None:
    p = PerfilCozinha.inicial()
    args = ("fritadeira_industrial", Posse.TEM) if metodo == "com_equipamento" else ("x",)
    with pytest.raises(VocabularioDesconhecido, match="vocabulário controlado"):
        getattr(p, metodo)(*args)


def test_vocabulario_controlado_e_validado_em_tecnicas() -> None:
    p = PerfilCozinha.inicial()
    with pytest.raises(VocabularioDesconhecido, match="vocabulário controlado"):
        p.com_tecnica("gastronomia_molecular", Posse.TEM)
    with pytest.raises(VocabularioDesconhecido):
        p.domina_tecnica("inexistente")


def test_lote_tambem_valida_vocabulario() -> None:
    p = PerfilCozinha.inicial()
    with pytest.raises(VocabularioDesconhecido):
        p.com_equipamentos([("forno", Posse.TEM), ("inexistente", Posse.TEM)])
    with pytest.raises(VocabularioDesconhecido):
        p.com_tecnicas([("bechamel", Posse.TEM), ("inexistente", Posse.TEM)])


# --------------------------------------------------------------------------- #
# Substitutos
# --------------------------------------------------------------------------- #


def test_substituto_satisfaz_a_exigencia() -> None:
    p = PerfilCozinha.inicial().com_equipamento("air_fryer", Posse.TEM)
    posse, usado = p.tem_equipamento_ou_substituto("forno")
    assert posse is Posse.TEM
    assert usado == "air_fryer"


def test_equipamento_direto_dispensa_substituto() -> None:
    p = PerfilCozinha.inicial().com_equipamento("forno", Posse.TEM)
    posse, usado = p.tem_equipamento_ou_substituto("forno")
    assert posse is Posse.TEM
    assert usado is None


def test_negado_com_substituto_em_aberto_continua_em_aberto() -> None:
    """Não se bloqueia enquanto ainda há alternativa por perguntar."""
    p = PerfilCozinha.inicial().com_equipamento("forno", Posse.NAO_TEM)
    posse, _ = p.tem_equipamento_ou_substituto("forno")
    assert posse is Posse.DESCONHECIDO


def test_negado_com_todos_substitutos_negados_bloqueia() -> None:
    p = (
        PerfilCozinha.inicial()
        .com_equipamento("forno", Posse.NAO_TEM)
        .com_equipamento("air_fryer", Posse.NAO_TEM)
        .com_equipamento("forno_eletrico", Posse.NAO_TEM)
    )
    posse, _ = p.tem_equipamento_ou_substituto("forno")
    assert posse is Posse.NAO_TEM


def test_sem_substitutos_cadastrados() -> None:
    p = PerfilCozinha.inicial().com_equipamento("microondas", Posse.NAO_TEM)
    posse, _ = p.tem_equipamento_ou_substituto("microondas")
    assert posse is Posse.NAO_TEM


# --------------------------------------------------------------------------- #
# Restrições operacionais
# --------------------------------------------------------------------------- #


def test_restricoes_comecam_em_aberto() -> None:
    """As quatro do §2.2 mais as duas que saem das mesmas perguntas.

    Este conjunto é fixado de propósito. Antes, `tem_gas_sobrando` e
    `espaco_geladeira_litros` existiam como campo e nunca entravam em
    `pendencias()`: eram decorativos, e ninguém percebia porque nenhum teste
    dizia quais restrições contam.
    """
    r = RestricoesOperacionais()
    assert not r.completo
    assert set(r.pendencias()) == {
        "bocas_fogao",
        "tempo_max_por_fornada_min",
        "porcoes_por_fornada",
        "tem_gas_sobrando",
        "espaco_geladeira_litros",
        "energia_aparelhos_simultaneos",
    }


def test_as_quatro_do_enunciado_estao_no_levantamento() -> None:
    """Energia, gás, espaço na geladeira e tempo por cozinhada, nomeadas no §2.2."""
    pendentes = set(RestricoesOperacionais().pendencias())
    assert "energia_aparelhos_simultaneos" in pendentes
    assert "tem_gas_sobrando" in pendentes
    assert "espaco_geladeira_litros" in pendentes
    assert "tempo_max_por_fornada_min" in pendentes


def test_restricoes_completas() -> None:
    r = RestricoesOperacionais(
        bocas_fogao=4,
        tempo_max_por_fornada_min=120,
        porcoes_por_fornada=20,
        tem_gas_sobrando=True,
        espaco_geladeira_litros=20,
        energia_aparelhos_simultaneos=2,
    )
    assert r.completo
    assert not r.pendencias()


def test_gas_declarado_como_ausente_conta_como_respondido() -> None:
    """ "Não tenho reserva" é uma resposta, não uma pendência."""
    r = RestricoesOperacionais(tem_gas_sobrando=False)
    assert "tem_gas_sobrando" not in r.pendencias()


def test_geladeira_sem_espaco_conta_como_respondido() -> None:
    r = RestricoesOperacionais(espaco_geladeira_litros=0)
    assert "espaco_geladeira_litros" not in r.pendencias()


def test_atualizar_restricao() -> None:
    p = PerfilCozinha.inicial().com_restricao("bocas_fogao", 4)
    assert p.restricoes.bocas_fogao == 4


def test_restricao_desconhecida_e_rejeitada() -> None:
    with pytest.raises(VocabularioDesconhecido, match="vocabulário controlado"):
        PerfilCozinha.inicial().com_restricao("tem_fogao_industrial", True)


def test_toda_restricao_tem_pergunta_escrita() -> None:
    for campo in RestricoesOperacionais().pendencias():
        assert campo in PERGUNTAS_OPERACIONAIS
        assert "?" in PERGUNTAS_OPERACIONAIS[campo], "toda pendência precisa virar pergunta"


# --------------------------------------------------------------------------- #
# Panorama
# --------------------------------------------------------------------------- #


def test_conjuntos_de_panorama() -> None:
    p = (
        PerfilCozinha.inicial()
        .com_equipamento("forno", Posse.TEM)
        .com_equipamento("batedeira", Posse.NAO_TEM)
        .com_tecnica("bechamel", Posse.TEM)
        .com_tecnica("temperagem", Posse.NAO_TEM)
    )
    assert "forno" in p.equipamentos_conhecidos
    assert "batedeira" in p.equipamentos_ausentes
    assert "microondas" in p.equipamentos_em_aberto
    assert "bechamel" in p.tecnicas_dominadas
    assert "temperagem" in p.tecnicas_ausentes
    assert "massa_fresca" in p.tecnicas_em_aberto


def test_completude_cresce_com_as_respostas() -> None:
    p = PerfilCozinha.inicial()
    inicial = p.completude
    assert 0 < inicial < 1

    p = p.com_equipamento("forno", Posse.TEM).com_restricao("bocas_fogao", 4)
    assert p.completude > inicial


def test_completude_chega_a_um() -> None:
    p = PerfilCozinha.inicial()
    p = p.com_equipamentos((e, Posse.TEM) for e in p.equipamentos)
    p = p.com_tecnicas((t, Posse.TEM) for t in p.tecnicas)
    p = (
        p.com_restricao("bocas_fogao", 4)
        .com_restricao("tempo_max_por_fornada_min", 120)
        .com_restricao("porcoes_por_fornada", 20)
        .com_restricao("tem_gas_sobrando", True)
        .com_restricao("espaco_geladeira_litros", 20)
        .com_restricao("energia_aparelhos_simultaneos", 2)
    )
    assert p.completude == 1.0


def test_resumo_separa_o_que_ela_respondeu_do_que_e_suposto() -> None:
    inicial = PerfilCozinha.inicial()
    assert inicial.respondidos == 0
    assert inicial.supostos > 0
    assert inicial.resumo().startswith("0 respondidos por ela · ")
    com_forno = inicial.com_equipamento("forno", Posse.TEM)
    assert com_forno.respondidos == 1
    assert "em aberto" in com_forno.resumo()


# --------------------------------------------------------------------------- #
# Serialização: o dossiê precisa sobreviver entre sessões
# --------------------------------------------------------------------------- #


def test_ida_e_volta_preserva_o_perfil() -> None:
    original = (
        PerfilCozinha.inicial()
        .com_equipamento("forno", Posse.TEM)
        .com_equipamento("batedeira", Posse.NAO_TEM)
        .com_tecnica("bechamel", Posse.TEM)
        .com_restricao("bocas_fogao", 4)
        .com_restricao("tempo_max_por_fornada_min", 90)
    )
    recuperado = PerfilCozinha.de_dict(original.para_dict())

    assert recuperado.equipamentos == original.equipamentos
    assert recuperado.tecnicas == original.tecnicas
    assert recuperado.restricoes == original.restricoes


def test_desserializacao_ignora_ids_desconhecidos() -> None:
    """Uma taxonomia futura não pode quebrar um dossiê antigo."""
    p = PerfilCozinha.de_dict(
        {
            "equipamentos": {"forno": "tem", "teletransportador": "tem"},
            "tecnicas": {"bechamel": "tem"},
            "restricoes": {"bocas_fogao": 4},
        }
    )
    assert p.tem_equipamento("forno") is Posse.TEM
    assert "teletransportador" not in p.equipamentos


def test_desserializacao_de_dados_vazios() -> None:
    p = PerfilCozinha.de_dict({})
    assert p.tem_equipamento("forno") is Posse.DESCONHECIDO


@pytest.mark.parametrize(
    "ruim",
    [
        {"equipamentos": "não é dict"},
        {"tecnicas": []},
        {"restricoes": "x"},
    ],
)
def test_desserializacao_rejeita_formato_invalido(ruim: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="malformado"):
        PerfilCozinha.de_dict(ruim)


# --------------------------------------------------------------------------- #
# Gosto                                                                        #
# --------------------------------------------------------------------------- #


def test_gosto_resolvido_distingue_silencio_de_resposta() -> None:
    """Não dizer não é o mesmo que não gostar: é a razão de o enum ter três valores."""
    from mise.perfil import Gosto

    assert Gosto.GOSTA.resolvido
    assert Gosto.NAO_GOSTA.resolvido
    assert not Gosto.DESCONHECIDO.resolvido


def test_so_nao_gostar_bloqueia() -> None:
    from mise.perfil import Gosto

    assert Gosto.NAO_GOSTA.bloqueia
    assert not Gosto.GOSTA.bloqueia
    # Desconhecido vira pergunta, nunca bloqueio: descartar prato viável sem ela
    # ter opinado é o oposto do que o §2.1 pede.
    assert not Gosto.DESCONHECIDO.bloqueia
