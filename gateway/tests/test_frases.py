"""As frases da linha do tempo da conversa: pt-BR, sem jargão, sem dinheiro solto."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from gateway.frases import (
    FRASE_GENERICA,
    FRASES,
    FRASES_DA_AGENTE,
    FRASES_DO_MOTOR,
    MARCADORES,
    SENTINELA,
    TAMANHO_DO_DETALHE,
    Frase,
    detalhe,
    frase_para,
    mascarar_dinheiro,
    nome_da_ferramenta,
)
from gateway.politica import ESCOPOS

CONTRATOS = Path(__file__).resolve().parents[2] / "contratos" / "web"

#: O que não pode chegar a ela (DESIGN.md e plano da interface), mais os nomes de sistema.
JARGAO = re.compile(
    r"\b(motor|port[aã]o|apto|falta info|bloqueado|veredito|cmv|food cost|append-only"
    r"|mcp|ferramenta|servidor|json|api)\b",
    re.IGNORECASE,
)

TODAS = [*FRASES.values(), FRASE_GENERICA]


def _textos() -> list[str]:
    return [texto for frase in TODAS for texto in frase.textos()]


# --------------------------------------------------------------------------- #
# O catálogo
# --------------------------------------------------------------------------- #


def test_toda_ferramenta_do_motor_tem_frase() -> None:
    assert set(FRASES_DO_MOTOR) == set(ESCOPOS)


def test_as_ferramentas_do_hermes_que_a_agente_usa_tem_frase() -> None:
    usadas = {
        "web_search",
        "web_extract",
        "skill_view",
        "tool_describe",
        "tool_search",
        "memory",
        "session_search",
        "list_resources",
        "read_resource",
        "vision_analyze",
        "clarify",
    }
    assert usadas <= set(FRASES_DA_AGENTE)
    assert not set(FRASES_DA_AGENTE) & set(ESCOPOS), "uma ferramenta tem uma frase só"


@pytest.mark.parametrize("texto", _textos())
def test_nenhuma_frase_tem_jargao(texto: str) -> None:
    assert not JARGAO.search(texto), texto


@pytest.mark.parametrize("texto", _textos())
def test_frase_e_minuscula_e_sem_ponto_final(texto: str) -> None:
    """A linha do tempo junta as frases; maiúscula e ponto ficam por conta da tela."""
    assert texto == texto.strip()
    assert texto[0].islower()
    assert not texto.endswith((".", "!"))


@pytest.mark.parametrize("frase", TODAS, ids=lambda f: f.rotulo)
def test_presente_e_passado_tem_os_mesmos_marcadores(frase: Frase) -> None:
    def marcadores(texto: str) -> set[str]:
        return set(re.findall(r"\{(\w+)\}", texto))

    assert marcadores(frase.rotulo) == marcadores(frase.rotulo_feito) == set(frase.marcadores)
    assert frase.marcadores <= MARCADORES


@pytest.mark.parametrize("frase", TODAS, ids=lambda f: f.rotulo)
def test_frase_com_marcador_tem_a_generica_sem_marcador(frase: Frase) -> None:
    if frase.marcadores:
        assert frase.generica is not None
        assert "{" not in "".join(frase.generica)
    else:
        assert frase.generica is None


# --------------------------------------------------------------------------- #
# O contrato da conversa
# --------------------------------------------------------------------------- #


def test_a_atividade_do_turno_de_exemplo_sai_igual() -> None:
    eventos = [
        json.loads(linha)
        for linha in (CONTRATOS / "chat-eventos.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    (atividade,) = [e for e in eventos if e["tipo"] == "atividade.iniciada"]
    frase = frase_para(atividade["ferramenta"], {"receita": {"nome": "Arroz com frango"}})
    assert frase == {
        "rotulo": atividade["rotulo"],
        "rotulo_feito": atividade["rotulo_feito"],
    }


def test_as_atividades_da_conversa_de_exemplo_saem_iguais() -> None:
    conversa = json.loads((CONTRATOS / "conversa.json").read_text(encoding="utf-8"))
    feitas = [a["rotulo_feito"] for m in conversa["mensagens"] for a in m.get("atividades", [])]
    receita = {"receita": {"nome": "Arroz com frango"}}
    assert feitas == [
        frase_para("avaliar_receita", receita)["rotulo_feito"],
        frase_para("calcular_cmv", receita)["rotulo_feito"],
    ]


# --------------------------------------------------------------------------- #
# Preenchimento
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "nome", ["avaliar_receita", "mcp__mise__avaliar_receita", "mcp_mise_avaliar_receita"]
)
def test_o_prefixo_do_hermes_nao_muda_a_frase(nome: str) -> None:
    assert nome_da_ferramenta(nome) == "avaliar_receita"
    assert frase_para(nome, {"receita": {"nome": "Bolo"}})["rotulo"] == (
        "conferindo se a senhora consegue fazer bolo"
    )


def test_ferramenta_desconhecida_nunca_mostra_o_nome_cru() -> None:
    frase = frase_para("mcp__outro__apagar_tudo", {"prato": "Bolo"})
    assert frase == {"rotulo": FRASE_GENERICA.rotulo, "rotulo_feito": FRASE_GENERICA.rotulo_feito}


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("marmita a R$ 15,90", f"marmita a {SENTINELA}"),
        ("de R$1.234,56 para R$ 12", f"de {SENTINELA} para {SENTINELA}"),
        ("uns 12 reais o quilo", f"uns {SENTINELA} o quilo"),
        ("4,50 Reais e 1 real", f"{SENTINELA} e {SENTINELA}"),
        ("r$ 15 ou US$ 3,50 ou $ 2", f"{SENTINELA} ou {SENTINELA} ou {SENTINELA}"),
        ("2 kg de arroz", "2 kg de arroz"),
    ],
)
def test_dinheiro_sai_mascarado(texto: str, esperado: str) -> None:
    assert mascarar_dinheiro(texto) == esperado


def test_a_busca_na_web_mostra_a_consulta_sem_o_dinheiro() -> None:
    frase = frase_para("web_search", {"query": "marmita de frango até R$ 20"})
    assert frase["rotulo"] == f"pesquisando na internet: marmita de frango até {SENTINELA}"
    assert frase["rotulo_feito"].startswith("pesquisei na internet: ")


def test_argumento_longo_e_cortado_sem_deixar_digito_de_dinheiro() -> None:
    """Cortar antes de mascarar deixaria "18,9" de um "18,90 reais" à mostra."""
    consulta = "a" * (TAMANHO_DO_DETALHE - 10) + " 18,90 reais " + "b" * 30
    assert re.search(r"\d", consulta[: TAMANHO_DO_DETALHE - 1]), "o corte cru cairia no valor"
    cortada = detalhe(consulta)
    assert cortada is not None
    assert len(cortada) == TAMANHO_DO_DETALHE
    assert cortada.endswith("…")
    assert SENTINELA in cortada
    assert not re.search(r"\d", cortada)


def test_argumento_vira_uma_linha_so() -> None:
    frase = frase_para("custo_unitario", {"ingrediente": "Peito\nde   frango\t"})
    assert frase["rotulo"] == "conferindo o custo de peito de frango"


@pytest.mark.parametrize(
    "argumentos",
    [None, {}, [], 42, "não é json", '["lista"]', {"receita": 7}, {"receita": {"nome": "  "}}],
)
def test_sem_o_argumento_vale_a_frase_generica(argumentos: object) -> None:
    assert frase_para("avaliar_receita", argumentos) == {
        "rotulo": "conferindo se a senhora consegue fazer a receita",
        "rotulo_feito": "conferi se a senhora consegue fazer a receita",
    }


def test_argumentos_em_texto_json_tambem_valem() -> None:
    receita = json.dumps({"receita": json.dumps({"nome": "Frango à parmegiana"})})
    assert frase_para("avaliar_receita", receita)["rotulo_feito"] == (
        "conferi se a senhora consegue fazer frango à parmegiana"
    )


def test_sigla_no_comeco_do_nome_fica_maiuscula() -> None:
    assert frase_para("registrar_gosto", {"prato": "BBQ de costela"})["rotulo"] == (
        "anotando o que a senhora acha de BBQ de costela"
    )


@pytest.mark.parametrize(
    ("ferramenta", "argumentos", "rotulo"),
    [
        (
            "buscar_receita_na_web",
            {"url": "https://www.tudogostoso.com.br/receita/1-arroz"},
            "lendo a receita de tudogostoso.com.br",
        ),
        (
            "buscar_receita_na_web",
            {"url": "https://x.com/r", "fonte": "TudoGostoso"},
            "lendo a receita de TudoGostoso",
        ),
        ("buscar_receita_na_web", {"url": "não é endereço"}, "lendo uma receita da internet"),
        ("buscar_receita_na_web", {"url": "http://[::1"}, "lendo uma receita da internet"),
        ("buscar_receita_na_web", {"url": 12}, "lendo uma receita da internet"),
        (
            "web_extract",
            {"urls": ["https://panelinha.com.br/receita/x", "https://outro.com"]},
            "lendo uma página de panelinha.com.br",
        ),
        ("web_extract", {"urls": []}, "lendo uma página da internet"),
    ],
)
def test_a_fonte_vem_do_argumento_ou_do_endereco(
    ferramenta: str, argumentos: dict[str, object], rotulo: str
) -> None:
    assert frase_para(ferramenta, argumentos)["rotulo"] == rotulo


@pytest.mark.parametrize(
    ("ferramenta", "argumentos", "rotulo_feito"),
    [
        ("diagnostico_despensa", {}, "olhei sua despensa"),
        ("registrar_compra", {"ingrediente": "Milho verde"}, "anotei a compra de milho verde"),
        ("registrar_compra", {}, "anotei a compra"),
        ("registrar_preco_mercado", {"ingrediente": "trufa"}, "anotei o preço de trufa"),
        ("registrar_decisao", {"prato": "Bolo", "preco": 12}, "guardei a decisão da senhora"),
        ("testar_sensibilidade", {"preco": 12}, "fiz a conta desse preço"),
        (
            "estimar_preco_preliminar",
            {"prato": "Arroz com frango"},
            "fiz uma estimativa do preço de arroz com frango",
        ),
        (
            "estimar_preco_preliminar",
            {"receita_id": "3f2a9c0d1b7e4a55"},
            "fiz uma estimativa do preço",
        ),
        ("registrar_avaliacao_da_receita", {"receita_id": "x"}, "anotei a avaliação da senhora"),
        ("pauta_de_descoberta", {}, "separei o que procurar com o que a senhora tem"),
        ("_thinking", {}, "pensei no próximo passo"),
    ],
)
def test_frases_de_exemplo(
    ferramenta: str, argumentos: dict[str, object], rotulo_feito: str
) -> None:
    assert frase_para(ferramenta, argumentos)["rotulo_feito"] == rotulo_feito


def test_preco_do_argumento_nunca_entra_na_frase() -> None:
    """Nenhuma frase mostra o preço que o modelo passou: só a conta do card mostra."""
    for nome in FRASES:
        frase = frase_para(nome, {"preco": 12.5, "valor": 99, "prato": "Bolo", "query": "x"})
        assert "12" not in frase["rotulo"] + frase["rotulo_feito"]
        assert "99" not in frase["rotulo"] + frase["rotulo_feito"]
