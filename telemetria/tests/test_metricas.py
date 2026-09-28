"""Latência agregada.

O que estes testes protegem é a razão de a métrica existir: **percentil, não
média**. Um p50 de 200 ms com p99 de 9 s é um sistema em que uma pessoa a cada
cem espera nove segundos, e a média diria 300 ms.
"""

from __future__ import annotations

import threading

import pytest

from telemetria.metricas import JANELA, Registro, Serie


@pytest.fixture
def serie() -> Serie:
    s = Serie("teste")
    for valor in range(1, 101):  # 1..100
        s.registrar(float(valor))
    return s


def test_percentis_de_uma_distribuicao_conhecida(serie: Serie) -> None:
    assert serie.p50 == pytest.approx(50.5, abs=0.6)
    assert serie.p95 == pytest.approx(95.05, abs=0.6)
    assert serie.p99 == pytest.approx(99.01, abs=0.6)


def test_a_media_esconderia_a_cauda() -> None:
    """O caso concreto: 90% rápidas, 10% muito lentas.

    A média fica em 590 ms e parece aceitável. O p95 mostra que uma em cada vinte
    pessoas espera cinco segundos, e é essa que abandona a conversa.

    (Um exemplo com uma única amostra lenta em cem **não** serve: o p99 cai
    exatamente na fronteira e interpola para perto da média. Percentil mede a
    forma da cauda, não a existência de um ponto isolado.)
    """
    s = Serie("com cauda")
    for _ in range(900):
        s.registrar(100.0)
    for _ in range(100):
        s.registrar(5000.0)

    media = sum(s.amostras) / len(s.amostras)
    assert media == pytest.approx(590, abs=1)
    assert s.p50 == pytest.approx(100, abs=1)
    assert s.p95 == pytest.approx(5000, abs=1)
    assert s.p99 == pytest.approx(5000, abs=1)


def test_serie_vazia_devolve_zero() -> None:
    assert Serie("vazia").p95 == 0.0
    assert Serie("vazia").taxa_de_erro == 0.0


def test_uma_amostra_so() -> None:
    s = Serie("uma")
    s.registrar(42.0)
    assert s.p50 == s.p95 == s.p99 == 42.0


def test_janela_limita_a_memoria() -> None:
    """Guardar toda amostra cresce sem limite num processo que roda por semanas."""
    s = Serie("longa")
    for i in range(JANELA + 500):
        s.registrar(float(i))
    assert len(s.amostras) == JANELA
    assert s.total == JANELA + 500  # o contador não é truncado


def test_taxa_de_erro() -> None:
    s = Serie("com erro")
    for i in range(10):
        s.registrar(10.0, erro=(i < 3))
    assert s.taxa_de_erro == pytest.approx(0.3)


def test_texto_da_serie_traz_os_tres_percentis(serie: Serie) -> None:
    texto = str(serie)
    assert "p50" in texto
    assert "p95" in texto
    assert "p99" in texto


# --------------------------------------------------------------------------- #
# Registro                                                                     #
# --------------------------------------------------------------------------- #


def test_mais_lentas_ordena_por_p95() -> None:
    """É por onde qualquer investigação de latência começa."""
    r = Registro()
    for _ in range(20):
        r.registrar("rapida", 10.0)
        r.registrar("lenta", 900.0)
        r.registrar("media", 200.0)

    assert [s.nome for s in r.mais_lentas(3)] == ["lenta", "media", "rapida"]


def test_registro_e_seguro_entre_threads() -> None:
    """A API HTTP roda endpoints síncronos num threadpool.

    Sem trava, duas requisições simultâneas corrompem a contagem, e corrompem em
    silêncio, que é o pior jeito de uma métrica estar errada.
    """
    r = Registro()

    def marretar() -> None:
        for _ in range(500):
            r.registrar("concorrente", 5.0)

    threads = [threading.Thread(target=marretar) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    serie = r.serie("concorrente")
    assert serie is not None
    assert serie.total == 4000


def test_serie_inexistente_devolve_none() -> None:
    assert Registro().serie("nunca vista") is None


def test_prometheus_tem_o_formato_esperado() -> None:
    r = Registro()
    r.registrar("custo_unitario", 40.0)
    r.registrar("custo_unitario", 60.0, erro=True)

    saida = r.prometheus()
    assert "# TYPE sabor_ferramenta_duracao_ms summary" in saida
    assert 'ferramenta="custo_unitario",quantile="0.5"' in saida
    assert 'sabor_ferramenta_duracao_ms_count{ferramenta="custo_unitario"} 2' in saida
    assert 'sabor_ferramenta_erros_total{ferramenta="custo_unitario"} 1' in saida
    assert saida.endswith("\n")


def test_prometheus_escapa_aspas_no_rotulo() -> None:
    """Nome com aspas quebraria o formato e o scraper recusaria a série inteira."""
    r = Registro()
    r.registrar('com"aspas', 10.0)
    assert '\\"aspas' in r.prometheus()


def test_resumo_vazio() -> None:
    assert "nenhuma chamada" in Registro().resumo()


def test_resumo_lista_todas_as_series() -> None:
    r = Registro()
    r.registrar("a", 10.0)
    r.registrar("b", 20.0)
    resumo = r.resumo()
    assert "a:" in resumo
    assert "b:" in resumo


def test_limpar_zera_as_series() -> None:
    """Existe para teste: global sem como zerar é global difícil de testar."""
    r = Registro()
    r.registrar("x", 10.0, erro=True)
    assert r.serie("x") is not None

    r.limpar()
    assert r.serie("x") is None
    assert r.todas() == ()
