"""Busca de página, com a resiliência que rede exige.

Nenhum teste aqui toca a rede. Um teste que depende da internet falha por motivo
que não é o seu, e teste que falha por motivo alheio é teste que alguém marca
como instável e ignora.

O relógio e o `sleep` são injetados: um teste de backoff que dorme de verdade
leva oito segundos e é o primeiro que as pessoas pulam.
"""

from __future__ import annotations

import urllib.error

import pytest

from retrieval.busca import (
    DESCANSO,
    FALHAS_PARA_ABRIR,
    TENTATIVAS,
    BuscaFalhou,
    CircuitoAberto,
    Disjuntor,
    UrlRecusada,
    baixar,
    espera_com_jitter,
    validar,
)


class AbridorFalso:
    """No lugar do abridor seguro: devolve ou levanta o que o teste mandar."""

    def __init__(self, fingir):
        self.fingir = fingir

    def open(self, requisicao, timeout=0):
        return self.fingir(requisicao, timeout=timeout)


class RelogioFalso:
    """Tempo controlado, para o circuito ser testável sem esperar."""

    def __init__(self) -> None:
        self.agora = 0.0

    def __call__(self) -> float:
        return self.agora

    def avancar(self, segundos: float) -> None:
        self.agora += segundos


# --------------------------------------------------------------------------- #
# Validação de URL                                                             #
# --------------------------------------------------------------------------- #


def test_url_valida_devolve_o_dominio() -> None:
    assert validar("https://www.tudogostoso.com.br/receita/9") == "www.tudogostoso.com.br"


@pytest.mark.parametrize(
    "perigosa",
    ["file:///etc/passwd", "ftp://exemplo.com", "gopher://x", "sem-esquema", "https://"],
)
def test_url_perigosa_e_recusada_antes_de_abrir_conexao(perigosa: str) -> None:
    """A URL vem do modelo, que a leu de uma página.

    Tratar isso como dado confiável é o caminho para `file:///etc/passwd` virar
    uma requisição, e a recusa acontece **antes** de qualquer socket abrir.
    """
    with pytest.raises(UrlRecusada):
        validar(perigosa)


def test_dominio_e_normalizado_para_minuscula() -> None:
    """Senão o disjuntor trataria `Site.com` e `site.com` como domínios diferentes."""
    assert validar("https://TudoGostoso.COM.br/x") == "tudogostoso.com.br"


# --------------------------------------------------------------------------- #
# Backoff                                                                      #
# --------------------------------------------------------------------------- #


def test_backoff_cresce_exponencialmente() -> None:
    esperas = [espera_com_jitter(n, lambda: 1.0) for n in range(4)]
    assert esperas == [0.5, 1.0, 2.0, 4.0]


def test_backoff_tem_teto() -> None:
    """Sem teto, a quinta tentativa esperaria mais do que ela aguenta."""
    assert espera_com_jitter(10, lambda: 1.0) == 4.0


def test_jitter_espalha_de_verdade() -> None:
    """Jitter completo: `random() · limite`, não `limite ± pouco`.

    Jitter parcial deixa os clientes agrupados, que é o efeito manada que
    transforma indisponibilidade curta em longa.
    """
    assert espera_com_jitter(3, lambda: 0.0) == 0.0
    assert espera_com_jitter(3, lambda: 1.0) == 4.0


# --------------------------------------------------------------------------- #
# Retry                                                                        #
# --------------------------------------------------------------------------- #


def _falhando(vezes: int, monkeypatch, sucesso: str = "<html>ok</html>"):
    """Faz `_baixar` falhar `vezes` e depois devolver `sucesso`."""
    estado = {"chamadas": 0}

    def fingir(_url: str) -> str:
        estado["chamadas"] += 1
        if estado["chamadas"] <= vezes:
            raise BuscaFalhou("servidor fora do ar")
        return sucesso

    monkeypatch.setattr("retrieval.busca._baixar", fingir)
    return estado


def test_sucesso_na_primeira_nao_repete(monkeypatch) -> None:
    estado = _falhando(0, monkeypatch)
    assert baixar("https://exemplo.com/x", Disjuntor(), dormir=lambda _: None)
    assert estado["chamadas"] == 1


def test_repete_e_acerta_na_terceira(monkeypatch) -> None:
    estado = _falhando(2, monkeypatch)
    assert baixar("https://exemplo.com/x", Disjuntor(), dormir=lambda _: None)
    assert estado["chamadas"] == TENTATIVAS


def test_desiste_depois_do_limite(monkeypatch) -> None:
    estado = _falhando(99, monkeypatch)
    with pytest.raises(BuscaFalhou, match="3 tentativas"):
        baixar("https://exemplo.com/x", Disjuntor(), dormir=lambda _: None)
    assert estado["chamadas"] == TENTATIVAS


def test_espera_entre_as_tentativas(monkeypatch) -> None:
    """Repetir imediatamente contra um servidor sobrecarregado piora a sobrecarga."""
    _falhando(2, monkeypatch)
    esperas: list[float] = []
    baixar("https://exemplo.com/x", Disjuntor(), dormir=esperas.append)

    assert len(esperas) == TENTATIVAS - 1  # não espera depois da última
    assert all(e >= 0 for e in esperas)


def test_erro_definitivo_nao_e_repetido(monkeypatch) -> None:
    """404 não vai melhorar tentando de novo; repetir só gasta tempo dela."""
    estado = {"chamadas": 0}

    def fingir(_url: str) -> str:
        estado["chamadas"] += 1
        raise UrlRecusada("HTTP 404, não adianta repetir")

    monkeypatch.setattr("retrieval.busca._baixar", fingir)
    with pytest.raises(UrlRecusada):
        baixar("https://exemplo.com/x", Disjuntor(), dormir=lambda _: None)
    assert estado["chamadas"] == 1


# --------------------------------------------------------------------------- #
# Circuit breaker                                                              #
# --------------------------------------------------------------------------- #


def test_circuito_abre_depois_de_falhas_seguidas(monkeypatch) -> None:
    _falhando(99, monkeypatch)
    relogio = RelogioFalso()
    disjuntor = Disjuntor(relogio=relogio)

    # Cada `baixar` que esgota as tentativas conta uma falha de domínio.
    for _ in range(FALHAS_PARA_ABRIR):
        with pytest.raises(BuscaFalhou):
            baixar("https://caido.com/x", disjuntor, dormir=lambda _: None)

    with pytest.raises(CircuitoAberto, match="descanso"):
        baixar("https://caido.com/x", disjuntor, dormir=lambda _: None)


def test_circuito_de_um_dominio_nao_afeta_outro(monkeypatch) -> None:
    """Um site de receita fora do ar não pode impedir a busca em todos."""
    _falhando(99, monkeypatch)
    disjuntor = Disjuntor(relogio=RelogioFalso())
    for _ in range(FALHAS_PARA_ABRIR):
        with pytest.raises(BuscaFalhou):
            baixar("https://caido.com/x", disjuntor, dormir=lambda _: None)

    assert disjuntor.permitido("outro.com")


def test_circuito_fecha_depois_do_descanso(monkeypatch) -> None:
    """Meio-aberto: depois do descanso, uma tentativa passa para testar."""
    _falhando(99, monkeypatch)
    relogio = RelogioFalso()
    disjuntor = Disjuntor(relogio=relogio)
    for _ in range(FALHAS_PARA_ABRIR):
        with pytest.raises(BuscaFalhou):
            baixar("https://caido.com/x", disjuntor, dormir=lambda _: None)

    assert not disjuntor.permitido("caido.com")
    relogio.avancar(DESCANSO + 1)
    assert disjuntor.permitido("caido.com")


def test_sucesso_zera_o_contador(monkeypatch) -> None:
    disjuntor = Disjuntor(relogio=RelogioFalso())
    disjuntor.registrar_falha("exemplo.com")
    disjuntor.registrar_falha("exemplo.com")

    _falhando(0, monkeypatch)
    baixar("https://exemplo.com/x", disjuntor, dormir=lambda _: None)
    assert disjuntor.falhas.get("exemplo.com") is None


def test_url_recusada_nao_abre_o_circuito(monkeypatch) -> None:
    """404 não é o site estar fora do ar: abrir o circuito puniria o inocente."""

    def fingir(_url: str) -> str:
        raise UrlRecusada("HTTP 404")

    monkeypatch.setattr("retrieval.busca._baixar", fingir)
    disjuntor = Disjuntor(relogio=RelogioFalso())
    for _ in range(FALHAS_PARA_ABRIR + 2):
        with pytest.raises(UrlRecusada):
            baixar("https://exemplo.com/x", disjuntor, dormir=lambda _: None)

    assert disjuntor.permitido("exemplo.com")


# --------------------------------------------------------------------------- #
# Tradução de erro HTTP                                                        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_status_temporario_vira_falha_repetivel(status: int) -> None:
    def fingir(requisicao, timeout=0):  # noqa: ARG001
        raise urllib.error.HTTPError("https://x", status, "ruim", {}, None)  # type: ignore[arg-type]

    abrir = AbridorFalso(fingir)
    from retrieval.busca import _baixar

    with pytest.raises(BuscaFalhou) as capturado:
        _baixar("https://exemplo.com/x", abrir)
    assert not isinstance(capturado.value, UrlRecusada)


@pytest.mark.parametrize("status", [400, 403, 404, 410])
def test_status_definitivo_nao_e_repetivel(status: int) -> None:
    def fingir(requisicao, timeout=0):  # noqa: ARG001
        raise urllib.error.HTTPError("https://x", status, "ruim", {}, None)  # type: ignore[arg-type]

    abrir = AbridorFalso(fingir)
    from retrieval.busca import _baixar

    with pytest.raises(UrlRecusada):
        _baixar("https://exemplo.com/x", abrir)


def test_timeout_vira_falha_repetivel() -> None:
    def fingir(requisicao, timeout=0):  # noqa: ARG001
        raise TimeoutError

    abrir = AbridorFalso(fingir)
    from retrieval.busca import _baixar

    with pytest.raises(BuscaFalhou, match="servidor"):
        _baixar("https://exemplo.com/x", abrir)


# --------------------------------------------------------------------------- #
# Leitura da resposta                                                          #
# --------------------------------------------------------------------------- #


class RespostaFalsa:
    """Uma resposta HTTP de mentira, com `read` limitado como o real."""

    def __init__(self, corpo: bytes) -> None:
        self.corpo = corpo

    def read(self, quanto: int) -> bytes:
        return self.corpo[:quanto]

    def __enter__(self) -> RespostaFalsa:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_pagina_normal_e_decodificada() -> None:
    abrir = AbridorFalso(lambda requisicao, timeout=0: RespostaFalsa("<html>Açaí</html>".encode()))  # noqa: ARG005
    from retrieval.busca import _baixar

    assert "Açaí" in _baixar("https://exemplo.com/x", abrir)


def test_byte_invalido_nao_derruba_a_busca() -> None:
    """Site com encoding errado existe, e não pode travar a conversa."""
    abrir = AbridorFalso(lambda requisicao, timeout=0: RespostaFalsa(b"<html>\xff\xfe</html>"))  # noqa: ARG005
    from retrieval.busca import _baixar

    assert "<html>" in _baixar("https://exemplo.com/x", abrir)


def test_pagina_gigante_e_recusada() -> None:
    """Quem controla o tamanho é o servidor remoto, não nós.

    Sem teto, uma resposta enorme consome memória até o processo morrer, e isso
    é uma negação de serviço que qualquer site pode causar de graça.
    """
    from retrieval.busca import TAMANHO_MAXIMO, _baixar

    abrir = AbridorFalso(lambda requisicao, timeout=0: RespostaFalsa(b"x" * (TAMANHO_MAXIMO + 10)))  # noqa: ARG005
    with pytest.raises(UrlRecusada, match="grande demais"):
        _baixar("https://exemplo.com/x", abrir)


def test_buscar_receita_junta_as_duas_metades(monkeypatch) -> None:
    """Buscar é problema de rede; extrair é problema de dado.

    Separados porque falham por razões diferentes, e o agente precisa dizer
    coisas diferentes: "não consegui acessar o site" e "esse site não publica a
    receita em formato estruturado" pedem ações diferentes dela.
    """
    from retrieval.busca import buscar_receita

    pagina = (
        '<script type="application/ld+json">'
        '{"@type":"Recipe","name":"Arroz da web","recipeIngredient":["1 xícara de arroz"],'
        '"recipeYield":"2"}</script>'
    )
    monkeypatch.setattr("retrieval.busca._baixar", lambda url: pagina)  # noqa: ARG005

    achada = buscar_receita(
        "https://www.tudogostoso.com.br/x", disjuntor=Disjuntor(), dormir=lambda _: None
    )
    assert achada.receita.nome == "Arroz da web"
    assert achada.receita.url == "https://www.tudogostoso.com.br/x"
    assert achada.fonte == "tudogostoso.com.br"
