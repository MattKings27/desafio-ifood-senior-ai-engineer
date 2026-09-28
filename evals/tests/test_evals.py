"""Testes do próprio avaliador.

Um avaliador que sempre aprova é pior que nenhum: ele produz a mesma tela verde
de um sistema correto. Estes testes verificam que ele **consegue** reprovar.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from evals import adversarial, portao

CASOS = Path(__file__).resolve().parents[1] / "casos"


@pytest.fixture(scope="module")
def despensa():
    from mise.despensa import carregar_despensa

    return carregar_despensa(
        Path(__file__).resolve().parents[2] / "dados" / "despensa_dona_maria.xlsx"
    )


def test_o_dataset_dourado_passa_inteiro(despensa) -> None:
    falhas = [r for r in portao.rodar(despensa=despensa) if not r.passou]
    assert not falhas, "\n".join(f"{r.nome}: {r.motivo}" for r in falhas)


def test_todos_os_ataques_sao_defendidos(despensa) -> None:
    furos = [a for a in adversarial.rodar(despensa) if not a.defendeu]
    assert not furos, "\n".join(f"{a.nome}: {a.garantia} ({a.detalhe})" for a in furos)


def test_o_avaliador_consegue_reprovar(despensa, tmp_path: Path) -> None:
    """Um caso deliberadamente errado tem que falhar.

    É o teste que impede o avaliador de virar decoração: se ele aprovasse isto,
    aprovaria qualquer coisa.
    """
    caso = yaml.safe_load((CASOS / "portao.yaml").read_text(encoding="utf-8"))[0]
    caso["espera"]["veredito"] = "BLOQUEADO"  # o certo é APTO

    arquivo = tmp_path / "errado.yaml"
    arquivo.write_text(yaml.safe_dump([caso], allow_unicode=True), encoding="utf-8")

    resultados = portao.rodar(arquivo, despensa)
    assert not resultados[0].passou
    assert "esperava BLOQUEADO" in resultados[0].motivo


def test_avaliador_pega_pergunta_ausente(despensa, tmp_path: Path) -> None:
    caso = yaml.safe_load((CASOS / "portao.yaml").read_text(encoding="utf-8"))[0]
    caso["espera"]["pergunta_contendo"] = "algo que ninguém pergunta"

    arquivo = tmp_path / "errado.yaml"
    arquivo.write_text(yaml.safe_dump([caso], allow_unicode=True), encoding="utf-8")

    r = portao.rodar(arquivo, despensa)[0]
    assert not r.passou
    assert "nenhuma pergunta menciona" in r.motivo


def _caso_do_peso() -> dict:
    casos = yaml.safe_load((CASOS / "portao.yaml").read_text(encoding="utf-8"))
    return next(c for c in casos if c["nome"] == "peso_informado_por_ela_destrava_o_custo")


@pytest.mark.parametrize(
    ("muda", "motivo"),
    [
        ({"resposta_dela": [{"linha": "sal a gosto", "peso": "5 g"}]}, "não perguntava o peso"),
        (
            {"resposta_dela": [{"linha": "1 peito cortado em 4 filés", "peso": "400 g"}]},
            "saiu R$ 2,80",
        ),
        ({"antes_da_resposta": {"veredito": "FALTA INFO"}}, "antes da resposta"),
    ],
)
def test_avaliador_pega_a_resposta_dela_errada(
    despensa, tmp_path: Path, muda: dict, motivo: str
) -> None:
    """O peso que não era pergunta, o custo que não fecha e o antes que não pergunta reprovam."""
    caso = {**_caso_do_peso(), **muda}
    arquivo = tmp_path / "errado.yaml"
    arquivo.write_text(yaml.safe_dump([caso], allow_unicode=True), encoding="utf-8")
    r = portao.rodar(arquivo, despensa)[0]
    assert not r.passou
    assert motivo in r.motivo


def test_avaliador_pega_custo_sem_conferencia(despensa, tmp_path: Path) -> None:
    """O preço que não se acha segura a conferência, e o custo: o avaliador pega o custo pedido."""
    casos = yaml.safe_load((CASOS / "portao.yaml").read_text(encoding="utf-8"))
    caso = next(c for c in casos if c["nome"] == "ingrediente_sem_preco_fica_de_fora_sem_pergunta")
    caso["espera"] = {"veredito": "BLOQUEADO", "custo_por_porcao": "R$ 2,10"}
    arquivo = tmp_path / "errado.yaml"
    arquivo.write_text(yaml.safe_dump([caso], allow_unicode=True), encoding="utf-8")
    r = portao.rodar(arquivo, despensa)[0]
    assert not r.passou
    assert "a conferência não libera" in r.motivo


def test_cada_caso_tem_descricao() -> None:
    """Caso sem descrição não explica o que protege, e ninguém sabe se pode mudar."""
    casos = yaml.safe_load((CASOS / "portao.yaml").read_text(encoding="utf-8"))
    sem = [c["nome"] for c in casos if not c.get("descricao", "").strip()]
    assert not sem, f"casos sem descrição: {sem}"


def test_todo_ataque_nomeia_a_garantia() -> None:
    """Ataque sem garantia nomeada não diz o que quebrou quando passa."""
    for a in adversarial.rodar():
        assert a.garantia.strip(), f"{a.nome} não nomeia a garantia que testa"


def test_os_vereditos_cobrem_os_quatro_estados() -> None:
    """Um dataset que só tem caso feliz não prova portão nenhum."""
    casos = yaml.safe_load((CASOS / "portao.yaml").read_text(encoding="utf-8"))
    vereditos = {c["espera"]["veredito"] for c in casos}
    assert vereditos == {"APTO", "APTO COM COMPRA", "FALTA INFO", "BLOQUEADO"}


# --------------------------------------------------------------------------- #
# Apresentação e resolução de caminho                                          #
# --------------------------------------------------------------------------- #


def test_resultado_se_apresenta() -> None:
    assert "ok" in str(portao.Resultado("x", True))
    assert "FALHA" in str(portao.Resultado("x", False, "porque sim"))
    assert "porque sim" in str(portao.Resultado("x", False, "porque sim"))


def test_ataque_se_apresenta() -> None:
    assert "defendeu" in str(adversarial.Ataque("x", "g", True))
    assert "PASSOU" in str(adversarial.Ataque("x", "g", False, "furou"))
    assert "furou" in str(adversarial.Ataque("x", "g", False, "furou"))


def test_planilha_respeita_a_variavel_de_ambiente(monkeypatch) -> None:
    """Permite avaliar contra outra planilha sem editar código."""
    monkeypatch.setenv("MISE_PLANILHA", "/caminho/inventado.xlsx")
    assert str(portao._planilha()) == "/caminho/inventado.xlsx"
    assert str(adversarial._planilha()) == "/caminho/inventado.xlsx"


def test_planilha_padrao_aponta_para_a_real(monkeypatch) -> None:
    monkeypatch.delenv("MISE_PLANILHA", raising=False)
    assert portao._planilha().name == "despensa_dona_maria.xlsx"
    assert adversarial._planilha().name == "despensa_dona_maria.xlsx"


# --------------------------------------------------------------------------- #
# Os ramos de falha: só executam quando uma garantia quebra                    #
# --------------------------------------------------------------------------- #


def test_caso_com_permite_precificar_errado(despensa, tmp_path: Path) -> None:
    caso = yaml.safe_load((CASOS / "portao.yaml").read_text(encoding="utf-8"))[0]
    caso["espera"]["permite_precificar"] = False  # o certo é True

    arquivo = tmp_path / "errado.yaml"
    arquivo.write_text(yaml.safe_dump([caso], allow_unicode=True), encoding="utf-8")

    r = portao.rodar(arquivo, despensa)[0]
    assert not r.passou
    assert "permite_precificar" in r.motivo


def test_caso_com_impedimento_ausente(despensa, tmp_path: Path) -> None:
    caso = yaml.safe_load((CASOS / "portao.yaml").read_text(encoding="utf-8"))[0]
    caso["espera"]["impedimento_contendo"] = "coisa que não impede nada"

    arquivo = tmp_path / "errado.yaml"
    arquivo.write_text(yaml.safe_dump([caso], allow_unicode=True), encoding="utf-8")

    r = portao.rodar(arquivo, despensa)[0]
    assert not r.passou
    assert "nenhum impedimento menciona" in r.motivo


def test_extracao_de_pagina_com_injecao_preserva_o_texto() -> None:
    """A frase da injeção vira nome de ingrediente: dado, não instrução."""
    a = adversarial.injecao_vinda_de_pagina_de_receita()
    assert a.defendeu
    assert "nome de ingrediente" in a.detalhe


def _caso(nome: str) -> dict:
    casos = yaml.safe_load((CASOS / "portao.yaml").read_text(encoding="utf-8"))
    return next(c for c in casos if c["nome"] == nome)


def _rodar_um(caso: dict, despensa, tmp_path: Path) -> portao.Resultado:
    arquivo = tmp_path / "um.yaml"
    arquivo.write_text(yaml.safe_dump([caso], allow_unicode=True), encoding="utf-8")
    return portao.rodar(arquivo, despensa)[0]


def test_caso_com_aviso_ausente(despensa, tmp_path: Path) -> None:
    """O aviso não muda o veredito: sem conferir o texto, uma boca só passaria calada."""
    caso = _caso("outra_panela_com_duas_bocas_passa_sem_aviso")
    caso["espera"] = {"veredito": "APTO", "aviso_contendo": "Com uma boca"}
    r = _rodar_um(caso, despensa, tmp_path)
    assert not r.passou
    assert "nenhum aviso menciona" in r.motivo


def test_caso_com_aviso_que_nao_devia(despensa, tmp_path: Path) -> None:
    caso = _caso("outra_panela_com_uma_boca_avisa_sem_bloquear")
    caso["espera"] = {"veredito": "APTO", "sem_aviso": True}
    r = _rodar_um(caso, despensa, tmp_path)
    assert not r.passou
    assert "não devia avisar" in r.motivo


def test_perfil_que_nao_existe_e_erro_e_nao_perfil_completo() -> None:
    """Um nome digitado errado virava o perfil completo, e o caso passava sem provar nada."""
    with pytest.raises(ValueError, match="completo_sem_fogao"):
        portao._perfil("completo_sem_fogão")


def test_os_perfis_nomeados_mudam_o_que_dizem() -> None:
    from mise.perfil import Posse

    assert portao._perfil("completo_sem_fogao").tem_equipamento("fogao") is Posse.NAO_TEM
    assert portao._perfil("completo_sem_saber_do_fogao").tem_equipamento("fogao") is (
        Posse.DESCONHECIDO
    )
    assert portao._perfil("completo_uma_boca").restricoes.bocas_fogao == 1
    assert (
        portao._perfil("completo_sem_saber_da_geladeira").restricoes.espaco_geladeira_litros is None
    )
    assert portao._perfil("completo_rapido").restricoes.tempo_max_por_fornada_min == 60
    assert portao._perfil("completo").restricoes.tempo_max_por_fornada_min == 240


def test_os_tres_tempos_chegam_na_receita_do_caso() -> None:
    receita = portao._receita(
        {
            "nome": "Bolo",
            "ingredientes": [{"texto": "3 ovos", "nome": "ovos", "quantidade": 3, "medida": "ovo"}],
            "tempo_preparo_min": 20,
            "tempo_cozimento_min": 40,
            "tempo_total_min": 60,
        }
    )
    assert (receita.tempo_preparo_min, receita.tempo_cozimento_min, receita.tempo_total_min) == (
        20,
        40,
        60,
    )


# --------------------------------------------------------------------------- #
# O que o caso diz de cada ingrediente e da procedência                        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("nome", "espera", "motivo"),
    [
        (
            "tempero_sem_quantidade_vai_a_gosto",
            {"situacao": {"temperos de sua preferência": "nao_entendi"}},
            "devia ser nao_entendi, e ficou a_gosto",
        ),
        (
            "tempero_sem_quantidade_vai_a_gosto",
            {"situacao": {"trufa branca": "falta"}},
            "nenhuma linha da receita é 'trufa branca'",
        ),
        (
            "opcional_que_ela_nao_tem_fica_listado",
            {"opcional_listado": "Peito de frango"},
            "não ficou listado como opcional",
        ),
        (
            "receita_digitada_com_endereco_falso_nao_e_da_internet",
            {"origem": "web"},
            "a origem devia ser web, e é informada_por_ela",
        ),
    ],
)
def test_o_avaliador_confere_ingredientes_e_procedencia(
    despensa, tmp_path: Path, nome: str, espera: dict[str, object], motivo: str
) -> None:
    caso = _caso(nome)
    caso["espera"] = {"veredito": caso["espera"]["veredito"], **espera}
    r = _rodar_um(caso, despensa, tmp_path)
    assert not r.passou
    assert motivo in r.motivo


def test_o_avaliador_pega_receita_que_ficou_com_endereco(despensa) -> None:
    """Se a receita digitada guardasse o endereço, o caso tem de reprovar."""
    from mise.receita import Origem

    caso = _caso("receita_digitada_com_endereco_falso_nao_e_da_internet")
    receita = portao._receita_digitada(caso["receita"])
    from dataclasses import replace

    com_endereco = replace(receita, url="https://exemplo.com.br/x", origem=Origem.WEB)
    divergencias = portao._da_receita(
        {"sem_endereco": True},
        com_endereco,
        portao.avaliar(receita, portao._perfil("completo"), despensa),
    )
    assert divergencias == ["a receita ficou com o endereço 'https://exemplo.com.br/x'"]


def test_linha_do_caso_passa_pelo_leitor_das_paginas() -> None:
    linha = portao._ingrediente({"linha": "1 xícara de uva-passa (opcional)"})
    assert (linha.nome, linha.opcional, linha.medida) == ("uva-passa", True, "xicara")
    assert portao._ingrediente({"texto": "x", "nome": "x", "opcional": True}).opcional


def _caso_do_aceite(nome: str) -> dict:
    casos = yaml.safe_load((CASOS / "portao.yaml").read_text(encoding="utf-8"))
    return next(c for c in casos if c["nome"] == nome)


@pytest.mark.parametrize(
    ("chave", "errado", "motivo"),
    [
        ("aceite", "liberado", "o aceite devia ser liberado"),
        ("confirmar_a_cozinha", ["fogao"], "a confirmação devia pedir ['fogao']"),
        ("pergunta_do_aceite", "Antes de aceitar, a senhora tem forno?", "a pergunta do aceite"),
    ],
)
def test_o_avaliador_pega_o_aceite_errado(
    despensa, tmp_path: Path, chave: str, errado: object, motivo: str
) -> None:
    """O aceite com o básico suposto é recusado; o caso que diz outra coisa reprova."""
    caso = _caso_do_aceite("aceite_espera_ela_confirmar_o_que_toda_cozinha_tem")
    caso["espera"][chave] = errado
    arquivo = tmp_path / "errado.yaml"
    arquivo.write_text(yaml.safe_dump([caso], allow_unicode=True), encoding="utf-8")
    r = portao.rodar(arquivo, despensa)[0]
    assert not r.passou
    assert motivo in r.motivo


def test_a_pergunta_do_aceite_sem_nada_a_confirmar_reprova(despensa, tmp_path: Path) -> None:
    caso = _caso_do_aceite("aceite_liberado_depois_que_ela_confirma")
    caso["espera"]["pergunta_do_aceite"] = "Antes de aceitar, a senhora confirma que tem fogão?"
    arquivo = tmp_path / "errado.yaml"
    arquivo.write_text(yaml.safe_dump([caso], allow_unicode=True), encoding="utf-8")
    assert not portao.rodar(arquivo, despensa)[0].passou
