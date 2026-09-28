"""A descoberta de receitas de ponta a ponta, contra um Hermes falso.

O que estes testes protegem, na ordem em que doeria:

1. Receita só entra no catálogo pela página que o servidor leu: o que o modelo
   escreve, ou um id que ele cita, não vira receita nem conta como encontrada.
2. A chave de desligar: desligada, nada chega ao Hermes (cada rodada custa).
3. Uma rodada por vez; a conversa em andamento e o Hermes cheio fazem esperar.
4. O progresso sai do catálogo e dos eventos do run, com a forma do contrato
   (`contratos/web/receitas-descoberta.jsonl`), e os erros chegam em português.
5. Os limites (8 pesquisas, 20 páginas, cerca de 16 minutos) param o run de verdade,
   e são os mesmos da pauta que o pedido fixo repete.
6. Só entra receita em português, lida da página de verdade: a página em outra
   língua é buscada, recusada pelo servidor, e a rodada segue.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import retrieval.busca
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hermes_falso import Esperar, Evento, Fazer, HermesFalso, Quebrar, RoteiroDeRun, turno
from mise import descoberta as pauta
from mise.catalogo import OrigemNoCatalogo, id_da_url
from mise.erros import ErroDeDados
from mise.mcp_server import Sessao
from retrieval.extrator import extrair

from gateway import descoberta as d
from gateway.conversa import Pedido, ServicoDeConversa
from gateway.descoberta import Configuracao, ServicoDeDescoberta
from gateway.http import criar_app

RAIZ = Path(__file__).resolve().parents[2]
PLANILHA = RAIZ / "dados" / "despensa_dona_maria.xlsx"
PROMPT = RAIZ / "hermes" / "prompts" / "descoberta.md"
CONTRATO = RAIZ / "contratos" / "web" / "receitas-descoberta.jsonl"
ORIGEM = "http://localhost:3000"

RAPIDA = Configuracao(
    ligada=True,
    keepalive_s=0.05,
    intervalo_da_espera_s=0.01,
    espera_da_conversa_s=2.0,
    espera_se_ocupada_s=0.0,
    intervalo_do_estado_s=0.01,
    duracao_maxima_s=10.0,
    prompt=PROMPT,
)

FOTO = "https://static.tudogostoso.com.br/fotos/alcaparras.jpg"
FRANGO_URL = "https://www.tudogostoso.com.br/receita/77-frango-com-alcaparras.html"
CARNE_URL = "https://www.panelinha.com.br/receita/carne-moida-com-batata"
SEM_RECEITA_URL = "https://www.exemplo.com.br/blog/dicas-de-cozinha"
EM_INGLES_URL = "https://www.allrecipes.com/recipe/2024/brazilian-farofa"


def _pagina(nome: str, ingredientes: list[str], passos: list[str], site: str) -> str:
    objeto = {
        "@type": "Recipe",
        "name": nome,
        "recipeYield": "4 porções",
        "recipeIngredient": ingredientes,
        "recipeInstructions": passos,
        "publisher": {"@type": "Organization", "name": site},
        "image": FOTO,
        "prepTime": "PT10M",
        "cookTime": "PT30M",
    }
    return f'<script type="application/ld+json">{json.dumps(objeto)}</script>'


PAGINAS = {
    FRANGO_URL: _pagina(
        "Frango com alcaparras",
        ["500 g de peito de frango", "2 colheres de sopa de alcaparras", "1 cebola", "sal a gosto"],
        ["Refogue a cebola.", "Junte o frango e cozinhe por 25 minutos na panela."],
        "TudoGostoso",
    ),
    CARNE_URL: _pagina(
        "Carne moída com batata",
        ["500 g de carne moída", "3 batatas", "1 cebola", "sal a gosto"],
        ["Refogue a cebola.", "Junte a carne e a batata e cozinhe por 30 minutos na panela."],
        "Panelinha",
    ),
    SEM_RECEITA_URL: "<html><body><p>Dicas de cozinha, sem receita.</p></body></html>",
    # Receita estruturada de verdade, mas em inglês: o servidor recusa pela língua.
    EM_INGLES_URL: '<html lang="en-US">'
    + _pagina(
        "Brazilian farofa",
        ["2 cups manioc flour", "4 tablespoons butter", "1 onion", "salt to taste"],
        ["Melt the butter.", "Add the flour and toast for 5 minutes."],
        "Allrecipes",
    )
    + "</html>",
}


# --------------------------------------------------------------------------- #
# Montagem                                                                     #
# --------------------------------------------------------------------------- #


@pytest.fixture
def hermes() -> HermesFalso:
    return HermesFalso()


@pytest.fixture
def paginas(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """As páginas "da internet", sem rede: o extrator de verdade sobre o HTML daqui."""
    buscadas: list[str] = []

    def buscar(url: str, fonte: str = "", **_: Any) -> Any:
        buscadas.append(url)
        if url not in PAGINAS:
            raise retrieval.busca.BuscaFalhou("sem rede no teste")
        return extrair(PAGINAS[url], url, fonte)

    monkeypatch.setattr(retrieval.busca, "buscar_receita", buscar)
    return buscadas


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, hermes: HermesFalso) -> FastAPI:
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "estado" / "dossie.db"))
    for variavel in ("MISE_AUDITORIA", "MISE_CONVERSAS", "MISE_AUDITOR_URL", "MISE_FUSO"):
        monkeypatch.delenv(variavel, raising=False)
    app = criar_app()
    conversa: ServicoDeConversa = app.state.conversa
    conversa.fabrica_do_cliente = hermes.cliente
    app.state.descoberta = ServicoDeDescoberta(
        app.state.sessao, conversa=conversa, configuracao=RAPIDA
    )
    return app


@pytest.fixture
def servico(app: FastAPI) -> ServicoDeDescoberta:
    servico: ServicoDeDescoberta = app.state.descoberta
    return servico


@pytest.fixture
def sessao(app: FastAPI) -> Sessao:
    sessao: Sessao = app.state.sessao
    return sessao


@pytest.fixture
async def api(app: FastAPI, servico: ServicoDeDescoberta) -> AsyncIterator[httpx.AsyncClient]:
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://127.0.0.1:8777") as cliente:
        yield cliente
    await servico.fechar()
    await app.state.conversa.fechar()


def ler_sse(corpo: str) -> list[dict[str, Any]]:
    eventos = []
    for bloco in corpo.split("\n\n"):
        linhas = [linha for linha in bloco.splitlines() if not linha.startswith(":")]
        if not linhas:
            continue
        campos = dict(linha.split(": ", 1) for linha in linhas)
        assert "event" not in campos
        evento = json.loads(campos["data"])
        assert int(campos["id"]) == evento["seq"]
        eventos.append(evento)
    return eventos


async def descobrir(api: httpx.AsyncClient) -> httpx.Response:
    return await api.post("/api/receitas/descoberta", headers={"Origin": ORIGEM})


async def eventos(api: httpx.AsyncClient, **params: Any) -> list[dict[str, Any]]:
    resposta = await api.get("/api/receitas/descoberta/eventos", params=params)
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"].startswith("text/event-stream")
    assert resposta.headers["cache-control"] == "no-cache, no-transform"
    return ler_sse(resposta.text)


def de_tipo(lista: list[dict[str, Any]], tipo: str) -> list[dict[str, Any]]:
    return [e for e in lista if e["tipo"] == tipo]


# --------------------------------------------------------------------------- #
# O roteiro de um run: o que o Hermes publica                                  #
# --------------------------------------------------------------------------- #


def _saida_da_ferramenta(dados: dict[str, Any]) -> str:
    """Como o Hermes embrulha a saída de uma ferramenta MCP (`{"result": "<texto>"}`)."""
    texto = json.dumps(dados, ensure_ascii=False, indent=2)
    return json.dumps({"result": texto}, ensure_ascii=False)


def ferramenta(nome: str, preview: str | None, saida: str = "") -> list[Evento]:
    return [
        Evento("tool.started", {"tool": nome, "preview": preview}),
        Evento(
            "tool.completed",
            {"tool": nome, "duration": 0.2, "error": False, "preview": saida[:500]},
        ),
    ]


def ler_pagina(sessao: Sessao, url: str) -> list[Any]:
    """`buscar_receita_na_web` rodando no servidor MCP: a página entra pelo servidor."""
    saida: dict[str, Any] = {}

    def rodar() -> None:
        try:
            saida.update(sessao.receita_da_web(url))
        except Exception as erro:  # o servidor MCP devolve o erro como texto
            saida.update({"erro": str(erro), "categoria": "dado"})

    nome = "mcp__mise__buscar_receita_na_web"
    return [
        Evento("tool.started", {"tool": nome, "preview": url}),
        Fazer(rodar),
        Evento(
            "tool.completed",
            {
                "tool": nome,
                "duration": 0.2,
                "error": False,
                "preview": lambda: _saida_da_ferramenta(saida)[:500],
            },
        ),
    ]


def mensagem_da_ferramenta(dados: dict[str, Any]) -> dict[str, Any]:
    texto = json.dumps(dados, ensure_ascii=False, indent=2)
    return {
        "role": "tool",
        "tool_name": "mcp__mise__buscar_receita_na_web",
        "content": f"<untrusted_tool_output>\n{texto}\n</untrusted_tool_output>",
    }


def inicio_do_run() -> list[Evento]:
    pauta = _saida_da_ferramenta({"disponivel": True, "buscas": ["receita com alcaparras"]})
    return [
        *ferramenta("mcp__mise__pauta_de_descoberta", None, pauta),
        *ferramenta("web_search", "receita com alcaparras", '{"result": "[...]"}'),
    ]


def fim_do_run(status: str = "completed", **campos: Any) -> list[Evento]:
    return [Evento(f"run.{status}", {"output": "pronto", **campos})]


# --------------------------------------------------------------------------- #
# A chave de desligar                                                          #
# --------------------------------------------------------------------------- #


def test_desligada_sem_a_variavel_e_ligada_so_com_ligada() -> None:
    assert d.ligada_no_ambiente({}) is False
    assert d.ligada_no_ambiente({"SABOR_DESCOBERTA": "desligada"}) is False
    assert d.ligada_no_ambiente({"SABOR_DESCOBERTA": "talvez"}) is False
    assert d.ligada_no_ambiente({"SABOR_DESCOBERTA": " Ligada "}) is True
    assert Configuracao.do_ambiente({}).ligada is False
    assert Configuracao.do_ambiente({"SABOR_DESCOBERTA": "ligada"}).ligada is True
    assert Configuracao.do_ambiente({"SABOR_PROMPT_DESCOBERTA": "/tmp/p.md"}).prompt == Path(
        "/tmp/p.md"
    )


def test_nos_testes_a_descoberta_esta_desligada(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """O conftest desliga: o app montado do ambiente nunca chega ao Hermes."""
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "dossie.db"))
    app = criar_app()
    with TestClient(app) as cliente:
        resposta = cliente.post("/api/receitas/descoberta")
    corpo = resposta.json()
    assert resposta.status_code == 501, "a tela abre a conversa com o pedido escrito"
    assert (corpo["ok"], corpo["categoria"], corpo["erro"]) == (False, "regra", d.DESLIGADA_AQUI)
    assert corpo["dados"]["estado"] == "parada"


async def test_desligada_recusa_sem_falar_com_o_hermes(
    api: httpx.AsyncClient, servico: ServicoDeDescoberta, hermes: HermesFalso
) -> None:
    servico.configuracao = Configuracao(ligada=False, prompt=PROMPT)
    resposta = await descobrir(api)
    assert resposta.status_code == 501
    corpo = resposta.json()
    assert (corpo["ok"], corpo["categoria"]) == (False, "regra")
    assert "desligada" in corpo["erro"]
    assert hermes.pedidos == []
    assert servico.estado() is None


# --------------------------------------------------------------------------- #
# O caminho feliz                                                              #
# --------------------------------------------------------------------------- #


async def test_a_descoberta_traz_receitas_pelo_servidor(
    api: httpx.AsyncClient,
    servico: ServicoDeDescoberta,
    sessao: Sessao,
    hermes: HermesFalso,
    paginas: list[str],
) -> None:
    hermes.runs.append(
        RoteiroDeRun(
            [
                *inicio_do_run(),
                *ler_pagina(sessao, FRANGO_URL),
                *ler_pagina(sessao, SEM_RECEITA_URL),
                *ler_pagina(sessao, CARNE_URL),
                *ler_pagina(sessao, FRANGO_URL),  # a mesma página de novo: já conhecida
                *fim_do_run(),
            ]
        )
    )
    resposta = await descobrir(api)
    assert resposta.status_code == 202, resposta.text
    inicio = resposta.json()["dados"]
    assert set(inicio) == {"execucao_id", "estado", "texto", "eventos"}
    assert inicio["estado"] == "procurando"
    assert inicio["eventos"] == f"/api/receitas/descoberta/eventos?execucao={inicio['execucao_id']}"
    await servico.esperar()

    # O pedido ao Hermes: sessão nova, instruções fixas, raciocínio baixo, idempotente.
    assert len(hermes.sessoes_criadas) == 1
    (pedido,) = hermes.runs_pedidos
    assert pedido["session_id"] == hermes.sessoes_criadas[0]
    assert pedido["instructions"] == PROMPT.read_text(encoding="utf-8").strip()
    assert pedido["input"] == d.ENTRADA
    assert pedido["model_options"] == {"reasoning": {"effort": "low"}}
    assert pedido["idempotency_key"] == inicio["execucao_id"]

    # O servidor leu cada página uma vez; a repetida voltou do catálogo.
    assert paginas == [FRANGO_URL, SEM_RECEITA_URL, CARNE_URL]
    frango = sessao.catalogo.por_url(FRANGO_URL)
    carne = sessao.catalogo.por_url(CARNE_URL)
    assert frango is not None and carne is not None
    assert frango.origem is carne.origem is OrigemNoCatalogo.DESCOBERTA
    assert sessao.catalogo.contar() == 2

    lista = await eventos(api, execucao=inicio["execucao_id"])
    encontradas = de_tipo(lista, "receita.encontrada")
    assert [e["receita"]["slug"] for e in encontradas] == [frango.slug, carne.slug]
    for evento in encontradas:
        assert evento["aba"] in {"pode_fazer", "falta_resposta"}
        assert evento["receita"]["imagem"]["url"].startswith("/motor/imagens/")
    (fim,) = de_tipo(lista, "fim")
    assert fim == {
        "seq": fim["seq"],
        "tipo": "fim",
        "estado": "parada",
        "lidas": 3,
        "encontradas": 2,
        "texto": "Encontrei 2 receitas novas.",
    }
    textos = [e["texto"] for e in de_tipo(lista, "progresso")]
    assert d.SEPARANDO in textos
    assert "Procurando na internet: receita com alcaparras…" in textos
    assert "Lendo uma receita de tudogostoso.com.br…" in textos

    # A grade mostra a rodada, e ler a grade não começa outra.
    grade = (await api.get("/api/receitas")).json()["dados"]
    assert grade["descoberta"] == {
        "estado": "parada",
        "lidas": 3,
        "encontradas": 2,
        "texto": "Encontrei 2 receitas novas.",
    }
    assert len(hermes.runs_pedidos) == 1


async def test_pagina_em_outra_lingua_nao_entra_e_a_rodada_segue(
    api: httpx.AsyncClient,
    servico: ServicoDeDescoberta,
    sessao: Sessao,
    hermes: HermesFalso,
    paginas: list[str],
) -> None:
    """Receita estruturada em inglês é buscada de verdade e recusada pelo servidor.

    A lista de compras sairia falsa ("2 cups manioc flour" não casa com a farinha
    de mandioca dela). A página conta como lida, não entra no catálogo, e a
    rodada segue para a próxima.
    """
    hermes.runs.append(
        RoteiroDeRun(
            [
                *inicio_do_run(),
                *ler_pagina(sessao, EM_INGLES_URL),
                *ler_pagina(sessao, FRANGO_URL),
                *fim_do_run(),
            ]
        )
    )
    await descobrir(api)
    await servico.esperar()
    assert paginas == [EM_INGLES_URL, FRANGO_URL]
    assert sessao.catalogo.por_url(EM_INGLES_URL) is None
    assert sessao.catalogo.contar() == 1
    assert servico.estado() == {
        "estado": "parada",
        "lidas": 2,
        "encontradas": 1,
        "texto": "Encontrei 1 receita nova.",
    }
    with pytest.raises(ErroDeDados, match="outra língua"):
        sessao.receita_da_web(EM_INGLES_URL)


async def test_os_eventos_tem_a_forma_do_contrato(
    api: httpx.AsyncClient,
    servico: ServicoDeDescoberta,
    sessao: Sessao,
    hermes: HermesFalso,
    paginas: list[str],
) -> None:
    hermes.runs.append(
        RoteiroDeRun([*inicio_do_run(), *ler_pagina(sessao, FRANGO_URL), *fim_do_run()])
    )
    await descobrir(api)
    await servico.esperar()
    contrato = [json.loads(linha) for linha in CONTRATO.read_text(encoding="utf-8").splitlines()]
    formas = {e["tipo"]: set(e) for e in contrato}
    lista = await eventos(api)
    assert {e["tipo"] for e in lista} == set(formas)
    for evento in lista:
        assert set(evento) == formas[evento["tipo"]], evento["tipo"]
    assert [e["seq"] for e in lista] == list(range(1, len(lista) + 1))
    item_do_contrato = de_tipo(contrato, "receita.encontrada")[0]["receita"]
    assert set(de_tipo(lista, "receita.encontrada")[0]["receita"]) == set(item_do_contrato)


async def test_os_eventos_retomam_e_param_no_fim(
    api: httpx.AsyncClient,
    servico: ServicoDeDescoberta,
    sessao: Sessao,
    hermes: HermesFalso,
    paginas: list[str],
) -> None:
    antes = await api.get("/api/receitas/descoberta/eventos")
    assert antes.status_code == 204, "sem rodada nenhuma, nada a mandar"
    hermes.runs.append(RoteiroDeRun([*inicio_do_run(), *fim_do_run()]))
    inicio = (await descobrir(api)).json()["dados"]
    await servico.esperar()
    todos = await eventos(api)
    ultimo = todos[-1]["seq"]
    assert todos[-1]["tipo"] == "fim"
    assert [e["seq"] for e in await eventos(api, desde=ultimo - 1)] == [ultimo]
    parado = await api.get("/api/receitas/descoberta/eventos", params={"desde": ultimo})
    assert parado.status_code == 204
    retomado = await api.get(
        "/api/receitas/descoberta/eventos", headers={"Last-Event-ID": str(ultimo)}
    )
    assert retomado.status_code == 204
    outra = await api.get("/api/receitas/descoberta/eventos", params={"execucao": "dx-00000000"})
    assert outra.status_code == 404
    assert outra.json()["categoria"] == "ausente"
    assert (await eventos(api, execucao=inicio["execucao_id"]))[-1]["tipo"] == "fim"


async def test_o_fluxo_ao_vivo_manda_keepalive_ate_o_fim(
    api: httpx.AsyncClient, servico: ServicoDeDescoberta, hermes: HermesFalso
) -> None:
    segura = asyncio.Event()
    hermes.runs.append(RoteiroDeRun([*inicio_do_run(), Esperar(segura), *fim_do_run()]))
    await descobrir(api)

    async def ouvir() -> str:
        resposta = await api.get("/api/receitas/descoberta/eventos")
        return resposta.text

    ouvinte = asyncio.create_task(ouvir())
    await asyncio.sleep(0.2)
    assert not ouvinte.done()
    segura.set()
    corpo = await asyncio.wait_for(ouvinte, 5)
    assert ": keepalive" in corpo
    assert ler_sse(corpo)[-1]["tipo"] == "fim"


# --------------------------------------------------------------------------- #
# O modelo nunca escreve no catálogo                                           #
# --------------------------------------------------------------------------- #


async def test_o_modelo_nunca_escreve_no_catalogo(
    api: httpx.AsyncClient,
    servico: ServicoDeDescoberta,
    sessao: Sessao,
    hermes: HermesFalso,
    paginas: list[str],
) -> None:
    """Receita escrita no texto, id inventado e receita de antes não viram descoberta."""
    trazida = sessao.receita_da_web(CARNE_URL, origem=OrigemNoCatalogo.URL_DELA)
    antes = sessao.catalogo.contar()
    inventada = "https://www.tudogostoso.com.br/receita/999-bolo-que-nao-existe.html"
    receita_no_texto = json.dumps(
        {"receita_id": id_da_url(inventada), "ja_conhecida": False, "nome": "Bolo de alcaparras"}
    )
    hermes.runs.append(
        RoteiroDeRun(
            [
                *inicio_do_run(),
                # A leitura "diz" que trouxe uma receita que o servidor nunca leu.
                *ferramenta(
                    "mcp__mise__buscar_receita_na_web",
                    inventada,
                    _saida_da_ferramenta(
                        {"receita_id": id_da_url(inventada), "ja_conhecida": False}
                    ),
                ),
                # E cita o id da receita que ela mesma trouxe antes da rodada.
                *ferramenta(
                    "mcp__mise__buscar_receita_na_web",
                    CARNE_URL,
                    _saida_da_ferramenta(
                        {"receita_id": trazida["receita_id"], "ja_conhecida": False}
                    ),
                ),
                Evento("message.delta", {"delta": receita_no_texto}),
                *fim_do_run(output=receita_no_texto),
            ],
            mensagens=[
                {"role": "assistant", "content": receita_no_texto},
                mensagem_da_ferramenta({"receita_id": id_da_url(inventada), "ja_conhecida": False}),
            ],
        )
    )
    await descobrir(api)
    await servico.esperar()
    assert sessao.catalogo.contar() == antes
    assert sessao.catalogo.obter(id_da_url(inventada)) is None
    carne = sessao.catalogo.obter(trazida["receita_id"])
    assert carne is not None and carne.origem is OrigemNoCatalogo.URL_DELA
    lista = await eventos(api)
    assert de_tipo(lista, "receita.encontrada") == []
    assert de_tipo(lista, "fim")[0]["encontradas"] == 0
    assert paginas == [CARNE_URL], "só a leitura que ela pediu foi ao site"


# --------------------------------------------------------------------------- #
# Uma por vez, e a espera                                                      #
# --------------------------------------------------------------------------- #


async def test_uma_rodada_por_vez(
    api: httpx.AsyncClient, servico: ServicoDeDescoberta, hermes: HermesFalso
) -> None:
    segura = asyncio.Event()
    hermes.runs.append(RoteiroDeRun([*inicio_do_run(), Esperar(segura), *fim_do_run()]))
    primeira = await descobrir(api)
    assert primeira.status_code == 202
    segunda = await descobrir(api)
    assert segunda.status_code == 409
    corpo = segunda.json()
    assert (corpo["ok"], corpo["categoria"], corpo["erro"]) == (False, "ocupado", d.JA_PROCURANDO)
    assert corpo["dados"]["execucao_id"] == primeira.json()["dados"]["execucao_id"]
    assert corpo["dados"]["estado"] == "procurando"
    grade = (await api.get("/api/receitas")).json()["dados"]
    assert grade["descoberta"]["estado"] == "procurando"
    segura.set()
    await servico.esperar()
    assert len(hermes.runs_pedidos) == 1


async def test_espera_a_conversa_terminar_e_tenta_de_novo(
    api: httpx.AsyncClient,
    servico: ServicoDeDescoberta,
    hermes: HermesFalso,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ocupada = {"agora": True}
    monkeypatch.setattr(ServicoDeConversa, "ocupada", property(lambda _self: ocupada["agora"]))
    hermes.runs.append(RoteiroDeRun([*inicio_do_run(), *fim_do_run()]))
    resposta = await descobrir(api)
    assert resposta.status_code == 202
    assert resposta.json()["dados"]["texto"] == d.ESPERANDO_A_CONVERSA
    await asyncio.sleep(0.1)
    assert hermes.runs_pedidos == [], "com a conversa no meio, o run espera"
    ocupada["agora"] = False
    await servico.esperar()
    assert len(hermes.runs_pedidos) == 1
    lista = await eventos(api)
    assert lista[0]["etapa"] == "esperando"
    assert lista[-1]["estado"] == "parada"


async def test_a_conversa_que_nao_termina_desiste_sem_gastar(
    api: httpx.AsyncClient,
    servico: ServicoDeDescoberta,
    hermes: HermesFalso,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ServicoDeConversa, "ocupada", property(lambda _self: True))
    servico.configuracao = Configuracao(
        ligada=True, espera_da_conversa_s=0.05, intervalo_da_espera_s=0.01, prompt=PROMPT
    )
    await descobrir(api)
    await servico.esperar()
    assert hermes.runs_pedidos == []
    assert servico.estado() == {
        "estado": "parada",
        "lidas": 0,
        "encontradas": 0,
        "texto": d.CONVERSA_NAO_TERMINOU,
    }


async def test_a_conversa_ocupada_e_um_turno_em_andamento(
    app: FastAPI, hermes: HermesFalso
) -> None:
    """`ocupada` é o turno de verdade, em qualquer conversa."""
    conversa: ServicoDeConversa = app.state.conversa
    segura = asyncio.Event()
    hermes.roteiros.append(turno(["Oi!"], antes=[Esperar(segura)]))
    assert conversa.ocupada is False
    conversa_id = conversa.criar()["id"]
    turno_id = await conversa.iniciar_turno(conversa_id, Pedido("Oi", "u-1"))
    assert conversa.ocupada is True
    segura.set()
    await conversa.esperar(turno_id)
    assert conversa.ocupada is False
    await conversa.fechar()


async def test_hermes_cheio_tenta_de_novo_daqui_a_pouco(
    api: httpx.AsyncClient, servico: ServicoDeDescoberta, hermes: HermesFalso
) -> None:
    hermes.ocupada_por = 1
    hermes.runs.append(RoteiroDeRun([*inicio_do_run(), *fim_do_run()]))
    await descobrir(api)
    await servico.esperar()
    assert len(hermes.runs_pedidos) == 1
    lista = await eventos(api)
    assert d.ESPERANDO_A_CONSULTORA in [e.get("texto") for e in lista]
    assert lista[-1]["estado"] == "parada"


async def test_hermes_cheio_demais_desiste_em_portugues(
    api: httpx.AsyncClient, servico: ServicoDeDescoberta, hermes: HermesFalso
) -> None:
    hermes.ocupada_por = 10
    await descobrir(api)
    await servico.esperar()
    fim = (await eventos(api))[-1]
    assert (fim["tipo"], fim["estado"]) == ("fim", "erro")
    assert fim["texto"] == f"{d.CONTINUOU_OCUPADA} {d.TENTE_DE_NOVO}"
    assert hermes.ocupada_por == 10 - RAPIDA.tentativas_se_ocupada


# --------------------------------------------------------------------------- #
# Erros na língua dela                                                         #
# --------------------------------------------------------------------------- #


async def test_consultora_fora_do_ar(
    api: httpx.AsyncClient, servico: ServicoDeDescoberta, hermes: HermesFalso
) -> None:
    hermes.fora_do_ar = True
    resposta = await descobrir(api)
    assert resposta.status_code == 202
    await servico.esperar()
    assert servico.estado() == {
        "estado": "erro",
        "lidas": 0,
        "encontradas": 0,
        "texto": f"{d.FORA_DO_AR} {d.TENTE_DE_NOVO}",
    }
    grade = (await api.get("/api/receitas")).json()["dados"]
    assert grade["descoberta"]["estado"] == "erro"


async def test_run_que_falha_diz_o_que_ja_ficou_na_lista(
    api: httpx.AsyncClient,
    servico: ServicoDeDescoberta,
    sessao: Sessao,
    hermes: HermesFalso,
    paginas: list[str],
) -> None:
    hermes.runs.append(
        RoteiroDeRun(
            [
                *inicio_do_run(),
                *ler_pagina(sessao, FRANGO_URL),
                *fim_do_run("failed", error="Provider returned HTTP 500: internal error"),
            ]
        )
    )
    await descobrir(api)
    await servico.esperar()
    fim = (await eventos(api))[-1]
    assert fim["estado"] == "erro"
    assert fim["texto"] == f"{d.PROBLEMA} A receita nova que eu trouxe já está na lista."
    assert "HTTP" not in fim["texto"] and "Provider" not in fim["texto"]


async def test_gateway_reiniciado_no_meio(
    api: httpx.AsyncClient, servico: ServicoDeDescoberta, hermes: HermesFalso
) -> None:
    hermes.runs.append(RoteiroDeRun([*inicio_do_run(), *fim_do_run("interrupted")]))
    await descobrir(api)
    await servico.esperar()
    assert servico.estado()["texto"] == f"{d.INTERROMPIDA} {d.TENTE_DE_NOVO}"  # type: ignore[index]


async def test_sem_as_instrucoes_nao_chama_o_hermes(
    api: httpx.AsyncClient, servico: ServicoDeDescoberta, hermes: HermesFalso, tmp_path: Path
) -> None:
    servico.configuracao = Configuracao(ligada=True, prompt=tmp_path / "nao-existe.md")
    await descobrir(api)
    await servico.esperar()
    assert servico.estado()["texto"] == d.SEM_INSTRUCOES  # type: ignore[index]
    assert hermes.runs_pedidos == []


def test_textos_do_fim() -> None:
    assert d.texto_do_fim(0, 0) == "Desta vez não achei página de receita nova para ler."
    assert d.texto_do_fim(1, 0) == "Li 1 página, mas nenhuma receita nova entrou desta vez."
    assert d.texto_do_fim(5, 0) == "Li 5 páginas, mas nenhuma receita nova entrou desta vez."
    assert d.texto_do_fim(5, 1) == "Encontrei 1 receita nova."
    assert d.texto_do_erro(d.DEMOROU, 3) == (
        "A busca demorou demais e eu parei. As 3 receitas novas que eu trouxe já estão na lista."
    )


# --------------------------------------------------------------------------- #
# Limites                                                                      #
# --------------------------------------------------------------------------- #


def _pesquisas(quantas: int) -> list[Evento]:
    return [p for n in range(quantas) for p in ferramenta("web_search", f"receita com {n}", "")]


def _leituras(quantas: int) -> list[Evento]:
    nome = "mcp__mise__buscar_receita_na_web"
    return [p for n in range(quantas) for p in ferramenta(nome, f"https://x.com.br/{n}", "")]


def test_os_limites_da_rodada_sao_os_da_pauta() -> None:
    """8 pesquisas e 20 páginas, os números da pauta; o tempo cresce junto, 35 s por passo."""
    padrao = Configuracao()
    assert (padrao.maximo_de_buscas, padrao.maximo_de_paginas) == (8, 20)
    assert (padrao.maximo_de_buscas, padrao.maximo_de_paginas) == (
        pauta.MAXIMO_DE_BUSCAS,
        pauta.MAXIMO_DE_PAGINAS,
    )
    assert padrao.duracao_maxima_s == d.DURACAO_MAXIMA_S == 35.0 * (8 + 20)


async def test_oito_pesquisas_cabem_na_rodada(
    api: httpx.AsyncClient, servico: ServicoDeDescoberta, hermes: HermesFalso
) -> None:
    hermes.runs.append(RoteiroDeRun([*_pesquisas(pauta.MAXIMO_DE_BUSCAS), *fim_do_run()]))
    await descobrir(api)
    await servico.esperar()
    assert hermes.paradas == []
    assert servico.estado()["estado"] == "parada"  # type: ignore[index]


async def test_passou_de_oito_pesquisas_o_run_para(
    api: httpx.AsyncClient, servico: ServicoDeDescoberta, hermes: HermesFalso
) -> None:
    pesquisas = _pesquisas(pauta.MAXIMO_DE_BUSCAS + 1)
    roteiro = RoteiroDeRun([*pesquisas, Esperar(asyncio.Event()), *fim_do_run()])
    hermes.runs.append(roteiro)
    await descobrir(api)
    await servico.esperar()
    assert hermes.paradas == [roteiro.run_id]
    assert servico.estado()["estado"] == "parada"  # type: ignore[index]


async def test_vinte_paginas_cabem_na_rodada(
    api: httpx.AsyncClient, servico: ServicoDeDescoberta, hermes: HermesFalso
) -> None:
    hermes.runs.append(RoteiroDeRun([*_leituras(pauta.MAXIMO_DE_PAGINAS), *fim_do_run()]))
    await descobrir(api)
    await servico.esperar()
    assert hermes.paradas == []
    assert servico.estado()["lidas"] == 20  # type: ignore[index]


async def test_passou_de_vinte_paginas_o_run_para(
    api: httpx.AsyncClient, servico: ServicoDeDescoberta, hermes: HermesFalso
) -> None:
    """A 21ª página não é lida: o serviço pede para parar quando ela começa."""
    leituras = _leituras(pauta.MAXIMO_DE_PAGINAS + 1)
    roteiro = RoteiroDeRun([*leituras, Esperar(asyncio.Event()), *fim_do_run()])
    hermes.runs.append(roteiro)
    await descobrir(api)
    await servico.esperar()
    assert hermes.paradas == [roteiro.run_id]
    assert servico.estado()["lidas"] == 20  # type: ignore[index]


async def test_rodada_longa_demais_para_e_diz(
    api: httpx.AsyncClient, servico: ServicoDeDescoberta, hermes: HermesFalso
) -> None:
    servico.configuracao = Configuracao(ligada=True, duracao_maxima_s=0.2, prompt=PROMPT)
    roteiro = RoteiroDeRun([*inicio_do_run(), Esperar(asyncio.Event()), *fim_do_run()])
    hermes.runs.append(roteiro)
    await descobrir(api)
    await servico.esperar()
    assert hermes.paradas == [roteiro.run_id]
    assert servico.estado()["texto"] == f"{d.DEMOROU} {d.TENTE_DE_NOVO}"  # type: ignore[index]


# --------------------------------------------------------------------------- #
# O fluxo que cai                                                              #
# --------------------------------------------------------------------------- #


async def test_fluxo_caiu_segue_pelo_estado_e_confere_a_transcricao(
    api: httpx.AsyncClient,
    servico: ServicoDeDescoberta,
    sessao: Sessao,
    hermes: HermesFalso,
    paginas: list[str],
) -> None:
    """Sem os eventos do fim, a transcrição da sessão diz o que o servidor leu."""
    lida: dict[str, Any] = {}
    hermes.runs.append(
        RoteiroDeRun(
            [
                *inicio_do_run(),
                Fazer(lambda: lida.update(sessao.receita_da_web(FRANGO_URL))),
                Quebrar(),
            ],
            mensagens=[
                mensagem_da_ferramenta(
                    {"receita_id": id_da_url(FRANGO_URL), "ja_conhecida": False}
                ),
                mensagem_da_ferramenta({"receita_id": id_da_url(CARNE_URL), "ja_conhecida": True}),
                {"role": "tool", "tool_name": "web_search", "content": '{"ja_conhecida": false}'},
            ],
        )
    )
    await descobrir(api)
    await servico.esperar()
    assert servico.estado() == {
        "estado": "parada",
        "lidas": 1,
        "encontradas": 1,
        "texto": "Encontrei 1 receita nova.",
    }
    frango = sessao.catalogo.por_url(FRANGO_URL)
    assert frango is not None and frango.origem is OrigemNoCatalogo.DESCOBERTA


def test_a_pista_do_hermes_escapada_ou_nao() -> None:
    receita = "0123456789abcdef"
    assert d.resultado_da_leitura(f'{{"receita_id": "{receita}", "ja_conhecida": false}}') == (
        receita,
        False,
    )
    embrulhada = _saida_da_ferramenta({"receita_id": receita, "ja_conhecida": True})
    assert d.resultado_da_leitura(embrulhada) == (receita, True)
    assert d.resultado_da_leitura('{"erro": "a página abriu, mas não traz a receita"}') == (
        None,
        None,
    )
    assert d.resultado_da_leitura(None) == (None, None)


# --------------------------------------------------------------------------- #
# As bordas                                                                    #
# --------------------------------------------------------------------------- #


def test_cada_erro_do_hermes_na_lingua_dela() -> None:
    from gateway.hermes_cliente import (
        AgenteOcupada,
        ChaveRecusada,
        FalhaNoHermes,
        HermesForaDoAr,
        TempoEsgotado,
    )

    assert d._erro_do_hermes(HermesForaDoAr("x")) == d.FORA_DO_AR
    assert d._erro_do_hermes(ChaveRecusada("x")) == d.FORA_DO_AR
    assert d._erro_do_hermes(AgenteOcupada("x")) == d.CONTINUOU_OCUPADA
    assert d._erro_do_hermes(TempoEsgotado("x")) == d.DEMOROU
    assert d._erro_do_hermes(FalhaNoHermes("x")) == d.PROBLEMA


def test_o_site_so_sai_de_endereco_de_verdade() -> None:
    assert d._site("https://www.panelinha.com.br/receita/x") == "panelinha.com.br"
    assert d._site(None) is None
    assert d._site("receita com alcaparras") is None
    assert d._site("http://[::1") is None
    assert d._site("https://") is None


async def test_titulo_repetido_abre_a_sessao_sem_titulo(
    api: httpx.AsyncClient, servico: ServicoDeDescoberta, hermes: HermesFalso
) -> None:
    hermes.recusa_titulo = True
    hermes.runs.append(RoteiroDeRun([*inicio_do_run(), *fim_do_run()]))
    await descobrir(api)
    await servico.esperar()
    assert len(hermes.sessoes_criadas) == 1
    assert hermes.runs_pedidos[0]["session_id"] == hermes.sessoes_criadas[0]


async def test_fechar_no_meio_interrompe_e_diz(
    app: FastAPI, hermes: HermesFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Com fábrica própria, o serviço tem o cliente dele, e fecha os dois ao sair."""
    servico = ServicoDeDescoberta(
        app.state.sessao, fabrica_do_cliente=hermes.cliente, configuracao=RAPIDA
    )
    hermes.runs.append(RoteiroDeRun([*inicio_do_run(), Esperar(asyncio.Event()), *fim_do_run()]))
    resposta = await servico.iniciar()
    assert resposta.status == 202
    await asyncio.sleep(0.2)
    await servico.fechar()
    assert servico.estado()["estado"] == "erro"  # type: ignore[index]
    assert servico.estado()["texto"] == f"{d.INTERROMPIDA} {d.TENTE_DE_NOVO}"  # type: ignore[index]
    await servico.fechar()


async def test_falha_do_hermes_no_fluxo_e_problema(
    api: httpx.AsyncClient, servico: ServicoDeDescoberta, hermes: HermesFalso
) -> None:
    hermes.runs.append(RoteiroDeRun([*inicio_do_run(), *fim_do_run()], run_id="run_que_some"))
    original = hermes._run

    def sem_eventos(request: httpx.Request, caminho: str) -> httpx.Response:
        if caminho.endswith("/events"):
            return httpx.Response(500, json={"error": {"message": "boom"}})
        return original(request, caminho)

    hermes._run = sem_eventos  # type: ignore[method-assign]
    await descobrir(api)
    await servico.esperar()
    assert servico.estado()["texto"] == f"{d.PROBLEMA} {d.TENTE_DE_NOVO}"  # type: ignore[index]


async def test_erro_inesperado_vira_problema(
    api: httpx.AsyncClient,
    servico: ServicoDeDescoberta,
    hermes: HermesFalso,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def quebra(*_: Any) -> None:
        raise RuntimeError("bug")

    monkeypatch.setattr(servico, "_processar", quebra)
    hermes.runs.append(RoteiroDeRun([*inicio_do_run(), *fim_do_run()]))
    await descobrir(api)
    await servico.esperar()
    assert servico.estado()["texto"] == f"{d.PROBLEMA} {d.TENTE_DE_NOVO}"  # type: ignore[index]


async def test_fluxo_caiu_e_o_run_ainda_rodava(
    api: httpx.AsyncClient,
    servico: ServicoDeDescoberta,
    sessao: Sessao,
    hermes: HermesFalso,
    paginas: list[str],
) -> None:
    """Sem o fluxo, o serviço pergunta o estado até o run terminar; sem transcrição, segue."""
    roteiro = RoteiroDeRun(
        [
            *inicio_do_run(),
            *ler_pagina(sessao, FRANGO_URL),
            Fazer(hermes.mensagens_das_sessoes.clear),
            Quebrar(),
        ],
        status_se_cair="running",
    )
    hermes.runs.append(roteiro)
    await descobrir(api)
    await asyncio.sleep(0.2)
    assert servico.em_andamento is not None
    hermes.status_dos_runs[roteiro.run_id] = "completed"
    await servico.esperar()
    assert servico.estado() == {
        "estado": "parada",
        "lidas": 1,
        "encontradas": 1,
        "texto": "Encontrei 1 receita nova.",
    }


async def test_parar_recusado_para_pelo_tempo(
    api: httpx.AsyncClient, servico: ServicoDeDescoberta, hermes: HermesFalso
) -> None:
    servico.configuracao = Configuracao(ligada=True, duracao_maxima_s=0.3, prompt=PROMPT)
    hermes.recusa_parar = True
    pesquisas = _pesquisas(pauta.MAXIMO_DE_BUSCAS + 1)
    hermes.runs.append(RoteiroDeRun([*pesquisas, Esperar(asyncio.Event()), *fim_do_run()]))
    await descobrir(api)
    await servico.esperar()
    assert hermes.paradas == []
    assert servico.estado()["texto"] == f"{d.DEMOROU} {d.TENTE_DE_NOVO}"  # type: ignore[index]


async def test_a_transcricao_sem_nome_de_ferramenta_e_com_conteudo_em_partes(
    api: httpx.AsyncClient,
    servico: ServicoDeDescoberta,
    sessao: Sessao,
    hermes: HermesFalso,
    paginas: list[str],
) -> None:
    lida: dict[str, Any] = {}
    resultado = {"receita_id": id_da_url(CARNE_URL), "ja_conhecida": False}
    hermes.runs.append(
        RoteiroDeRun(
            [
                *inicio_do_run(),
                Fazer(lambda: lida.update(sessao.receita_da_web(CARNE_URL))),
                Quebrar(),
            ],
            mensagens=[
                {"role": "tool", "content": [{"type": "text", "text": json.dumps(resultado)}]},
                {"role": "tool", "content": "sem nada de receita aqui"},
            ],
        )
    )
    await descobrir(api)
    await servico.esperar()
    assert servico.estado()["encontradas"] == 1  # type: ignore[index]
    carne = sessao.catalogo.por_url(CARNE_URL)
    assert carne is not None and carne.origem is OrigemNoCatalogo.DESCOBERTA
