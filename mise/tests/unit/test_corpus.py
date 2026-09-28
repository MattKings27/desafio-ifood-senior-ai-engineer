"""O site inteiro como corpus: cada tela vira trechos com fonte, rota e o contexto no cabeçalho."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from retrieval.corpus import Trecho

from mise import corpus, perfil_historico
from mise.catalogo import Catalogo, OrigemNoCatalogo, ReceitaDoCatalogo
from mise.despensa import carregar_despensa
from mise.dinheiro import Dinheiro
from mise.dossie import Canal, Decisao, Dossie, OrigemPreco
from mise.mcp_server import ReceitaEntrada, Sessao
from mise.perfil import Gosto, Posse
from mise.perfil_historico import TipoDeItem
from mise.receita import Origem, Receita

PLANILHA = Path(__file__).resolve().parents[3] / "dados" / "despensa_dona_maria.xlsx"
AGORA = datetime(2026, 9, 25, 13, 0, tzinfo=UTC)

BOLO: dict[str, Any] = {
    "nome": "Bolo de fubá",
    "rendimento_porcoes": 8,
    "modo_preparo": ["Bata tudo no liquidificador por 3 minutos.", "Leve ao forno por 40 minutos."],
    "url": "https://www.tudogostoso.com.br/receita/123-bolo-de-fuba",
    "fonte": "TudoGostoso",
    "ingredientes": [
        {"texto": "2 xícaras de fubá", "nome": "fubá", "quantidade": 2, "medida": "xicara"},
        {
            "texto": "1 colher de fermento",
            "nome": "fermento",
            "quantidade": 1,
            "medida": "colher de sopa",
            "opcional": True,
        },
    ],
}

ARROZ: dict[str, Any] = {
    "nome": "Arroz com frango",
    "modo_preparo": ["Junte o frango e o arroz e cozinhe na panela."],
    "ingredientes": [
        {"texto": "500 g de frango", "nome": "peito de frango", "quantidade": 500, "medida": "g"},
        {"texto": "sal a gosto", "nome": "sal"},
    ],
}


def _da_web(dados: dict[str, Any]) -> Receita:
    """A receita como a busca na web a guarda: com o endereço e o site."""
    ditada = ReceitaEntrada(**{k: v for k, v in dados.items() if k not in ("url", "fonte")})
    return replace(ditada.para_dominio(), url=dados["url"], fonte=dados["fonte"], origem=Origem.WEB)


@pytest.fixture
def sessao(tmp_path: Path) -> Sessao:
    dossie = Dossie(tmp_path / "dossie.db", relogio=lambda: AGORA)
    sessao = Sessao(planilha=carregar_despensa(PLANILHA), dossie=dossie)
    perfil_historico.mudar_item(dossie, TipoDeItem.EQUIPAMENTO, "forno", Posse.TEM, Canal.TELA)
    perfil_historico.mudar_item(
        dossie, TipoDeItem.EQUIPAMENTO, "air_fryer", Posse.NAO_TEM, Canal.CONVERSA
    )
    perfil_historico.mudar_restricao(dossie, "bocas_fogao", 4, Canal.TELA)
    sessao.guardar(_da_web(BOLO))
    sessao.guardar(ReceitaEntrada(**ARROZ).para_dominio())
    dossie.registrar_gosto("Bolo de fubá", Gosto.NAO_GOSTA, "o forno esquenta a casa")
    dossie.registrar_decisao("Arroz com frango", Decisao.ADIADO, "falta o gosto", canal=Canal.TELA)
    dossie.registrar_decisao("Arroz com frango", Decisao.ACEITO, detalhes={"preco": "R$ 18,00"})
    dossie.registrar_compra("coco ralado", Decimal(100), "g", Dinheiro.de("6.00"), "Coco ralado")
    dossie.registrar_preco(
        "amendoim", Dinheiro.de("8.00"), OrigemPreco.INFORMADO_POR_ELA, Decimal(200), "g"
    )
    dossie.registrar_preco("shoyu", Dinheiro.de("7.00"), OrigemPreco.PESQUISADO_NA_WEB)
    sessao.mudar_despensa(lambda editavel: editavel.acabou("leite-integral"))
    yield sessao
    dossie.fechar()


def _por_id(sessao: Sessao) -> dict[str, Trecho]:
    return {t.id: t for t in corpus.montar_trechos(sessao, conhecimento=False)}


# --------------------------------------------------------------------------- #
# Os trechos de cada tela
# --------------------------------------------------------------------------- #


def test_item_da_despensa_com_a_conta_a_origem_e_a_planilha(sessao: Sessao) -> None:
    alcaparras = _por_id(sessao)["despensa:alcaparras"]
    assert (alcaparras.tipo, alcaparras.rota, alcaparras.fonte) == (
        "despensa",
        "/despensa/alcaparras",
        "a despensa da senhora",
    )
    assert alcaparras.cabecalho == "Alcaparras, na despensa da senhora:"
    assert "Comprou 1 balde de 2 kg por R$ 82,00." in alcaparras.corpo
    assert "R$ 82,00 ÷ 2 kg = R$ 41,00/kg" in alcaparras.corpo
    assert "Origem: da planilha." in alcaparras.corpo
    assert "aba Precos, linha 30 (Alcaparras | 1 | balde 2kg | R$ 82,00)" in alcaparras.corpo
    assert alcaparras.nome == "Alcaparras, na sua despensa"


def test_item_que_acabou_e_a_ultima_mudanca(sessao: Sessao) -> None:
    leite = _por_id(sessao)["despensa:leite-integral"]
    assert leite.corpo.startswith("O estoque acabou.")
    assert "Última mudança:" in leite.corpo
    assert "na conversa em 25/09/2026, 10:00" in leite.corpo


def test_item_com_peso_estimado_e_o_resumo(sessao: Sessao) -> None:
    trechos = _por_id(sessao)
    cobertura = trechos["despensa:cobertura-de-chocolate"]
    # O peso que a planilha não diz vem estimado, com a fonte: nada em aberto para ela.
    assert "Falta saber:" not in cobertura.corpo
    assert "estimativa" in cobertura.corpo
    resumo = trechos["despensa:resumo"]
    assert resumo.rota == "/despensa"
    assert "37 itens, e a senhora pagou R$ 663,39 no total." in resumo.corpo
    assert "Alcaparras (R$ 82,00, 12% do que a senhora pagou)" in resumo.corpo
    assert "Itens com pergunta em aberto" not in resumo.corpo


def test_cozinha_com_quem_disse_quando_e_o_que_substitui(sessao: Sessao) -> None:
    trechos = _por_id(sessao)
    forno = trechos["cozinha:equipamento:forno"]
    assert forno.rota == "/cozinha"
    assert forno.corpo.startswith("A senhora disse que tem forno, pela tela em 25/09/2026, 10:00.")
    assert "O que faz o mesmo papel: air fryer e forno elétrico." in forno.corpo
    assert "Receitas que pedem: Bolo de fubá." in forno.corpo
    assert "assar" in forno.palavras
    air_fryer = trechos["cozinha:equipamento:air_fryer"]
    assert "não tem air fryer, na conversa" in air_fryer.corpo
    liquidificador = trechos["cozinha:equipamento:liquidificador"]
    assert liquidificador.corpo.startswith("Ainda não perguntei à senhora.")
    assert "A senhora tem liquidificador aí na cozinha?" in liquidificador.corpo
    faca = trechos["cozinha:equipamento:faca"]
    assert faca.corpo.startswith("Está como suposto")
    refogar = trechos["cozinha:tecnica:refogar"]
    assert "Dificuldade 1 de 5." in refogar.corpo
    bocas = trechos["cozinha:restricao:bocas_fogao"]
    assert bocas.corpo == "A senhora disse que o fogão tem 4 bocas, pela tela em 25/09/2026, 10:00."
    gas = trechos["cozinha:restricao:tem_gas_sobrando"]
    assert gas.corpo.startswith("Ainda não perguntei. A pergunta é:")


def test_restricao_anotada_sem_historico(sessao: Sessao) -> None:
    perfil = sessao.perfil.com_restricao("porcoes_por_fornada", 12)
    sessao.dossie.salvar_perfil(perfil)
    porcoes = _por_id(sessao)["cozinha:restricao:porcoes_por_fornada"]
    assert porcoes.corpo == "Está anotado que monta 12 marmitas numa leva."


def test_equipamento_anotado_sem_historico(sessao: Sessao) -> None:
    perfil = sessao.perfil
    sessao.dossie.salvar_perfil(
        perfil.com_equipamento("microondas", Posse.TEM).com_equipamento("freezer", Posse.NAO_TEM)
    )
    trechos = _por_id(sessao)
    assert trechos["cozinha:equipamento:microondas"].corpo.startswith(
        "Está anotado que a senhora tem."
    )
    assert trechos["cozinha:equipamento:freezer"].corpo.startswith(
        "Está anotado que a senhora não tem."
    )


def test_receita_em_pai_e_filhos(sessao: Sessao) -> None:
    trechos = _por_id(sessao)
    slug = "2bbb7aef61479a21"
    pai = trechos[f"receita:{slug}"]
    assert pai.cabecalho == "Receita Bolo de fubá, TudoGostoso:"
    assert (pai.rota, pai.fonte, pai.pai) == (f"/receitas/{slug}", "TudoGostoso", None)
    assert "Rende 8 porções." in pai.corpo
    assert "A receita veio do site TudoGostoso." in pai.corpo
    assert (
        "Endereço da receita: https://www.tudogostoso.com.br/receita/123-bolo-de-fuba." in pai.corpo
    )
    assert "Situação para a senhora: Não dá." in pai.corpo
    ingredientes = trechos[f"receita:{slug}:ingredientes"]
    assert ingredientes.pai == pai.id
    assert "Opcionais: fermento." in ingredientes.corpo
    passo = trechos[f"receita:{slug}:passo-2"]
    assert passo.cabecalho == "Receita Bolo de fubá, TudoGostoso, passo 2 de 2:"
    assert (passo.pai, passo.ordem) == (pai.id, 2)
    assert "Pede forno (a senhora tem)." in passo.corpo
    assert "Tempo: 40 min no forno." in passo.corpo


def test_receita_ditada_sem_rendimento_e_a_gosto(sessao: Sessao) -> None:
    trechos = _por_id(sessao)
    arroz = trechos["receita:arroz-com-frango"]
    assert arroz.cabecalho == "Receita Arroz com frango, receita que a senhora ditou:"
    assert arroz.fonte == "receita ditada pela senhora"
    assert "A receita não diz quantas porções rende." in arroz.corpo
    assert "Falta saber:" in arroz.corpo
    assert "A gosto: sal." in trechos["receita:arroz-com-frango:ingredientes"].corpo


def test_avaliacao_cardapio_e_orcamento(sessao: Sessao) -> None:
    trechos = _por_id(sessao)
    gosto = trechos["avaliacao:2bbb7aef61479a21"]
    assert gosto.corpo == (
        "A senhora disse que não gosta de fazer, em 25/09/2026, 10:00. "
        "Impedimento que ela vê: o forno esquenta a casa."
    )
    cardapio = trechos["cardapio:arroz-com-frango"]
    assert cardapio.rota == "/cardapio"
    assert cardapio.corpo.startswith("A senhora aceitou pôr no cardápio a R$ 18,00 na conversa")
    assert "Antes, a senhora deixou para decidir depois pela tela" in cardapio.corpo
    assert "(motivo: falta o gosto)" in cardapio.corpo
    assert trechos["cardapio:resumo"].corpo == "Pratos no cardápio: Arroz com frango."
    orcamento = trechos["orcamento"]
    assert orcamento.rota == "/despensa#orcamento"
    assert "A senhora já usou R$ 6,00 e restam R$ 74,00. 1 compra contando." in orcamento.corpo
    assert trechos["orcamento:compra-1"].corpo.startswith("Coco ralado: R$ 6,00, na conversa")
    amendoim = trechos["orcamento:preco-amendoim"]
    assert amendoim.corpo == "R$ 8,00 por 0,2 kg, a senhora informou em 25/09/2026, 10:00."
    assert trechos["orcamento:preco-shoyu"].corpo.startswith("R$ 7,00, foi pesquisado na internet")


def test_estrelas_notas_e_pontuacao_entram_na_avaliacao(sessao: Sessao) -> None:
    from mise.avaliacoes import Avaliacoes

    Avaliacoes(sessao.dossie).gravar(
        "2bbb7aef61479a21", estrelas={"sabor": 5, "apelo": 4}, notas="Testar com açafrão."
    )
    Avaliacoes(sessao.dossie).gravar("arroz-com-frango", notas="Vende bem no almoço.")
    trechos = _por_id(sessao)
    bolo = trechos["avaliacao:2bbb7aef61479a21"]
    assert "Estrelas que ela deu, de 1 a 5: sabor 5 e apelo de venda 4." in bolo.corpo
    assert "Pontuação " in bolo.corpo
    assert "de 100 (" in bolo.corpo
    assert bolo.corpo.endswith("Notas dela: Testar com açafrão.")
    so_notas = trechos["avaliacao:arroz-com-frango"]
    assert so_notas.corpo == "Notas dela: Vende bem no almoço."


def test_compra_devolvida_e_o_cardapio_vazio(tmp_path: Path) -> None:
    dossie = Dossie(tmp_path / "d.db", relogio=lambda: AGORA)
    sessao = Sessao(planilha=carregar_despensa(PLANILHA), dossie=dossie)
    dossie.registrar_compra("coco", Decimal(100), "g", Dinheiro.de("6.00"), "Coco")
    dossie.estornar(1)
    trechos = {t.id: t for t in corpus.montar_trechos(sessao, conhecimento=False)}
    assert "depois devolvida aos complementos" in trechos["orcamento:compra-1"].corpo
    assert "Nenhuma compra contando" in trechos["orcamento"].corpo
    assert trechos["cardapio:resumo"].corpo == "Ainda não há prato no cardápio."
    vazia = Sessao(planilha=carregar_despensa(PLANILHA), dossie=Dossie(tmp_path / "v.db"))
    assert (
        "Nenhuma compra ainda."
        in {t.id: t for t in corpus.trechos_do_orcamento(vazia)}["orcamento"].corpo
    )
    dossie.fechar()
    vazia.dossie.fechar()


def test_receita_do_catalogo_entra_pelo_adaptador(
    sessao: Sessao, monkeypatch: pytest.MonkeyPatch
) -> None:
    receita = ReceitaEntrada(
        **{**ARROZ, "nome": "Farofa da casa", "rendimento_porcoes": 2}
    ).para_dominio()
    guardada = ReceitaDoCatalogo(
        slug="farofa-da-casa",
        receita=receita,
        origem=OrigemNoCatalogo.DESCOBERTA,
        site="Receiteria",
    )
    repetida = ReceitaDoCatalogo(
        slug="arroz-com-frango", receita=receita, origem=OrigemNoCatalogo.DESCOBERTA
    )
    monkeypatch.setattr(Catalogo, "listar", lambda _self, **_: (guardada, repetida))
    trechos = _por_id(sessao)
    assert "Está no catálogo." in trechos["receita:farofa-da-casa"].corpo
    assert trechos["receita:arroz-com-frango"].cabecalho.startswith("Receita Arroz com frango")


JARGAO = re.compile(
    r"\b(?:motor|port[aã]o|apto|falta info|bloqueado|veredito|cmv|food cost)\b", re.IGNORECASE
)


def test_nenhum_trecho_tem_jargao_nem_travessao(sessao: Sessao) -> None:
    """O texto dos trechos chega a ela pelo agente: na língua dela, sem separador."""
    for trecho in corpus.montar_trechos(sessao):
        assert not JARGAO.search(trecho.texto), trecho.id
        assert " \u2014 " not in trecho.texto and " \u2013 " not in trecho.texto, trecho.id


def test_conhecimento_entra_quando_pedido(sessao: Sessao) -> None:
    com = corpus.montar_trechos(sessao)
    sem = corpus.montar_trechos(sessao, conhecimento=False)
    assert len(com) - len(sem) >= 40
    assert all(t.tipo == "conhecimento" for t in com[len(sem) :])


def test_sem_planilha_legivel_o_item_continua(
    sessao: Sessao, monkeypatch: pytest.MonkeyPatch
) -> None:
    def quebrar(*_: object) -> None:
        raise OSError("planilha sumiu")

    corpus._linhas_da_planilha.cache_clear()
    monkeypatch.setattr("mise.planilha_txt.ler_celulas", quebrar)
    alcaparras = _por_id(sessao)["despensa:alcaparras"]
    assert "Na planilha dela" not in alcaparras.corpo
    corpus._linhas_da_planilha.cache_clear()


def test_sem_origem_da_planilha(sessao: Sessao, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sessao.planilha, "origem", None)
    assert corpus._planilha(sessao) == {}


# --------------------------------------------------------------------------- #
# A versão, o índice e a consulta
# --------------------------------------------------------------------------- #


def test_o_carimbo_muda_quando_algo_e_gravado(sessao: Sessao) -> None:
    antes = corpus.carimbo(sessao)
    assert corpus.carimbo(sessao) == antes
    sessao.dossie.registrar_gosto("Arroz com frango", Gosto.GOSTA)
    depois = corpus.carimbo(sessao)
    assert depois != antes
    perfil_historico.mudar_restricao(sessao.dossie, "bocas_fogao", 2, Canal.TELA)
    assert corpus.carimbo(sessao) != depois


def test_o_indice_so_e_refeito_quando_o_estado_muda(sessao: Sessao) -> None:
    corpus_ = corpus.CorpusDaSessao(sessao)
    primeiro = corpus_.indice()
    assert corpus_.indice() is primeiro
    assert corpus_.reconstrucoes == 1
    sessao.dossie.registrar_gosto("Arroz com frango", Gosto.GOSTA)
    assert corpus_.indice() is not primeiro
    assert corpus_.reconstrucoes == 2


def test_um_corpus_por_sessao(sessao: Sessao, tmp_path: Path) -> None:
    assert corpus.corpus_da_sessao(sessao) is corpus.corpus_da_sessao(sessao)
    outra = Sessao(planilha=sessao.planilha, dossie=Dossie(tmp_path / "outra.db"))
    assert corpus.corpus_da_sessao(outra) is not corpus.corpus_da_sessao(sessao)
    assert corpus.vetorizador_da_sessao(sessao) is corpus.vetorizador_da_sessao(sessao)
    outra.dossie.fechar()


def test_consultar_na_forma_do_contrato(sessao: Sessao) -> None:
    corpus_ = corpus.CorpusDaSessao(sessao)
    resposta = corpus_.consultar("quanto paguei nas alcaparras?")
    assert set(resposta) == {"trechos", "nada_relevante", "texto"}
    assert resposta["trechos"][0]["id"] == "despensa:alcaparras"
    assert resposta["texto"].startswith("Achei ")
    um = corpus_.consultar("quanto paguei nas alcaparras?", k=1)
    assert um["texto"] == "Achei 1 trecho com fonte sobre a pergunta."
    nada = corpus_.consultar("qual a capital da França?")
    assert (nada["trechos"], nada["nada_relevante"], nada["texto"]) == ([], True, corpus.NAO_SEI)


def test_as_fontes_viram_chips(sessao: Sessao) -> None:
    corpus_ = corpus.CorpusDaSessao(sessao)
    fontes = corpus.fontes_do_resultado(corpus_.buscar("quanto paguei nas alcaparras?"))
    assert fontes is not None
    assert fontes["texto"] == "De onde eu tirei isso"
    assert fontes["chips"][0] == {
        "rotulo": "Alcaparras, na sua despensa",
        "rota": "/despensa/alcaparras",
    }
    de_cozinha = corpus.fontes_do_resultado(corpus_.buscar("como se faz molho bechamel?"))
    assert de_cozinha is not None
    assert any(
        chip["rota"] is None and "Wikipédia" in chip["rotulo"] for chip in de_cozinha["chips"]
    )
    assert corpus.fontes_do_resultado(corpus_.buscar("qual a capital da França?")) is None
