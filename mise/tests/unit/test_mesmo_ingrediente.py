"""O parecido pergunta e a resposta dela fica na receita: "A receita pede canela. É a sua canela em pó?".

O casamento aproximado nunca vira "tem" sozinho, e também não vira compra sem
perguntar: a linha espera ela dizer se é o item dela. O que ela responde (pela
tela, `responder_sobre_a_receita`, ou pela conversa, `avaliar_receita` com o
`receita_id`) fica gravado naquela receita e vale dali em diante.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import receitas_de_teste as rt

from mise.erros import ErroDeUso
from mise.mcp_server import ReceitaEntrada, Sessao
from mise.passos import perguntas_com_opcoes
from mise.receitas_json import guardada_por_slug, respostas_json
from mise.viabilidade import SituacaoDoIngrediente, Veredito, pergunta_do_mesmo_item

URL = "https://www.tudogostoso.com.br/receita/1-arroz-doce-com-canela.html"
PAGINA = rt.pagina(
    "Arroz doce com canela",
    ["1 kg de arroz", "1 colher de sopa de canela", "sal a gosto"],
    ["Cozinhe o arroz na panela por 20 minutos e polvilhe a canela."],
)
LINHA = "1 colher de sopa de canela"


@pytest.fixture
def sessao(tmp_path: Path) -> Sessao:
    sessao = rt.sessao_nova(tmp_path)
    rt.cozinha_confirmada(sessao)
    return sessao


def _canela(sessao: Sessao, slug: str) -> object:
    receita = sessao.catalogo.obter(slug)
    assert receita is not None
    avaliacao = sessao.avaliar(receita.receita)
    (ajuste,) = [a for a in avaliacao.ajustes if a.ingrediente.texto_original == LINHA]
    return avaliacao, ajuste


def test_o_parecido_vira_compra_com_a_decisao_dita(sessao: Sessao) -> None:
    """Na dúvida, não é o dela: vira compra, a decisão é dita, e ela corrige se for."""
    arroz_doce = rt.da_web(sessao, URL, PAGINA)
    avaliacao, ajuste = _canela(sessao, arroz_doce.slug)
    assert ajuste.situacao is SituacaoDoIngrediente.FALTA
    assert ajuste.item is None, "o parecido não é o item dela antes de ela dizer"
    assert ajuste.item_considerado == "Canela em pó"
    assert ajuste.decisao.startswith("Considerei que canela não é a sua canela em pó")
    assert "canela" in [f.nome for f in avaliacao.faltantes], "entra na compra"
    assert not [p for p in perguntas_com_opcoes(avaliacao.perguntas) if p["campo"] == LINHA]
    assert avaliacao.veredito_da_cozinha is not Veredito.FALTA_INFO


def test_sim_pela_tela_usa_o_que_ela_tem_e_fica_lembrado(sessao: Sessao) -> None:
    arroz_doce = rt.da_web(sessao, URL, PAGINA)
    feita = sessao.responder_sobre_a_receita(arroz_doce.slug, LINHA, "É, sim")
    (linha,) = [i for i in feita.receita.ingredientes if i.texto_original == LINHA]
    assert linha.item_da_despensa == "Canela em pó"
    _, ajuste = _canela(sessao, arroz_doce.slug)
    assert ajuste.situacao in (SituacaoDoIngrediente.TEM, SituacaoDoIngrediente.TEM_PARTE)
    assert ajuste.item is not None
    assert ajuste.item.nome == "Canela em pó"
    guardada = guardada_por_slug(sessao, arroz_doce.slug)
    (dito,) = respostas_json(guardada, guardada.atualizada_em or guardada.criada_em)
    assert dito["texto"] == (
        "A senhora disse que “1 colher de sopa de canela” é o que tem na despensa: canela em pó."
    )
    with pytest.raises(ErroDeUso, match="não muda a receita"):
        sessao.responder_sobre_a_receita(arroz_doce.slug, LINHA, "sim")


def test_nao_pela_tela_vira_compra_sem_perguntar_de_novo(sessao: Sessao) -> None:
    arroz_doce = rt.da_web(sessao, URL, PAGINA)
    sessao.responder_sobre_a_receita(arroz_doce.slug, LINHA, "nao")
    avaliacao, ajuste = _canela(sessao, arroz_doce.slug)
    assert ajuste.situacao is SituacaoDoIngrediente.FALTA
    assert ajuste.pergunta is None
    assert "canela" in [f.nome for f in avaliacao.faltantes]
    guardada = guardada_por_slug(sessao, arroz_doce.slug)
    (dito,) = respostas_json(guardada, guardada.atualizada_em or guardada.criada_em)
    assert dito["texto"].endswith("não é o que tem na despensa: entra na compra.")


def test_pela_conversa_com_o_receita_id(sessao: Sessao) -> None:
    """O agente manda a linha com o mesmo texto e o item que ela confirmou."""
    arroz_doce = rt.da_web(sessao, URL, PAGINA)
    resposta = ReceitaEntrada.model_validate(
        {
            "nome": "Arroz doce com canela",
            "ingredientes": [
                {"texto": LINHA, "nome": "canela", "item_da_despensa": "Canela em pó"}
            ],
        }
    )
    receita, _ = sessao.receita_para_avaliar(arroz_doce.slug, resposta)
    (linha,) = [i for i in receita.ingredientes if i.texto_original == LINHA]
    assert linha.item_da_despensa == "Canela em pó"


def test_so_se_confirma_o_item_que_foi_perguntado(sessao: Sessao) -> None:
    """Sem isto, a canela podia virar o bacon dela, e o custo sairia de um item que ela não disse."""
    arroz_doce = rt.da_web(sessao, URL, PAGINA)
    trocada = ReceitaEntrada.model_validate(
        {
            "nome": "Arroz doce com canela",
            "ingredientes": [{"texto": LINHA, "nome": "canela", "item_da_despensa": "Bacon"}],
        }
    )
    with pytest.raises(ErroDeUso, match="só confirmo o item que a conferência perguntou"):
        sessao.receita_para_avaliar(arroz_doce.slug, trocada)
    ditada = ReceitaEntrada.model_validate(
        {
            **rt.ARROZ_COM_FRANGO,
            "ingredientes": [
                {"texto": "1 kg de arroz", "nome": "arroz", "item_da_despensa": "Bacon"}
            ],
        }
    )
    with pytest.raises(ErroDeUso, match="não tem pergunta"):
        sessao.receita_para_avaliar(None, ditada)


def test_numa_receita_de_frango_o_peito_ja_e_o_dela(sessao: Sessao) -> None:
    """ "1 peito cortado em 4 filés" em "Frango com alcaparras": sem pergunta, sem compra."""
    url = "https://www.tudogostoso.com.br/receita/33527-frango-com-alcaparras.html"
    pagina = rt.pagina(
        "Frango com alcaparras",
        ["1 peito cortado em 4 filés", "Suco de 1 limão", "2 colheres (sopa) de alcaparras"],
        ["Tempere o frango e frite na frigideira."],
    )
    frango = rt.da_web(sessao, url, pagina)
    avaliacao = sessao.avaliar(frango.receita)
    (peito,) = [a for a in avaliacao.ajustes if a.ingrediente.nome == "peito"]
    assert peito.item is not None
    assert peito.item.nome == "Peito de frango"
    assert "peito" not in [f.nome for f in avaliacao.faltantes]


@pytest.mark.parametrize(
    ("pedido", "item", "texto"),
    [
        ("alcatra", "Miolo de alcatra", "A receita pede alcatra. É o seu miolo de alcatra?"),
        ("Canela", "Canela em pó", "A receita pede canela. É a sua canela em pó?"),
        ("alcaparra", "Alcaparras", "A receita pede alcaparra. São as suas alcaparras?"),
        ("tahine", "Tahine", "A receita pede tahine. É o item tahine da sua despensa?"),
    ],
)
def test_a_pergunta_fala_como_ela(pedido: str, item: str, texto: str) -> None:
    assert pergunta_do_mesmo_item(pedido, item) == texto


@pytest.mark.parametrize(
    "linha",
    [
        "1/2 xícara de água",
        "1 litro de agua ou até cobrir tudo.",
        "2 xícaras (chá) de água quente",
        # Como está escrito numa página de verdade (era 1,5 litro).
        "1 5 litro de água (para o cozimento)",
    ],
)
def test_agua_da_torneira_nao_se_compra(sessao: Sessao, linha: str) -> None:
    """ "Falta comprar: água" e "quanto custa a água?" não são perguntas de cozinha."""
    url = "https://www.tudogostoso.com.br/receita/2-arroz-soltinho.html"
    pagina = rt.pagina("Arroz soltinho", ["1 kg de arroz", linha], ["Cozinhe na panela."])
    arroz = rt.da_web(sessao, url, pagina)
    avaliacao = sessao.avaliar(arroz.receita)
    (agua,) = [a for a in avaliacao.ajustes if a.ingrediente.texto_original == linha]
    assert agua.situacao is SituacaoDoIngrediente.TEM
    assert agua.da_torneira
    assert avaliacao.faltantes == ()
    assert not [p for p in avaliacao.perguntas if "gua" in p.campo]


def test_agua_de_coco_continua_sendo_compra(sessao: Sessao) -> None:
    url = "https://www.tudogostoso.com.br/receita/3-arroz-com-coco.html"
    pagina = rt.pagina(
        "Arroz com coco", ["1 kg de arroz", "200 ml de água de coco"], ["Cozinhe na panela."]
    )
    arroz = rt.da_web(sessao, url, pagina)
    assert [f.nome for f in sessao.avaliar(arroz.receita).faltantes] == ["água de coco"]
