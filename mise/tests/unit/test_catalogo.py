"""O catálogo de receitas: as regras de id e de imagem, e a leitura que começa vazia."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
from retrieval.extrator import extrair

from mise.catalogo import (
    PREFIXO_DA_IMAGEM,
    TAMANHO_DA_CHAVE_DA_IMAGEM,
    Catalogo,
    OrigemNoCatalogo,
    ReceitaDoCatalogo,
    TemposDaReceita,
    chave_da_imagem,
    foto_generica,
    id_da_receita,
    id_da_url,
    rota_da_imagem,
    url_canonica,
)
from mise.despensa_json import slug_da_receita
from mise.dossie import Dossie
from mise.receita import Receita, ingrediente, receita

FOTO = "https://static.tudogostoso.com.br/fotos/22090-carne-moida-com-arroz.jpg"
ARROZ = ingrediente("1 kg de arroz", "arroz", 1, "kg")


@pytest.mark.parametrize(
    "endereco",
    [
        "https://www.TudoGostoso.com.br/receita/1-arroz/?utm_source=x#topo",
        "http://tudogostoso.com.br/receita/1-arroz",
        "  https://tudogostoso.com.br/receita/1-arroz/  ",
    ],
)
def test_o_mesmo_endereco_de_varios_jeitos_e_a_mesma_receita(endereco: str) -> None:
    assert url_canonica(endereco) == "tudogostoso.com.br/receita/1-arroz"
    esperado = hashlib.sha256(b"tudogostoso.com.br/receita/1-arroz").hexdigest()[:16]
    assert id_da_url(endereco) == esperado


def test_o_id_da_receita_e_o_da_url_ou_o_slug_do_nome() -> None:
    da_web = receita("Arroz", [ARROZ], url="https://www.tudogostoso.com.br/receita/1-arroz/")
    ditada = receita("Arroz com Frango!", [ARROZ])
    assert id_da_receita(da_web) == id_da_url("tudogostoso.com.br/receita/1-arroz")
    assert id_da_receita(ditada) == "arroz-com-frango"
    for r in (da_web, ditada):
        assert slug_da_receita(r) == id_da_receita(r), "a despensa usa a mesma regra"


def test_a_chave_da_foto_e_do_endereco_original() -> None:
    chave = chave_da_imagem(FOTO)
    assert chave == hashlib.sha256(FOTO.encode()).hexdigest()[:TAMANHO_DA_CHAVE_DA_IMAGEM]
    assert len(chave) == 32
    assert chave_da_imagem(f"  {FOTO} ") == chave
    assert chave_da_imagem(FOTO + "?w=640") != chave, "outra foto, outra chave"
    assert rota_da_imagem(FOTO) == f"{PREFIXO_DA_IMAGEM}{chave}" == f"/motor/imagens/{chave}"


def test_a_receita_do_catalogo_mostra_a_foto_so_pela_rota() -> None:
    carne = receita("Carne moída com arroz", [ARROZ], url="https://tudogostoso.com.br/r/2")
    com_foto = ReceitaDoCatalogo(
        slug=id_da_receita(carne),
        receita=carne,
        origem=OrigemNoCatalogo.DESCOBERTA,
        url_canonica=url_canonica("https://tudogostoso.com.br/r/2"),
        site="TudoGostoso",
        imagem_url=FOTO,
        tempos=TemposDaReceita(preparo_min=15, cozimento_min=30, total_min=45),
    )
    assert com_foto.nome == "Carne moída com arroz"
    assert com_foto.rota_da_imagem == rota_da_imagem(FOTO)
    ditada = ReceitaDoCatalogo(
        slug="arroz-com-frango",
        receita=receita("Arroz com frango", [ARROZ]),
        origem=OrigemNoCatalogo.DITA,
    )
    assert ditada.rota_da_imagem is None
    assert ditada.tempos == TemposDaReceita()
    assert [o.value for o in OrigemNoCatalogo] == ["descoberta", "url_dela", "conversa", "dita"]


def test_o_catalogo_comeca_vazio_e_diz_isso_sem_erro(tmp_path: Path) -> None:
    with Dossie(tmp_path / "dossie.db") as dossie:
        catalogo = Catalogo(dossie)
        assert catalogo.listar() == ()
        assert catalogo.listar(q="arroz", origem=OrigemNoCatalogo.DITA, limite=3) == ()
        assert catalogo.obter("arroz-com-frango") is None
        assert catalogo.por_url("https://tudogostoso.com.br/r/2") is None


# --------------------------------------------------------------------------- #
# A escrita: só o servidor, pela página lida ou pela receita que ela dita      #
# --------------------------------------------------------------------------- #

import receitas_de_teste as rt  # noqa: E402

from mise.catalogo import PaginaLida, chave_do_nome  # noqa: E402
from mise.erros import ErroDeUso  # noqa: E402
from mise.receita import Origem  # noqa: E402


def test_a_pagina_lida_entra_com_a_procedencia(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    carne = rt.da_web(sessao, rt.CARNE_URL, rt.CARNE)
    assert carne.slug == id_da_url(rt.CARNE_URL)
    assert (carne.nome, carne.site, carne.autor) == (
        "Carne moída com arroz na panela",
        "TudoGostoso",
        "Leuda",
    )
    assert carne.receita.fonte == "TudoGostoso"
    assert carne.receita.origem is Origem.WEB
    assert carne.url_canonica == "tudogostoso.com.br/receita/22090-carne-moida-com-arroz.html"
    assert carne.tempos == TemposDaReceita(15, 30, 45)
    assert carne.rendimento_texto == "4 porções"
    assert carne.credito_da_imagem == "Foto: TudoGostoso"
    assert carne.rota_da_imagem == rota_da_imagem(rt.FOTO)
    assert carne.da_internet and carne.origem is OrigemNoCatalogo.DESCOBERTA
    assert len(carne.hash_do_conteudo) == 64
    assert carne.criada_em is not None and carne.atualizada_em is not None
    assert sessao.catalogo.obter(carne.slug.upper()) == carne
    assert sessao.catalogo.por_url(rt.CARNE_URL + "?utm=1") == carne
    assert sessao.catalogo.por_nome("CARNE MOIDA com arroz na panela") == carne
    assert sessao.catalogo.contar() == 1
    assert sessao.catalogo.contar(OrigemNoCatalogo.DITA) == 0
    sessao.dossie.fechar()


def test_a_mesma_pagina_de_novo_so_atualiza_se_mudou(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    primeira = rt.da_web(sessao, rt.CARNE_URL, rt.CARNE)
    assert rt.da_web(sessao, rt.CARNE_URL, rt.CARNE, OrigemNoCatalogo.URL_DELA) == primeira
    mudada = rt.CARNE.replace("500 g de carne", "600 g de carne")
    depois = rt.da_web(sessao, rt.CARNE_URL, mudada)
    assert depois.hash_do_conteudo != primeira.hash_do_conteudo
    assert depois.nome == primeira.nome and depois.origem is OrigemNoCatalogo.DESCOBERTA
    assert depois.receita.ingredientes[0].quantidade == 600
    sessao.dossie.fechar()


def test_nome_repetido_ganha_o_site_e_depois_o_numero(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    html = rt.pagina("Bolo de fubá", ["2 xícaras de fubá"], ["Asse no forno."])
    um = rt.da_web(sessao, "https://tudogostoso.com.br/r/1", html)
    dois = rt.da_web(sessao, "https://tudogostoso.com.br/r/2", html)
    tres = rt.da_web(sessao, "https://tudogostoso.com.br/r/3", html)
    sem_site = rt.da_web(
        sessao,
        "https://blog.exemplo.com.br/r/4",
        rt.pagina("Bolo de Fubá", ["1 xícara de fubá"], ["Asse."], site=None),
    )
    assert [um.nome, dois.nome, tres.nome] == [
        "Bolo de fubá",
        "Bolo de fubá (TudoGostoso)",
        "Bolo de fubá (TudoGostoso 2)",
    ]
    assert sem_site.nome == "Bolo de Fubá (blog.exemplo.com.br)"
    assert dois.nome_original == "Bolo de fubá"
    assert [r.nome for r in sessao.catalogo.listar(q="FUBA", limite=2)] == [
        "Bolo de Fubá (blog.exemplo.com.br)",
        "Bolo de fubá (TudoGostoso 2)",
    ]
    assert sessao.catalogo.listar(origem=OrigemNoCatalogo.DITA) == ()
    sessao.dossie.fechar()


def test_o_nome_de_uma_receita_em_avaliacao_nao_e_tomado(tmp_path: Path) -> None:
    """Receita em avaliação de antes do catálogo continua dona do nome dela."""
    sessao = rt.sessao_nova(tmp_path)
    antiga = receita("Carne moída com arroz na panela", [ARROZ])
    sessao.guardar(antiga)
    carne = rt.da_web(sessao, rt.CARNE_URL, rt.CARNE)
    assert carne.nome == "Carne moída com arroz na panela (TudoGostoso)"
    sessao.dossie.fechar()


def test_nomes_demais_e_recusado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import mise.catalogo as modulo

    monkeypatch.setattr(modulo, "_TENTATIVAS_DE_NOME", 2)
    sessao = rt.sessao_nova(tmp_path)
    html = rt.pagina("Pudim", ["3 ovos"], ["Asse."])
    rt.da_web(sessao, "https://tudogostoso.com.br/p/1", html)
    rt.da_web(sessao, "https://tudogostoso.com.br/p/2", html)
    with pytest.raises(ErroDeUso, match="demais"):
        rt.da_web(sessao, "https://tudogostoso.com.br/p/3", html)
    sessao.dossie.fechar()


def test_so_entra_como_da_internet_a_pagina_lida(tmp_path: Path) -> None:
    with Dossie(tmp_path / "dossie.db") as dossie:
        catalogo = Catalogo(dossie)
        ditada = receita("Arroz", [ARROZ])
        with pytest.raises(ErroDeUso, match="página que o servidor leu"):
            catalogo.guardar_da_web(PaginaLida(ditada), OrigemNoCatalogo.CONVERSA)
        da_web = receita("Arroz", [ARROZ], url="https://tudogostoso.com.br/r/1")
        with pytest.raises(ErroDeUso, match="página que o servidor leu"):
            catalogo.guardar_da_web(PaginaLida(da_web), OrigemNoCatalogo.CONVERSA)
        lida = Receita(
            nome="Arroz",
            ingredientes=(ARROZ,),
            url="https://tudogostoso.com.br/r/1",
            origem=Origem.WEB,
        )
        with pytest.raises(ErroDeUso, match="ditada"):
            catalogo.guardar_da_web(PaginaLida(lida), OrigemNoCatalogo.DITA)
        with pytest.raises(ErroDeUso, match="endereço"):
            catalogo.guardar_dita(lida)


def test_a_receita_que_ela_dita_e_corrigida_pelo_mesmo_nome(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    primeira = rt.ditada(sessao, **rt.ARROZ_COM_FRANGO)
    assert (primeira.slug, primeira.origem) == ("arroz-com-frango", OrigemNoCatalogo.DITA)
    assert not primeira.da_internet
    assert primeira.site is None and primeira.imagem_url is None
    corrigida = rt.ditada(sessao, **{**rt.ARROZ_COM_FRANGO, "rendimento_porcoes": 6})
    assert corrigida.slug == primeira.slug
    assert corrigida.receita.rendimento_porcoes == 6
    assert sessao.catalogo.contar(OrigemNoCatalogo.DITA) == 1
    sessao.dossie.fechar()


def test_ditada_com_o_nome_de_uma_da_internet_e_recusada_com_o_id(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    carne = rt.da_web(sessao, rt.CARNE_URL, rt.CARNE)
    with pytest.raises(ErroDeUso, match="receita_id dela") as erro:
        sessao.catalogo.guardar_dita(receita("carne moída com arroz na panela", [ARROZ]))
    assert erro.value.contexto["receita_id"] == carne.slug
    assert "de TudoGostoso" in erro.value.mensagem
    sem_site = rt.da_web(
        sessao,
        "https://blog.exemplo.com.br/x",
        rt.pagina("Pão de queijo", ["1 xícara de polvilho"], ["Asse."], site=None),
    )
    assert sem_site.site == "blog.exemplo.com.br"
    sessao.dossie.fechar()


def test_ditada_com_o_nome_de_uma_em_avaliacao_e_recusada(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    sessao.guardar(receita("Pudim", [ARROZ], url="https://exemplo.com.br/pudim"))
    with pytest.raises(ErroDeUso, match="outra receita em avaliação"):
        sessao.catalogo.guardar_dita(receita("Pudim", [ARROZ]))
    sessao.dossie.fechar()


def test_completar_grava_o_que_ela_respondeu(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    carne = rt.da_web(sessao, rt.CARNE_URL, rt.CARNE)
    nova = replace(carne.receita, nome="outro nome", rendimento_porcoes=6)
    completa = sessao.catalogo.completar(carne.slug, nova, [("rendimento_porcoes", "6 porções")])
    assert completa.nome == carne.nome, "o nome do catálogo não muda"
    assert completa.receita.rendimento_porcoes == 6
    (resposta,) = completa.respostas
    assert (resposta.campo, resposta.valor) == ("rendimento_porcoes", "6 porções")
    with pytest.raises(ErroDeUso, match="não encontrei"):
        sessao.catalogo.completar("nao-existe", nova, [])
    sessao.dossie.fechar()


def test_chave_do_nome_sem_caixa_nem_acento() -> None:
    assert chave_do_nome("  Bolo de   FUBÁ ") == "bolo de fuba"


# --------------------------------------------------------------------------- #
# A descoberta marca o que trouxe, e as fotos que o proxy pode servir          #
# --------------------------------------------------------------------------- #


def test_a_descoberta_marca_so_o_que_entrou_depois_do_comeco(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    antes = rt.da_web(sessao, rt.CARNE_URL, rt.CARNE, OrigemNoCatalogo.CONVERSA)
    comeco = sessao.dossie.agora()
    depois = rt.da_web(sessao, rt.MILHO_URL, rt.MILHO, OrigemNoCatalogo.CONVERSA)
    marcada = sessao.catalogo.marcar_como_descoberta(depois.slug, comeco)
    assert marcada is not None and marcada.origem is OrigemNoCatalogo.DESCOBERTA
    guardada = sessao.catalogo.obter(depois.slug)
    assert guardada is not None and guardada.origem is OrigemNoCatalogo.DESCOBERTA
    assert sessao.catalogo.marcar_como_descoberta(depois.slug, comeco) == guardada
    assert sessao.catalogo.marcar_como_descoberta(antes.slug, comeco) is None, "já estava lá"
    velha = sessao.catalogo.obter(antes.slug)
    assert velha is not None and velha.origem is OrigemNoCatalogo.CONVERSA
    assert sessao.catalogo.marcar_como_descoberta("0" * 16, comeco) is None


def test_a_descoberta_nao_toma_a_receita_que_ela_trouxe(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    comeco = sessao.dossie.agora()
    dela = rt.da_web(sessao, rt.CARNE_URL, rt.CARNE, OrigemNoCatalogo.URL_DELA)
    assert sessao.catalogo.marcar_como_descoberta(dela.slug, comeco) is None
    guardada = sessao.catalogo.obter(dela.slug)
    assert guardada is not None and guardada.origem is OrigemNoCatalogo.URL_DELA


def test_as_fotos_do_catalogo_sao_as_que_as_paginas_declararam(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    assert sessao.catalogo.fotos() == ()
    carne = rt.da_web(sessao, rt.CARNE_URL, rt.CARNE)
    rt.ditada(sessao, **rt.ARROZ_COM_FRANGO)
    (foto,) = sessao.catalogo.fotos()
    assert (foto.imagem_url, foto.credito, foto.pagina) == (
        rt.FOTO,
        "Foto: TudoGostoso",
        rt.CARNE_URL,
    )
    assert foto.chave == chave_da_imagem(rt.FOTO) == carne.rota_da_imagem.rsplit("/", 1)[1]


GENERICA = "https://static.itdg.com.br/images/1200-675/default/placeholder-img-default-tdg.png"


@pytest.mark.parametrize(
    ("endereco", "generica"),
    [
        (GENERICA, True),
        ("https://site.com.br/img/sem-foto.png", True),
        ("https://site.com.br/assets/NO-IMAGE.jpg", True),
        ("https://placeholder.site.com.br/fotos/bolo.jpg", False),
        (FOTO, False),
        ("http://[::1", True),
    ],
)
def test_a_foto_generica_do_site_se_reconhece_pelo_caminho(endereco: str, generica: bool) -> None:
    """Só o caminho conta: um site chamado "placeholder" ainda pode ter a foto do prato."""
    assert foto_generica(endereco) is generica


def test_a_foto_generica_nao_chega_a_tela(tmp_path: Path) -> None:
    """A receita que declarou o chapéu cinza fica sem foto, e o proxy nem a registra."""
    sessao = rt.sessao_nova(tmp_path)
    lida = extrair(rt.pagina("Carne", ["500 g de carne"], ["Frite."]), rt.CARNE_URL)
    pagina = PaginaLida(receita=lida.receita, site="TudoGostoso", imagem_url=GENERICA)
    carne, nova = sessao.catalogo.guardar_da_web(pagina, OrigemNoCatalogo.DESCOBERTA)
    assert nova
    assert (carne.imagem_url, carne.credito_da_imagem) == (None, None)
    antiga = replace(carne, imagem_url=GENERICA)
    assert antiga.rota_da_imagem is None


def test_esquecer_a_foto_tira_de_todas_as_receitas_que_a_declararam(tmp_path: Path) -> None:
    """O proxy baixou a foto e ela é a genérica: o catálogo esquece, e a tela mostra o gradiente."""
    sessao = rt.sessao_nova(tmp_path)
    carne = rt.da_web(sessao, rt.CARNE_URL, rt.CARNE)
    assert carne.imagem_url == rt.FOTO
    assert sessao.catalogo.esquecer_foto(rt.FOTO) == 1
    guardada = sessao.catalogo.obter(carne.slug)
    assert guardada is not None
    assert (guardada.imagem_url, guardada.credito_da_imagem, guardada.rota_da_imagem) == (
        None,
        None,
        None,
    )
    assert sessao.catalogo.fotos() == ()
    assert sessao.catalogo.esquecer_foto(rt.FOTO) == 0
