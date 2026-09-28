"""A política de acesso. É fronteira de segurança: o que passa aqui, passa."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from gateway.politica import (
    ESCOPOS,
    METODO_CHAMADA,
    REGISTRAM_ARTEFATO,
    Auditoria,
    Autenticacao,
    Autorizacao,
    CircuitBreaker,
    Credencial,
    ErroDePolitica,
    Escopo,
    EstadoBreaker,
    Quota,
    RateLimit,
    escopos_de,
    pilha_padrao,
)


@dataclass
class CtxFalso:
    """O mínimo do `ServerRequestContext` que a política enxerga."""

    method: str = METODO_CHAMADA
    params: Any = None
    request_id: str = "req-1"

    def __post_init__(self) -> None:
        if self.params is None:
            self.params = {"name": "custo_unitario", "arguments": {}}


async def passa(_ctx: Any) -> str:
    return "ok"


async def explode(_ctx: Any) -> str:
    raise RuntimeError("falha do motor")


async def executar(middlewares: list[Any], ctx: Any, final: Any = passa) -> Any:
    """Encadeia a pilha na ordem em que o MCP a aplica (primeira = mais externa)."""

    async def chamar(indice: int, c: Any) -> Any:
        if indice >= len(middlewares):
            return await final(c)
        return await middlewares[indice](c, lambda prox: chamar(indice + 1, prox))

    return await chamar(0, ctx)


# --------------------------------------------------------------------------- #
# Allowlist
# --------------------------------------------------------------------------- #


def test_toda_ferramenta_tem_escopo_classificado() -> None:
    """Allowlist: ferramenta nova nasce inacessível até ser classificada."""
    assert all(isinstance(e, Escopo) for e in ESCOPOS.values())


def test_escrita_e_minoria_e_deliberada() -> None:
    """Acrescentar uma permissão de escrita tem que doer um pouco.

    Este teste fixa o conjunto exato de propósito: quem cria uma ferramenta que
    escreve precisa vir aqui e dizer por quê, num diff que alguém lê. Foi assim
    que `registrar_preco_mercado` e `registrar_gosto` entraram: a primeira grava a
    cotação que a Dona Maria informa, sem a qual o custo do que falta comprar fica
    indefinido; a segunda grava se ela quer fazer o prato, que é a quinta checagem
    do portão.

    `atualizar_despensa` entrou para o agente anotar o que ela conta que mudou na
    despensa ("acabou o bacon", "a cobertura vem com 1 kg"): sem isso, a conversa
    sabia do peso da embalagem e o custo continuava indedutível. Ela não mexe nos
    R$ 80,00 (acrescenta só o que ela já tinha); a compra com os complementos
    continua em `registrar_compra`, pelo portão do prato.

    `registrar_avaliacao_da_receita` entrou para a conversa guardar o que ela
    acha de uma receita: se gosta de fazer, as estrelas e as notas. É a mesma
    avaliação da página da receita, e o gosto dela é também a checagem de gosto
    do portão; sem ela, o que ela disse na conversa se perdia e a pontuação do
    ranking só existia na tela.
    """
    escrita = {n for n, e in ESCOPOS.items() if e is Escopo.ESCRITA}
    assert escrita == {
        "registrar_resposta",
        "registrar_decisao",
        "registrar_compra",
        "registrar_preco_mercado",
        "registrar_gosto",
        "atualizar_despensa",
        "registrar_avaliacao_da_receita",
    }
    # Escrita continua minoria folgada: ler é o caso comum, mudar estado não.
    assert len(escrita) * 2 < len(ESCOPOS)


def test_as_leituras_que_gravam_registro_do_servidor_sao_estas() -> None:
    """Leitura que grava alguma coisa diz o quê: o escopo não pode ser meia verdade.

    As cinco gravam um registro que o próprio servidor produz (a receita
    candidata, a planilha em texto, o preço médio que ele procurou nos
    mercados de São Paulo) e não mexem em nada dela. O conjunto é
    fixado de propósito: ferramenta de leitura que passar a gravar entra aqui,
    num diff que alguém lê. O teste de `test_catalogo_das_ferramentas` confere,
    chamando cada uma, que as outras de leitura não gravam nada.
    """
    assert REGISTRAM_ARTEFATO == {
        "buscar_receita_na_web",
        "buscar_preco_na_web",
        "avaliar_receita",
        "calcular_cmv",
        "consultar_planilha",
    }
    assert all(ESCOPOS[nome] is Escopo.LEITURA for nome in REGISTRAM_ARTEFATO)


def test_escopos_de_marca_desconhecidas() -> None:
    mapa = escopos_de(["custo_unitario", "apagar_tudo"])
    assert mapa["custo_unitario"] is Escopo.LEITURA
    assert mapa["apagar_tudo"] is None


# --------------------------------------------------------------------------- #
# Autenticação
# --------------------------------------------------------------------------- #


async def test_modo_aberto_sem_tokens() -> None:
    auth = Autenticacao(tokens={})
    assert auth.aberto
    assert await executar([auth], CtxFalso()) == "ok"


async def test_token_valido_passa(monkeypatch: pytest.MonkeyPatch) -> None:
    auth = Autenticacao(tokens={"segredo": Credencial("agente", frozenset({Escopo.LEITURA}))})
    monkeypatch.setenv("MISE_TOKEN", "segredo")
    assert await executar([auth], CtxFalso()) == "ok"


async def test_token_invalido_e_barrado(monkeypatch: pytest.MonkeyPatch) -> None:
    auth = Autenticacao(tokens={"segredo": Credencial("agente", frozenset({Escopo.LEITURA}))})
    monkeypatch.setenv("MISE_TOKEN", "chute")
    with pytest.raises(ErroDePolitica) as exc:
        await executar([auth], CtxFalso())
    assert exc.value.codigo == "nao_autenticado"


async def test_token_ausente_e_barrado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISE_TOKEN", raising=False)
    auth = Autenticacao(tokens={"segredo": Credencial("agente", frozenset({Escopo.LEITURA}))})
    with pytest.raises(ErroDePolitica, match="credencial"):
        await executar([auth], CtxFalso())


async def test_token_pode_vir_no_meta_da_chamada() -> None:
    auth = Autenticacao(tokens={"segredo": Credencial("agente", frozenset({Escopo.LEITURA}))})
    ctx = CtxFalso(params={"name": "custo_unitario", "_meta": {"mise_token": "segredo"}})
    assert await executar([auth], ctx) == "ok"


def test_autenticacao_do_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISE_TOKEN_LEITURA", "tok-r")
    monkeypatch.setenv("MISE_TOKEN_ESCRITA", "tok-w")
    auth = Autenticacao.do_ambiente()
    assert not auth.aberto
    assert auth.tokens["tok-r"].escopos == frozenset({Escopo.LEITURA})
    assert Escopo.ESCRITA in auth.tokens["tok-w"].escopos


def test_credencial_de_leitura_nao_escreve() -> None:
    cred = Credencial("r", frozenset({Escopo.LEITURA}))
    assert cred.pode(Escopo.LEITURA)
    assert not cred.pode(Escopo.ESCRITA)


async def test_metodo_que_nao_e_chamada_passa_direto() -> None:
    auth = Autenticacao(tokens={"x": Credencial("a", frozenset())})
    assert await executar([auth], CtxFalso(method="tools/list")) == "ok"


# --------------------------------------------------------------------------- #
# Autorização
# --------------------------------------------------------------------------- #


async def test_ferramenta_fora_da_allowlist_e_negada() -> None:
    ctx = CtxFalso(params={"name": "apagar_dossie"})
    with pytest.raises(ErroDePolitica) as exc:
        await executar([Autorizacao()], ctx)
    assert exc.value.codigo == "ferramenta_desconhecida"


async def test_escopo_insuficiente_e_negado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Credencial de leitura não compromete o orçamento da Dona Maria."""
    monkeypatch.setenv("MISE_TOKEN", "so-leitura")
    auth = Autenticacao(tokens={"so-leitura": Credencial("leitor", frozenset({Escopo.LEITURA}))})
    ctx = CtxFalso(params={"name": "registrar_compra"})
    with pytest.raises(ErroDePolitica) as exc:
        await executar([auth, Autorizacao()], ctx)
    assert exc.value.codigo == "escopo_insuficiente"


async def test_escopo_suficiente_passa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISE_TOKEN", "tudo")
    auth = Autenticacao(
        tokens={"tudo": Credencial("admin", frozenset({Escopo.LEITURA, Escopo.ESCRITA}))}
    )
    ctx = CtxFalso(params={"name": "registrar_compra"})
    assert await executar([auth, Autorizacao()], ctx) == "ok"


async def test_sem_credencial_resolvida_nao_bloqueia_por_escopo() -> None:
    """Modo aberto: a autorização ainda confere a allowlist, mas não o escopo."""
    assert await executar([Autorizacao()], CtxFalso()) == "ok"


# --------------------------------------------------------------------------- #
# Rate limit
# --------------------------------------------------------------------------- #


async def test_rate_limit_corta_rajada() -> None:
    limite = RateLimit(capacidade=3, recarga_por_segundo=0.0)
    for _ in range(3):
        assert await executar([limite], CtxFalso()) == "ok"
    with pytest.raises(ErroDePolitica) as exc:
        await executar([limite], CtxFalso())
    assert exc.value.codigo == "rate_limit"


async def test_rate_limit_e_por_ferramenta() -> None:
    """Estourar numa ferramenta não pode travar as outras."""
    limite = RateLimit(capacidade=1, recarga_por_segundo=0.0)
    await executar([limite], CtxFalso(params={"name": "custo_unitario"}))
    assert await executar([limite], CtxFalso(params={"name": "consultar_perfil"})) == "ok"


async def test_rate_limit_recarrega_com_o_tempo() -> None:
    """Relógio controlado: sem `sleep`, sem teste intermitente."""
    agora = [0.0]
    limite = RateLimit(capacidade=1, recarga_por_segundo=1.0, relogio=lambda: agora[0])

    await executar([limite], CtxFalso())
    with pytest.raises(ErroDePolitica):
        await executar([limite], CtxFalso())

    agora[0] = 1.5  # um segundo e meio depois, há token de novo
    assert await executar([limite], CtxFalso()) == "ok"


async def test_breaker_fecha_de_novo_apos_sucesso_no_meio_aberto() -> None:
    agora = [0.0]
    breaker = CircuitBreaker(limite_falhas=1, espera_segundos=10.0, relogio=lambda: agora[0])

    with pytest.raises(RuntimeError):
        await executar([breaker], CtxFalso(), final=explode)
    assert breaker.estado("custo_unitario") is EstadoBreaker.ABERTO

    agora[0] = 11.0
    assert breaker.estado("custo_unitario") is EstadoBreaker.MEIO_ABERTO
    assert await executar([breaker], CtxFalso()) == "ok"
    assert breaker.estado("custo_unitario") is EstadoBreaker.FECHADO


# --------------------------------------------------------------------------- #
# Quota
# --------------------------------------------------------------------------- #


async def test_quota_termina_laco_infinito() -> None:
    quota = Quota(maximo=2)
    await executar([quota], CtxFalso())
    await executar([quota], CtxFalso())
    with pytest.raises(ErroDePolitica) as exc:
        await executar([quota], CtxFalso())
    assert exc.value.codigo == "quota_esgotada"
    assert quota.usadas == 3


async def test_quota_ignora_nao_chamadas() -> None:
    quota = Quota(maximo=1)
    await executar([quota], CtxFalso(method="tools/list"))
    assert quota.usadas == 0


async def test_quota_e_janela_movel_e_nao_teto_para_sempre() -> None:
    """Sob o gateway do Hermes o processo do motor nunca reinicia.

    Com teto por processo, depois de `maximo` chamadas somadas ao longo de dias
    toda ferramenta era recusada. No ritmo normal, a janela nunca enche.
    """
    agora = [0.0]
    quota = Quota(maximo=3, janela_segundos=60.0, relogio=lambda: agora[0])
    for i in range(30):
        agora[0] = i * 30.0  # uma chamada a cada meio minuto, por quinze minutos
        assert await executar([quota], CtxFalso()) == "ok"
    assert quota.usadas == 2


async def test_quota_recusa_rajada_e_volta_depois_da_janela() -> None:
    agora = [0.0]
    quota = Quota(maximo=2, janela_segundos=60.0, relogio=lambda: agora[0])
    await executar([quota], CtxFalso())
    agora[0] = 10.0
    await executar([quota], CtxFalso())
    agora[0] = 20.0
    with pytest.raises(ErroDePolitica) as exc:
        await executar([quota], CtxFalso())
    assert exc.value.codigo == "quota_esgotada"
    assert "2 chamadas em 1 minuto esgotada" in exc.value.motivo

    agora[0] = 81.0  # a rajada inteira, inclusive a recusada, saiu da janela
    assert quota.usadas == 0
    assert await executar([quota], CtxFalso()) == "ok"


async def test_quota_conta_a_recusada_para_o_laco_nao_escapar() -> None:
    """Um laço que continua batendo continua barrado; a janela só esvazia quando ele para."""
    agora = [0.0]
    quota = Quota(maximo=1, janela_segundos=60.0, relogio=lambda: agora[0])
    await executar([quota], CtxFalso())
    for segundo in (30.0, 70.0, 110.0):  # a aceita já saiu da janela; as recusadas, não
        agora[0] = segundo
        with pytest.raises(ErroDePolitica):
            await executar([quota], CtxFalso())
    agora[0] = 171.0
    assert await executar([quota], CtxFalso()) == "ok"


def test_quota_do_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISE_QUOTA_CHAMADAS", "40")
    monkeypatch.setenv("MISE_QUOTA_JANELA_MIN", "5")
    quota = Quota.do_ambiente()
    assert (quota.maximo, quota.janela_segundos) == (40, 300.0)
    pilha = pilha_padrao()
    (na_pilha,) = [m for m in pilha if isinstance(m, Quota)]
    assert na_pilha.maximo == 40


@pytest.mark.parametrize("bruto", ["", "zero", "-3", "0", "2.5"])
def test_quota_do_ambiente_ignora_valor_invalido(
    monkeypatch: pytest.MonkeyPatch, bruto: str
) -> None:
    monkeypatch.setenv("MISE_QUOTA_CHAMADAS", bruto)
    monkeypatch.setenv("MISE_QUOTA_JANELA_MIN", bruto)
    quota = Quota.do_ambiente()
    assert (quota.maximo, quota.janela_segundos) == (500, 3600.0)


def test_quota_sem_ambiente_usa_o_padrao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISE_QUOTA_CHAMADAS", raising=False)
    monkeypatch.delenv("MISE_QUOTA_JANELA_MIN", raising=False)
    assert (Quota.do_ambiente().maximo, Quota().janela_segundos) == (500, 3600.0)


@pytest.mark.parametrize(("maximo", "janela"), [(0, 60.0), (5, 0.0)])
def test_quota_sem_sentido_e_recusada(maximo: int, janela: float) -> None:
    with pytest.raises(ValueError, match="janela positiva"):
        Quota(maximo=maximo, janela_segundos=janela)


# --------------------------------------------------------------------------- #
# Circuit breaker
# --------------------------------------------------------------------------- #


async def test_breaker_abre_apos_falhas_seguidas() -> None:
    breaker = CircuitBreaker(limite_falhas=3, espera_segundos=60)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await executar([breaker], CtxFalso(), final=explode)

    assert breaker.estado("custo_unitario") is EstadoBreaker.ABERTO
    with pytest.raises(ErroDePolitica) as exc:
        await executar([breaker], CtxFalso(), final=explode)
    assert exc.value.codigo == "circuito_aberto"


async def test_sucesso_zera_o_contador() -> None:
    breaker = CircuitBreaker(limite_falhas=2)
    with pytest.raises(RuntimeError):
        await executar([breaker], CtxFalso(), final=explode)
    await executar([breaker], CtxFalso())
    with pytest.raises(RuntimeError):
        await executar([breaker], CtxFalso(), final=explode)
    assert breaker.estado("custo_unitario") is EstadoBreaker.FECHADO


async def test_breaker_meio_aberto_apos_a_espera() -> None:
    breaker = CircuitBreaker(limite_falhas=1, espera_segundos=0.0)
    with pytest.raises(RuntimeError):
        await executar([breaker], CtxFalso(), final=explode)
    assert breaker.estado("custo_unitario") is EstadoBreaker.MEIO_ABERTO


async def test_breaker_nao_conta_recusa_de_politica() -> None:
    """Negar acesso não é falha do motor: não pode abrir o circuito."""
    breaker = CircuitBreaker(limite_falhas=1)

    async def nega(_ctx: Any) -> str:
        raise ErroDePolitica("negado", "teste")

    with pytest.raises(ErroDePolitica):
        await executar([breaker], CtxFalso(), final=nega)
    assert breaker.estado("custo_unitario") is EstadoBreaker.FECHADO


# --------------------------------------------------------------------------- #
# Auditoria
# --------------------------------------------------------------------------- #


async def test_auditoria_registra_sucesso() -> None:
    auditoria = Auditoria()
    await executar([auditoria], CtxFalso())
    evento = auditoria.memoria[-1]
    assert evento["ferramenta"] == "custo_unitario"
    assert evento["resultado"] == "ok"
    assert evento["duracao_ms"] >= 0


async def test_auditoria_registra_negacao() -> None:
    """Negação é o evento mais interessante do log: não pode faltar."""
    auditoria = Auditoria()
    ctx = CtxFalso(params={"name": "ferramenta_fantasma"})
    with pytest.raises(ErroDePolitica):
        await executar([auditoria, Autorizacao()], ctx)
    evento = auditoria.memoria[-1]
    assert evento["resultado"] == "negado"
    assert evento["codigo"] == "ferramenta_desconhecida"


async def test_auditoria_registra_erro_do_motor() -> None:
    auditoria = Auditoria()
    with pytest.raises(RuntimeError):
        await executar([auditoria], CtxFalso(), final=explode)
    assert auditoria.memoria[-1]["resultado"] == "erro"
    assert auditoria.memoria[-1]["tipo"] == "RuntimeError"


async def test_auditoria_grava_em_arquivo(tmp_path: Path) -> None:
    destino = tmp_path / "trilha" / "auditoria.jsonl"
    auditoria = Auditoria(destino=destino)
    await executar([auditoria], CtxFalso())
    await executar([auditoria], CtxFalso())

    linhas = destino.read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) == 2
    assert json.loads(linhas[0])["ferramenta"] == "custo_unitario"


async def test_auditoria_guarda_identidade(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISE_TOKEN", "tok")
    auth = Autenticacao(tokens={"tok": Credencial("agente-leitura", frozenset({Escopo.LEITURA}))})
    auditoria = Auditoria()
    await executar([auth, auditoria], CtxFalso())
    assert auditoria.memoria[-1]["identidade"] == "agente-leitura"


def test_auditoria_do_ambiente(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MISE_AUDITORIA", str(tmp_path / "a.jsonl"))
    assert Auditoria.do_ambiente().destino == tmp_path / "a.jsonl"
    monkeypatch.delenv("MISE_AUDITORIA")
    assert Auditoria.do_ambiente().destino is None


# --------------------------------------------------------------------------- #
# Pilha completa
# --------------------------------------------------------------------------- #


def test_ordem_da_pilha() -> None:
    """Autenticação primeiro; auditoria logo depois, para ver o que foi negado."""
    pilha = pilha_padrao()
    tipos = [type(m).__name__ for m in pilha]
    assert tipos == [
        "Autenticacao",
        "Auditoria",
        "Autorizacao",
        "RateLimit",
        "Quota",
        "CircuitBreaker",
    ]


async def test_pilha_completa_nega_e_audita(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISE_TOKEN", "r")
    auditoria = Auditoria()
    pilha = pilha_padrao(
        autenticacao=Autenticacao(tokens={"r": Credencial("leitor", frozenset({Escopo.LEITURA}))}),
        auditoria=auditoria,
    )
    with pytest.raises(ErroDePolitica) as exc:
        await executar(pilha, CtxFalso(params={"name": "registrar_compra"}))

    assert exc.value.codigo == "escopo_insuficiente"
    assert auditoria.memoria[-1]["resultado"] == "negado"
    assert auditoria.memoria[-1]["identidade"] == "leitor"


async def test_pilha_completa_deixa_passar_o_legitimo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISE_TOKEN", "w")
    auditoria = Auditoria()
    pilha = pilha_padrao(
        autenticacao=Autenticacao(
            tokens={"w": Credencial("escritor", frozenset({Escopo.LEITURA, Escopo.ESCRITA}))}
        ),
        auditoria=auditoria,
    )
    assert await executar(pilha, CtxFalso(params={"name": "registrar_compra"})) == "ok"
    assert auditoria.memoria[-1]["resultado"] == "ok"


def test_erro_de_politica_nao_vaza_interno() -> None:
    erro = ErroDePolitica("negado", "codigo_x", ferramenta="y")
    assert str(erro) == "negado"
    assert erro.codigo == "codigo_x"
    assert erro.contexto == {"ferramenta": "y"}
