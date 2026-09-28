"""Os dados dela: tudo o que a plataforma guarda, para baixar, e o recomeço pela planilha.

`GET /api/exportacao` devolve um arquivo JSON (`sabor-da-maria-dados.json`),
fora do envelope: é para ela guardar, e não para a tela ler. A forma está em
`contratos/web/exportacao.json`.

`POST /api/dados/restaurar {confirmar: true}` ("Restaurar os dados da
planilha", nas Preferências) guarda uma cópia de tudo em
`<pasta do dossiê>/copias/<quando>/` (o dossiê, as conversas e a trilha do
agente) e só então volta tudo ao que estava na planilha, dentro dos mesmos
arquivos (`mise.restauracao`): o agente, que mantém o dossiê aberto, vê o
recomeço na hora. Ficam as receitas das páginas lidas e as fotos. A resposta
diz, nas palavras dela, com o que ela recomeça (37 ingredientes, R$ 663,39, os
R$ 80,00 inteiros), e `recursos` diz às telas que tudo mudou. A mesma chave de
idempotência (o mesmo clique) não restaura nem copia duas vezes. A forma está
em `contratos/web/restauracao.json`.

Tudo sai das leituras que as telas já fazem, sem conta nova: a despensa e as
mudanças dela, a cozinha e as mudanças dela, o orçamento e todas as compras,
as decisões, o cardápio, os gostos, os preços que ela informou e as receitas em
avaliação. O que ela vê na tela é o que ela leva no arquivo.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response
from mise import despensa_json, perfil_historico
from mise.despensa_json import dinheiro_json
from mise.erros import ErroDeUso, ErroMise
from mise.perfil import contagem
from mise.restauracao import TABELAS_DELA, restaurar_dossie
from mise.serializacao import _receita_json
from pydantic import BaseModel, Field

from gateway.rotas._comum import RespostaPadrao, SessaoDaApp, _dinheiro, envelope_de_erro, responder
from gateway.rotas.perfil import ler_perfil

if TYPE_CHECKING:
    from mise.mcp_server import Sessao
    from mise.restauracao import DossieRestaurado

    from gateway.conversa import ServicoDeConversa

logger = logging.getLogger(__name__)

#: O nome do arquivo que o navegador salva.
NOME_DO_ARQUIVO: Final = "sabor-da-maria-dados.json"

#: Muda quando a forma do arquivo mudar, para quem ler um arquivo antigo saber.
VERSAO: Final = 1

#: Onde as cópias ficam, ao lado do dossiê.
PASTA_DAS_COPIAS: Final = "copias"

#: Todas as telas mudam depois de restaurar: é o `estado.alterado` de cada domínio.
RECURSOS_DA_RESTAURACAO: Final = (
    "despensa",
    "orcamento",
    "receitas",
    "perfil",
    "cardapio",
    "atividades",
    "conversas",
    "visao-geral",
    "precos",
    "avaliacoes",
)

#: Tamanho máximo da chave de idempotência do clique.
_TAMANHO_DA_CHAVE: Final = 200

roteador = APIRouter()


def exportacao(sessao: Sessao) -> dict[str, Any]:
    """Tudo o que ela tem, na forma de `contratos/web/exportacao.json`."""
    dossie = sessao.dossie
    agora = dossie.agora()
    estado = sessao.editavel.estado()
    extrato = dossie.extrato()
    por_id = {linha.id: linha for linha in extrato}
    return {
        "arquivo": "sabor-da-maria-dados",
        "versao": VERSAO,
        "gerado_em": agora.isoformat(),
        "despensa": despensa_json.listar(sessao),
        "despensa_eventos": [
            despensa_json.evento_json(evento, estado, por_id, agora) for evento in estado.eventos
        ],
        "cozinha": ler_perfil(sessao).dados,
        "cozinha_eventos": [
            {
                "tipo": evento.tipo.value,
                "campo": evento.campo,
                "antes": evento.antes,
                "depois": evento.depois,
                "nao_sei": evento.nao_sei,
                "canal": evento.canal.value,
                "quando": evento.registrado.isoformat(),
                "texto": evento.texto,
            }
            # Do mais antigo ao mais novo, como as mudanças da despensa.
            for evento in reversed(perfil_historico.eventos(dossie))
        ],
        "orcamento": despensa_json.orcamento_da_sessao(sessao),
        "compras": [despensa_json.compra_json(linha, agora) for linha in extrato],
        "decisoes": [
            {
                "prato": registro.prato,
                "decisao": registro.decisao.value,
                "motivo": registro.motivo,
                "detalhes": registro.detalhes,
                "canal": registro.canal,
                "quando": registro.registrado.isoformat(),
            }
            for registro in dossie.historico()
        ],
        "cardapio": list(dossie.cardapio),
        "gostos": [
            {
                "prato": opiniao.prato,
                "gosto": opiniao.gosto.value,
                "impedimento": opiniao.impedimento,
                "quando": opiniao.registrado.isoformat(),
            }
            for opiniao in dossie.gostos()
        ],
        "precos_de_mercado": [
            {
                "ingrediente": preco.ingrediente,
                "valor": _dinheiro(preco.valor),
                "por": str(preco.cotacao.por) if preco.cotacao.por else None,
                "origem": preco.origem.value,
                "quando": preco.registrado.isoformat(),
            }
            for preco in dossie.precos()
        ],
        "receitas_em_avaliacao": [
            {"receita_id": despensa_json.slug_da_receita(receita), **_receita_json(receita)}
            for receita in sessao.candidatas.values()
        ],
    }


@roteador.get("/api/exportacao", response_model=None)
def exportar(sessao: SessaoDaApp) -> Response:
    """O arquivo com todos os dados dela, para baixar."""
    try:
        dados = exportacao(sessao)
    except ErroMise as erro:
        return JSONResponse(envelope_de_erro(erro).model_dump())
    return Response(
        content=json.dumps(dados, ensure_ascii=False, indent=2, default=str),
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{NOME_DO_ARQUIVO}"',
            "Cache-Control": "no-store",
        },
    )


# --------------------------------------------------------------------------- #
# Restaurar os dados da planilha                                               #
# --------------------------------------------------------------------------- #


class PedidoDeRestauracao(BaseModel):
    """O "sim" do diálogo de confirmação, e a chave do clique."""

    confirmar: bool = False
    id_cliente: str | None = Field(default=None, min_length=1, max_length=_TAMANHO_DA_CHAVE)


def _trilha() -> Path | None:
    caminho = os.environ.get("MISE_AUDITORIA", "").strip()
    return Path(caminho).expanduser() if caminho else None


def fazer_copia(sessao: Sessao, servico: ServicoDeConversa) -> Path:
    """Guarda o dossiê, as conversas e a trilha numa pasta nova, antes de mexer em nada."""
    base = sessao.dossie.caminho.parent / PASTA_DAS_COPIAS
    carimbo = sessao.dossie.agora().strftime("%Y%m%d-%H%M%S")
    pasta = base / carimbo
    extra = 1
    while pasta.exists():
        extra += 1
        pasta = base / f"{carimbo}-{extra}"
    pasta.mkdir(parents=True)
    sessao.dossie.copiar_para(pasta / sessao.dossie.caminho.name)
    servico.banco.copiar_para(pasta / servico.banco.caminho.name)
    trilha = _trilha()
    if trilha is not None and trilha.is_file():
        shutil.copy2(trilha, pasta / trilha.name)
    return pasta


def _esvaziar_a_trilha() -> None:
    """A trilha do agente recomeça junto das conversas; a cópia guardou a antiga.

    Esvaziada no lugar, e não apagada: o servidor MCP abre o arquivo para
    acrescentar a cada chamada.
    """
    trilha = _trilha()
    if trilha is None or not trilha.is_file():
        return
    try:
        with trilha.open("r+", encoding="utf-8") as arquivo:
            arquivo.truncate(0)
    except OSError as erro:
        logger.warning("não consegui esvaziar a trilha %s: %s", trilha, erro)


def _texto_da_restauracao(
    mudou: bool, ingredientes: int, pago: str, restante: str, receitas: int
) -> str:
    comeco = (
        "Pronto, tudo voltou a ser como na planilha" if mudou else "Já estava tudo como na planilha"
    )
    grade = (
        f" As {contagem(receitas, 'receita', 'receitas')} que eu já li continuam na grade."
        if receitas
        else ""
    )
    return (
        f"{comeco}: {ingredientes} ingredientes, {pago} pagos, e os complementos "
        f"têm {restante}.{grade}"
    )


def restauracao_json(
    sessao: Sessao, restaurado: DossieRestaurado, conversas: int, copia: Path
) -> dict[str, Any]:
    """A resposta: o texto dela, a conciliação com a planilha e o que foi guardado."""
    despensa = sessao.despensa
    orcamento = sessao.dossie.orcamento()
    cozinha = ler_perfil(sessao).dados
    ingredientes = len(despensa.itens)
    pago = dinheiro_json(despensa.total_investido)
    restante = dinheiro_json(orcamento.restante)
    catalogo = restaurado.catalogo
    mudou = restaurado.mudou or conversas > 0
    return {
        "texto": _texto_da_restauracao(
            mudou, ingredientes, pago["texto"], restante["texto"], catalogo.mantidas
        ),
        "mudou": mudou,
        "conciliacao": {
            "ingredientes": ingredientes,
            "total_pago": pago,
            "orcamento_inicial": dinheiro_json(orcamento.inicial),
            "orcamento_restante": restante,
            "cozinha_texto": cozinha["resumo"],
            "texto": f"{ingredientes} ingredientes, {pago['texto']} pagos, restam "
            f"{restante['texto']}",
        },
        "apagado": {
            **{TABELAS_DELA[tabela]: n for tabela, n in restaurado.apagadas.items()},
            "conversas": conversas,
            "receitas ditas": catalogo.ditas,
            "respostas sobre as receitas": catalogo.sem_as_respostas,
        },
        "mantido": {
            "receitas": catalogo.mantidas,
            "texto": "as receitas das páginas lidas e as fotos continuam",
        },
        "copia": copia.name,
        "recursos": list(RECURSOS_DA_RESTAURACAO),
        "repetida": False,
    }


@roteador.post("/api/dados/restaurar", response_model=RespostaPadrao)
async def restaurar(
    corpo: PedidoDeRestauracao,
    requisicao: Request,
    sessao: SessaoDaApp,
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", min_length=1, max_length=_TAMANHO_DA_CHAVE
    ),
) -> RespostaPadrao:
    """Volta tudo ao que estava na planilha, depois de guardar a cópia. Ver o começo do módulo."""
    app = requisicao.app
    chave = idempotency_key or corpo.id_cliente
    feitas: dict[str, dict[str, Any]] | None = getattr(app.state, "restauracoes", None)
    if feitas is None:
        feitas = app.state.restauracoes = {}
    if chave is not None and chave in feitas:
        return RespostaPadrao(dados={**feitas[chave], "repetida": True})
    if not corpo.confirmar:
        return responder(_sem_confirmacao)
    servico: ServicoDeConversa = app.state.conversa
    # A resposta que o agente estava escrevendo não grava depois do recomeço.
    await servico.parar_todos()

    def montar() -> dict[str, Any]:
        copia = fazer_copia(sessao, servico)
        restaurado = restaurar_dossie(sessao.dossie)
        conversas = servico.banco.apagar_tudo()
        _esvaziar_a_trilha()
        sessao.editavel.recarregar()
        sessao.atualizar_planilha_txt()
        logger.info("dados restaurados; cópia em %s", copia)
        return restauracao_json(sessao, restaurado, conversas, copia)

    resposta = responder(montar)
    if chave is not None and resposta.ok:
        feitas[chave] = resposta.dados
    return resposta


def _sem_confirmacao() -> dict[str, Any]:
    raise ErroDeUso(
        "Para restaurar, é preciso confirmar: tudo o que a senhora mudou volta a ser como "
        "na planilha."
    )


__all__ = [
    "NOME_DO_ARQUIVO",
    "PASTA_DAS_COPIAS",
    "RECURSOS_DA_RESTAURACAO",
    "VERSAO",
    "PedidoDeRestauracao",
    "exportacao",
    "fazer_copia",
    "restauracao_json",
    "roteador",
]
