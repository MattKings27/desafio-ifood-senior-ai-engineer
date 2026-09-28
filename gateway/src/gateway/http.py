"""API HTTP do motor: o que o MCP expõe ao agente, aberto para a interface web.

O `gateway` é a camada que decide **como o motor é exposto**. Para o agente,
expõe por MCP, atrás da política de escopos de `gateway.politica`; aqui expõe
por HTTP para a web app, sobre a mesma sessão do motor. A porta HTTP não tem
escopo nem login: ela só atende esta máquina e só aceita escrita vinda da
própria tela (`gateway.seguranca`).

Distinção que vale registrar: a web app **não** calcula nada. Ela lê o que o
motor devolve, incluindo as derivações, e desenha. Qualquer conta feita em
JavaScript seria um segundo lugar onde o número pode estar errado, inclusive o
slider de preço, que pergunta ao motor a cada passo em vez de multiplicar.
"""

from __future__ import annotations

import json
import os
import time
from decimal import Decimal
from typing import Any, Final

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import AliasChoices, BaseModel, Field
from telemetria.metricas import REGISTRO
from telemetria.rastro import (
    configurar as configurar_rastro,
)
from telemetria.rastro import (
    identificador_do_trace,
    span_de_rota,
)

from gateway import rotas, seguranca
from gateway.conversa import ServicoDeConversa
from gateway.politica import ESCOPOS, Escopo
from gateway.rotas._comum import (
    RespostaDeErro,
    RespostaPadrao,
    _dinheiro,
    responder,
    tratar_resposta_de_erro,
)

#: A partir de 400, a resposta conta como falha para a taxa de erro.
_PRIMEIRO_STATUS_DE_ERRO: Final = 400

#: Tamanho máximo de uma chave de idempotência vinda da tela.
_TAMANHO_DA_CHAVE: Final = 200

ORIGENS: Final = [
    o.strip()
    for o in os.environ.get("MISE_CORS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if o.strip()
]


class GostoBody(BaseModel):
    """O que ela acha de fazer um prato.

    `impedimento` é o "vê algum impedimento?" do §2.1, em texto livre, e bloqueia
    mesmo quando ela gosta: gostar de fazer e conseguir fazer são coisas
    diferentes.
    """

    prato: str = Field(min_length=1)
    gosta: bool
    impedimento: str = ""


class PrecoMercadoBody(BaseModel):
    """Quanto custa comprar um ingrediente que falta, e por qual quantidade."""

    ingrediente: str = Field(min_length=1)
    valor: float = Field(ge=0)
    quantidade: float | None = Field(default=None, gt=0)
    unidade: str = ""
    origem: str = "informado_por_ela"


class RespostaBody(BaseModel):
    """A resposta dela a uma pergunta do portão."""

    tipo: str = Field(min_length=1)
    campo: str = Field(min_length=1)
    resposta: str = Field(min_length=1)


class ReceitaDaWebBody(BaseModel):
    """O endereço de uma receita na internet."""

    url: str = Field(min_length=8)
    fonte: str = ""


class CompraBody(BaseModel):
    """O que ela comprou para um prato já confirmado.

    `chave` é a de idempotência do clique (também aceita no cabeçalho
    `Idempotency-Key`). Com ela, duas compras iguais de verdade são duas; sem
    ela, a mesma compra repetida em poucos minutos conta uma vez só.
    """

    prato: str = Field(min_length=1)
    ingrediente: str = Field(min_length=1)
    quantidade: float = Field(gt=0)
    unidade: str = ""
    valor: float = Field(ge=0)
    chave: str | None = Field(default=None, min_length=1, max_length=_TAMANHO_DA_CHAVE)


class DecisaoBody(BaseModel):
    """A decisão dela sobre um prato. **Ela** decide, não o agente.

    `chave` é a de idempotência do clique (também aceita no cabeçalho
    `Idempotency-Key`): o reenvio do mesmo clique não grava duas vezes.
    """

    prato: str = Field(min_length=1)
    decisao: str
    motivo: str = ""
    preco: float | None = Field(default=None, gt=0)
    #: A tela nova manda como `id_cliente`, como nas escritas da despensa.
    chave: str | None = Field(
        default=None,
        min_length=1,
        max_length=_TAMANHO_DA_CHAVE,
        validation_alias=AliasChoices("chave", "id_cliente"),
    )


class ReceitaBody(BaseModel):
    """Receita como a interface envia.

    Definida no módulo, e não dentro da factory: com
    `from __future__ import annotations`, um modelo aninhado vira `ForwardRef`
    que o Pydantic não resolve na hora de validar o corpo da requisição.
    """

    nome: str
    ingredientes: list[dict[str, Any]]
    rendimento_porcoes: int | None = Field(default=None, ge=1)
    modo_preparo: list[str] = Field(default_factory=list)
    tempo_preparo_min: int | None = None
    #: O `cookTime` e o `totalTime` da receita, separados do preparo (`mise.receita`).
    tempo_cozimento_min: int | None = None
    tempo_total_min: int | None = None
    url: str | None = None
    fonte: str | None = None


def criar_app() -> FastAPI:  # noqa: PLR0915
    """Monta a API sobre a mesma sessão que o servidor MCP usa.

    A função é longa porque é um **registro de rotas**: mais de vinte handlers,
    cada um curto e independente. Quebrá-la em grupos parece mais limpo, mas troca uma
    função legível por seis mais o encanamento que as liga; a complexidade real
    está dentro de cada handler, e cada um cabe na tela.

    As rotas novas não entram aqui: vêm de `gateway.rotas.ROTEADORES`, incluídos
    antes destas. A sessão fica em `app.state.sessao` para os roteadores, e o
    envelope, o dinheiro e a categoria `ausente` (404) vêm de `gateway.rotas._comum`.
    """
    from mise.dossie import Canal  # noqa: PLC0415
    from mise.mcp_server import abrir_sessao  # noqa: PLC0415 (import tardio)
    from mise.precos_na_web import ligada  # noqa: PLC0415

    from gateway.auditoria_independente import auditor_do_ambiente  # noqa: PLC0415

    sessao = abrir_sessao()
    sessao.auditor = auditor_do_ambiente()
    # A receita que ela traz pelo endereço procura o preço do que falta (`SABOR_PRECOS_NA_WEB`).
    sessao.pesquisar_precos_ao_guardar = ligada()
    # O que chega por aqui foi ela na tela: decisões e compras gravam isso.
    sessao.canal = Canal.TELA
    # Liga o SDK do OpenTelemetry se `MISE_OTEL=1`. Sem isso a instrumentação
    # existe e é um no-op, que é o comportamento certo para quem só quer rodar
    # o agente, e o motivo de instrumentar com a API em vez do SDK.
    configurar_rastro()

    app = FastAPI(
        title="Sabor da Maria: motor",
        version="1.0.0",
        description="Leitura do motor determinístico para a interface. Nenhum cálculo aqui.",
    )
    # A tela nova edita e apaga (despensa, cozinha, notas, conversas): além de
    # ler e criar, precisa de PUT, PATCH e DELETE.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ORIGENS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    # Só atende `localhost`/`127.0.0.1` e só escreve a pedido da tela (gateway.seguranca).
    seguranca.configurar(app)
    app.state.sessao = sessao
    # O dono dos turnos da conversa (gateway.conversa): no arranque, marca como
    # interrompido o turno que o processo anterior deixou em andamento.
    app.state.conversa = ServicoDeConversa.do_ambiente(sessao, app)
    app.add_exception_handler(RespostaDeErro, tratar_resposta_de_erro)
    for roteador in rotas.ROTEADORES:
        app.include_router(roteador)

    # ------------------------------------------------------------------ #
    # Orçamento (o cardápio está em rotas/cardapio.py; a tela inicial, em
    # rotas/visao_geral.py)
    # ------------------------------------------------------------------ #

    @app.get("/api/orcamento", response_model=RespostaPadrao)
    def orcamento() -> RespostaPadrao:
        """Burn-down dos R$ 80,00 de complementos."""

        def montar() -> dict[str, Any]:
            e = sessao.dossie.orcamento()
            return {
                "inicial": _dinheiro(e.inicial),
                "gasto": _dinheiro(e.gasto),
                "restante": _dinheiro(e.restante),
                "fracao_usada": e.fracao_usada,
                "compras": [
                    {"descricao": d, "valor": _dinheiro(v), "quando": q.isoformat()}
                    for d, v, q in sessao.dossie.gastos()
                ],
            }

        return responder(montar)

    # ------------------------------------------------------------------ #
    # Portão, CMV e preço
    # ------------------------------------------------------------------ #

    @app.post("/api/avaliar", response_model=RespostaPadrao)
    def avaliar(receita: ReceitaBody) -> RespostaPadrao:
        """Roda o portão de viabilidade sobre uma receita, com o `exige` e o `por_passo`."""
        from mise.despensa_json import slug_da_receita  # noqa: PLC0415
        from mise.mcp_server import ReceitaEntrada, _avaliacao_json  # noqa: PLC0415
        from mise.passos import detalhar  # noqa: PLC0415

        def montar() -> dict[str, Any]:
            # A mesma regra da conversa: a receita digitada é a dela, e um
            # endereço só vale se o servidor já leu a página (`receita_para_avaliar`).
            dominio, recado = sessao.receita_para_avaliar(
                None, ReceitaEntrada(**receita.model_dump())
            )
            sessao.guardar(dominio)
            perfil = sessao.perfil
            avaliacao = sessao.avaliar(dominio, perfil=perfil)
            resultado = {**_avaliacao_json(avaliacao), **detalhar(dominio, perfil, avaliacao)}
            resultado["receita_id"] = slug_da_receita(dominio)
            if recado is not None:
                resultado["recado"] = recado
            return resultado

        return responder(montar)

    @app.post("/api/decisao", response_model=RespostaPadrao)
    def registrar_decisao(
        corpo: DecisaoBody,
        idempotency_key: str | None = Header(
            default=None, alias="Idempotency-Key", min_length=1, max_length=_TAMANHO_DA_CHAVE
        ),
    ) -> RespostaPadrao:
        """Registra o que ela decidiu sobre um prato. Aceitar passa pelo portão.

        O log é append-only: aceitar e depois recusar não apaga o aceite. É o que
        permite responder "por que este prato entrou no cardápio?" semanas depois.
        `texto` é a decisão dita para ela ("A senhora tirou o arroz com frango do
        cardápio."), lida contra a anterior do mesmo prato.
        """
        from gateway.cardapio import texto_da_decisao  # noqa: PLC0415

        def montar() -> dict[str, Any]:
            registro, detalhes = sessao.decidir(
                corpo.prato,
                corpo.decisao,
                corpo.motivo,
                corpo.preco,
                chave=idempotency_key or corpo.chave,
            )
            return {
                "prato": registro.prato,
                "decisao": registro.decisao.value,
                "motivo": registro.motivo,
                "texto": texto_da_decisao(registro, sessao.dossie.historico(registro.prato)),
                **detalhes,
                "cardapio": list(sessao.dossie.cardapio),
            }

        return responder(montar)

    @app.post("/api/gosto", response_model=RespostaPadrao)
    def registrar_gosto(corpo: GostoBody) -> RespostaPadrao:
        """Guarda se ela gosta de fazer um prato: a quinta checagem do portão."""
        from mise.perfil import Gosto  # noqa: PLC0415

        def montar() -> dict[str, Any]:
            opiniao = sessao.dossie.registrar_gosto(
                corpo.prato,
                Gosto.GOSTA if corpo.gosta else Gosto.NAO_GOSTA,
                corpo.impedimento,
            )
            return {
                "prato": opiniao.prato,
                "gosto": opiniao.gosto.value,
                "impedimento": opiniao.impedimento,
                "bloqueia": opiniao.gosto.bloqueia or bool(opiniao.impedimento),
                "texto": str(opiniao),
            }

        return responder(montar)

    @app.get("/api/gostos", response_model=RespostaPadrao)
    def listar_gostos() -> RespostaPadrao:
        """O que ela já disse sobre cada prato."""

        def montar() -> dict[str, Any]:
            return {
                "gostos": [
                    {
                        "prato": o.prato,
                        "gosto": o.gosto.value,
                        "impedimento": o.impedimento,
                        "texto": str(o),
                    }
                    for o in sessao.dossie.gostos()
                ]
            }

        return responder(montar)

    @app.post("/api/preco-mercado", response_model=RespostaPadrao)
    def registrar_preco_mercado(corpo: PrecoMercadoBody) -> RespostaPadrao:
        """Guarda o custo de um item que falta comprar, e devolve o orçamento."""

        def montar() -> dict[str, Any]:
            preco, faltando = sessao.cotar(
                corpo.ingrediente, corpo.valor, corpo.quantidade, corpo.unidade, corpo.origem
            )
            return {
                "ingrediente": preco.ingrediente,
                "valor": _dinheiro(preco.valor),
                "por": str(preco.cotacao.por) if preco.cotacao.por else None,
                "origem": preco.origem.value,
                "casou_com_o_que_falta": preco.ingrediente in faltando,
                "orcamento_restante": _dinheiro(sessao.dossie.orcamento().restante),
                "texto": str(preco),
            }

        return responder(montar)

    @app.post("/api/resposta", response_model=RespostaPadrao)
    def registrar_resposta(corpo: RespostaBody) -> RespostaPadrao:
        """A resposta dela a uma pergunta do portão, pela tela."""
        return responder(lambda: sessao.responder(corpo.tipo, corpo.campo, corpo.resposta))

    @app.get("/api/candidatas", response_model=RespostaPadrao)
    def comparar_candidatas() -> RespostaPadrao:
        """As receitas em avaliação lado a lado: o que a despensa já cobre em cada uma."""

        return responder(sessao.comparar)

    @app.get("/api/receita", response_model=RespostaPadrao)
    def receita_guardada(prato: str = Query(..., min_length=1)) -> RespostaPadrao:
        """A receita já avaliada, para a tela de preço abrir preenchida."""
        from mise.mcp_server import _receita_json  # noqa: PLC0415

        def montar() -> dict[str, Any]:
            receita, _ = sessao.receita_avaliada(prato)
            return _receita_json(receita)

        return responder(montar)

    @app.post("/api/receita-da-web", response_model=RespostaPadrao)
    def receita_da_web(corpo: ReceitaDaWebBody) -> RespostaPadrao:
        """Traz a receita de uma página para o catálogo, com a fonte. Só endereço público.

        A mesma porta da conversa (`Sessao.receita_da_web`): o servidor lê a
        página, e a fonte é a que a página diz, não a que veio no pedido. Como
        foi ela que trouxe, pela tela antiga de receitas, a receita também entra
        na lista das que estão em avaliação, que é o que aquela tela mostra.
        """
        from mise.catalogo import OrigemNoCatalogo  # noqa: PLC0415

        def montar() -> dict[str, Any]:
            trazida = sessao.receita_da_web(corpo.url, origem=OrigemNoCatalogo.URL_DELA)
            sessao.guardar(sessao.receita_por_id(str(trazida["receita_id"])))
            return trazida

        return responder(montar)

    @app.post("/api/compra", response_model=RespostaPadrao)
    def registrar_compra(
        corpo: CompraBody,
        idempotency_key: str | None = Header(
            default=None, alias="Idempotency-Key", min_length=1, max_length=_TAMANHO_DA_CHAVE
        ),
    ) -> RespostaPadrao:
        """Registra uma compra pelo portão: o prato confirmado e o item que ele precisa."""

        def montar() -> dict[str, Any]:
            resultado = sessao.comprar(
                corpo.prato,
                corpo.ingrediente,
                corpo.quantidade,
                corpo.unidade,
                corpo.valor,
                chave=idempotency_key or corpo.chave,
            )
            resultado["orcamento_restante"] = _dinheiro(resultado["orcamento_restante"])
            return resultado

        return responder(montar)

    @app.get("/api/precos-mercado", response_model=RespostaPadrao)
    def listar_precos_mercado() -> RespostaPadrao:
        """As cotações já registradas para o que falta comprar."""

        def montar() -> dict[str, Any]:
            return {
                "precos": [
                    {
                        "ingrediente": p.ingrediente,
                        "valor": _dinheiro(p.valor),
                        "origem": p.origem.value,
                        "texto": str(p),
                    }
                    for p in sessao.dossie.precos()
                ]
            }

        return responder(montar)

    @app.post("/api/cmv", response_model=RespostaPadrao)
    def cmv(receita: ReceitaBody) -> RespostaPadrao:
        """CMV por porção. Recusa receita sem viabilidade confirmada.

        A mesma garantia do MCP vale aqui: se a web app pudesse contornar o
        portão, ela seria um bypass da regra central do sistema.
        """
        from mise.cmv import calcular  # noqa: PLC0415
        from mise.mcp_server import ReceitaEntrada  # noqa: PLC0415

        def montar() -> dict[str, Any]:
            # O custo sai da receita que passou pela conferência; digitada
            # diferente dela, é recusada (`Sessao.receita_para_custear`).
            dominio = sessao.receita_para_custear(None, ReceitaEntrada(**receita.model_dump()))
            sessao.guardar(dominio)
            r = calcular(dominio, sessao.avaliar(dominio))
            return {
                "prato": r.receita,
                "total": _dinheiro(r.para_precificar),
                "e_faixa": r.e_faixa,
                "minimo": _dinheiro(r.minimo),
                "maximo": _dinheiro(r.maximo),
                "incerteza": float(r.incerteza_relativa),
                "rendimento_original": r.rendimento_original,
                "itens_a_gosto": list(r.itens_a_gosto),
                "linhas": [
                    {
                        "ingrediente": linha.ingrediente,
                        "quantidade": linha.quantidade,
                        "custo": _dinheiro(exibido),
                        "derivacao": linha.derivacao,
                        "fracao": (
                            float(linha.custo.valor / r.total.valor) if r.total.valor else 0.0
                        ),
                    }
                    for linha, exibido in zip(r.linhas, r.custos_exibidos(), strict=True)
                ],
                "explicacao": r.explicacao(),
            }

        return responder(montar)

    @app.get("/api/precos", response_model=RespostaPadrao)
    def precos(
        prato: str = Query(..., min_length=1, description="prato já avaliado"),
        cmv: float | None = Query(default=None, gt=0, description="confere com o calculado"),
    ) -> RespostaPadrao:
        """Os três cenários de um prato aprovado, com a taxa de 10% aberta.

        O custo é recalculado aqui a partir do prato. A tela não manda o número
        que vira preço: se mandasse, um erro dela viraria preço na vitrine. Os
        limites do controle deslizante (`controle{min, max, passo}`) também vêm
        daqui: o mínimo é dinheiro, e o teto também.
        """
        from mise.preco import montar_cenarios, sensibilidade  # noqa: PLC0415

        from gateway.cardapio import controle_do_preco  # noqa: PLC0415

        def montar() -> dict[str, Any]:
            valor = sessao.custo_conferido(prato, cmv)
            tabela = montar_cenarios(valor)
            return {
                "prato": prato,
                "cmv": _dinheiro(valor),
                "preco_minimo": _dinheiro(tabela.preco_minimo),
                "explicacao_da_taxa": tabela.explicacao_da_taxa(),
                "cenarios": [
                    {
                        "nome": c.nome,
                        "descricao": c.descricao,
                        "preco": _dinheiro(c.preco),
                        "taxa": _dinheiro(c.valor_da_taxa),
                        "recebe": _dinheiro(c.recebe),
                        "lucro": _dinheiro(c.lucro),
                        "food_cost": float(c.food_cost),
                        "margem": float(c.margem_sobre_preco),
                        "explicacao": c.explicacao(),
                    }
                    for c in tabela
                ],
                "sensibilidade": _serializar(sensibilidade(valor, tabela.cenarios[1].preco)),
                "controle": controle_do_preco(valor, tabela.preco_minimo),
            }

        return responder(montar)

    @app.get("/api/preco-em", response_model=RespostaPadrao)
    def preco_em(
        prato: str = Query(..., min_length=1),
        preco: float = Query(..., gt=0),
    ) -> RespostaPadrao:
        """Um ponto de preço arbitrário de um prato aprovado: é o que alimenta o slider.

        A interface **não** calcula esse número: pergunta ao motor a cada passo.
        É mais uma chamada de rede e um lugar a menos onde a conta pode divergir.
        """
        from mise.dinheiro import Dinheiro  # noqa: PLC0415
        from mise.preco import TAXA_PLATAFORMA, Cenario  # noqa: PLC0415

        def montar() -> dict[str, Any]:
            custo = sessao.custo_conferido(prato)
            c = Cenario("Escolhido", "", Dinheiro.de(preco), custo, TAXA_PLATAFORMA)
            return {
                "preco": _dinheiro(c.preco),
                "taxa": _dinheiro(c.valor_da_taxa),
                "recebe": _dinheiro(c.recebe),
                "lucro": _dinheiro(c.lucro),
                "food_cost": float(c.food_cost),
                "margem": float(c.margem_sobre_preco),
                "da_prejuizo": c.da_prejuizo,
                "explicacao": c.explicacao(),
            }

        return responder(montar)

    # ------------------------------------------------------------------ #
    # Trilha, política e saúde
    # ------------------------------------------------------------------ #

    @app.get("/api/auditoria", response_model=RespostaPadrao)
    def auditoria(limite: int = Query(default=50, ge=1, le=500)) -> RespostaPadrao:
        """Últimas chamadas ao motor: a trilha que torna o sistema explicável.

        O arquivo só nasce na primeira chamada de ferramenta do agente. Antes
        disso não há o que mostrar, e isso não é falha: é lista vazia. A tela
        mostrava "motor respondeu 503" para quem ainda não tinha conversado.
        Falha é não conseguir ler um arquivo que existe (um diretório no lugar,
        sem permissão): aí continua 503.
        """
        caminho = os.environ.get("MISE_AUDITORIA")
        if not caminho:
            return RespostaPadrao(dados={"eventos": [], "arquivo": None})
        try:
            eventos = _ler_cauda(caminho, limite)
        except FileNotFoundError:
            eventos = []
        except OSError as erro:
            raise HTTPException(status_code=503, detail=f"trilha indisponível: {erro}") from erro
        return RespostaPadrao(dados={"eventos": eventos, "arquivo": caminho})

    @app.get("/api/escopos", response_model=RespostaPadrao)
    def escopos() -> RespostaPadrao:
        """Quais ferramentas são de leitura e quais são de escrita."""
        return RespostaPadrao(
            dados={
                "leitura": sorted(n for n, e in ESCOPOS.items() if e is Escopo.LEITURA),
                "escrita": sorted(n for n, e in ESCOPOS.items() if e is Escopo.ESCRITA),
            }
        )

    # Há **dois** pontos de entrada no motor: o MCP, por onde o agente chama, e o
    # HTTP, por onde a interface chama. Instrumentar só um deixa metade do
    # sistema invisível, e foi exatamente o que aconteceu na primeira versão
    # disto: `/observabilidade` vinha vazio depois de dezenas de requisições,
    # porque a instrumentação estava só no middleware do MCP.
    @app.middleware("http")
    async def medir(requisicao: Request, adiante: Any) -> Any:
        rota = requisicao.url.path
        # Endpoint de infraestrutura fica de fora: probe a cada dez segundos
        # dominaria a amostra e esconderia a latência do que importa.
        if rota.startswith(("/saude", "/metricas", "/observabilidade")):
            return await adiante(requisicao)

        inicio = time.monotonic()
        com_erro = False
        with span_de_rota(requisicao.method, rota) as span:
            try:
                resposta = await adiante(requisicao)
            except Exception:
                com_erro = True
                raise
            else:
                com_erro = resposta.status_code >= _PRIMEIRO_STATUS_DE_ERRO
                span.set_attribute("http.response.status_code", resposta.status_code)
                if identificador := identificador_do_trace():
                    # O trace_id volta no cabeçalho: é o que transforma "deu erro
                    # na tela" num chamado que alguém consegue investigar.
                    resposta.headers["X-Trace-Id"] = identificador
                return resposta
            finally:
                duracao = (time.monotonic() - inicio) * 1000
                REGISTRO.registrar(f"{requisicao.method} {rota}", duracao, erro=com_erro)

    @app.get("/metricas", response_class=PlainTextResponse)
    def metricas() -> str:
        """Latência e erro por ferramenta, em formato de texto do Prometheus.

        Separado de `/saude/pronto` de propósito: readiness é uma pergunta de
        sim ou não que o orquestrador faz a cada dez segundos, e enfiar agregação
        de percentil ali tornaria a probe cara sem motivo.
        """
        return REGISTRO.prometheus()

    @app.get("/observabilidade", response_model=RespostaPadrao)
    def observabilidade() -> RespostaPadrao:
        """O mesmo dado, em JSON, para a tela de trilha.

        Traz as três mais lentas em primeiro lugar porque é por elas que qualquer
        investigação de latência começa, e deixar isso pronto evita que a
        primeira reação seja "o modelo está lento", que quase sempre está errada.
        """

        def montar() -> dict[str, Any]:
            series = REGISTRO.todas()
            return {
                "series": [
                    {
                        "ferramenta": s.nome,
                        "chamadas": s.total,
                        "p50_ms": round(s.p50, 1),
                        "p95_ms": round(s.p95, 1),
                        "p99_ms": round(s.p99, 1),
                        "taxa_de_erro": round(s.taxa_de_erro, 4),
                    }
                    for s in series
                ],
                "mais_lentas": [s.nome for s in REGISTRO.mais_lentas()],
                "rastro_ativo": bool(identificador_do_trace()),
            }

        return responder(montar)

    @app.get("/saude/vivo")
    def vivo() -> dict[str, str]:
        """Liveness: o processo responde."""
        return {"estado": "vivo"}

    @app.get("/saude/pronto")
    def pronto() -> dict[str, Any]:
        """Readiness: a planilha carregou e o dossiê abriu.

        Distinto do liveness de propósito: um processo vivo com planilha
        ilegível não deve receber tráfego, mas também não deve ser reiniciado
        em laço: reiniciar não conserta arquivo corrompido.

        O que conta é a planilha, e não a despensa de agora: ela pode tirar
        todos os itens, e a tela continua precisando responder para ela
        desfazer. Sem mudança nenhuma, a despensa de agora é a própria planilha.
        """
        if len(sessao.planilha) == 0:
            raise HTTPException(status_code=503, detail="a planilha não carregou")
        despensa_de_agora = sessao.despensa
        return {
            "estado": "pronto",
            "itens": len(despensa_de_agora),
            "pendencias": len(despensa_de_agora.pendencias),
            "orcamento_restante": str(sessao.dossie.orcamento().restante),
        }

    return app


# --------------------------------------------------------------------------- #
# Utilitários
# --------------------------------------------------------------------------- #


def _serializar(dados: dict[str, Any]) -> dict[str, Any]:
    """Converte `Dinheiro` e `Decimal` para o formato que a interface espera."""
    saida: dict[str, Any] = {}
    for chave, valor in dados.items():
        if hasattr(valor, "arredondado"):
            saida[chave] = _dinheiro(valor)
        elif isinstance(valor, Decimal):
            saida[chave] = float(valor)
        else:
            saida[chave] = valor
    return saida


def _ler_cauda(caminho: str, limite: int) -> list[dict[str, Any]]:
    """Últimos `limite` eventos da trilha. Linha corrompida é pulada, não fatal.

    O `~` é expandido como quem escreve (`politica.Auditoria.do_ambiente`): sem
    isso, `MISE_AUDITORIA=~/trilha.jsonl` gravava num arquivo e lia outro.
    """
    from pathlib import Path  # noqa: PLC0415

    linhas = Path(caminho).expanduser().read_text(encoding="utf-8").splitlines()[-limite:]
    eventos: list[dict[str, Any]] = []
    for linha in linhas:
        try:
            eventos.append(json.loads(linha))
        except json.JSONDecodeError:
            continue
    return eventos


def main() -> None:
    """Sobe a API. Usada por `make api`."""
    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        criar_app(),
        host=os.environ.get("MISE_HTTP_HOST", "127.0.0.1"),
        port=int(os.environ.get("MISE_HTTP_PORT", "8777")),
        log_level=os.environ.get("MISE_LOG", "info").lower(),
    )


if __name__ == "__main__":
    main()


__all__ = ["ReceitaBody", "RespostaPadrao", "criar_app", "main"]
