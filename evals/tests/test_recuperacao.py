"""O conjunto dourado da busca, com o vetorizador determinístico: é o portão do CI.

O modelo semântico não roda aqui (nem é instalado no CI): a coluna dele sai de
`make evals-recuperacao` na máquina que tem o modelo. Os n-gramas dão o mesmo
resultado em qualquer máquina, e são eles que reprovam uma regressão.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from mise.corpus import montar_trechos
from mise.mcp_server import Sessao

from evals import recuperacao
from evals.recuperacao import (
    PISO,
    Caso,
    Relatorio,
    Resposta,
    acerto_de_abstencao,
    calibrar,
    carregar_casos,
    main,
    montar_estado,
    mrr,
    ndcg,
    relatorio,
    revocacao,
    rodar,
    tabela,
    vetorizador_ngramas,
)


@pytest.fixture(scope="module")
def sessao(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Sessao]:
    sessao = montar_estado(tmp_path_factory.mktemp("recuperacao"))
    yield sessao
    sessao.dossie.fechar()


def test_o_conjunto_tem_o_tamanho_e_os_trechos_existem(sessao: Sessao) -> None:
    casos = carregar_casos()
    assert 40 <= len(casos) <= 60
    assert sum(1 for c in casos if c.abster) >= 8
    existentes = {t.id for t in montar_trechos(sessao)}
    faltam = {e for c in casos for e in c.esperados} - existentes
    assert not faltam, f"trechos esperados que o corpus não tem: {faltam}"


def test_os_n_gramas_ficam_acima_do_piso(sessao: Sessao) -> None:
    relatorio_, respostas = rodar(sessao, vetorizador_ngramas(), carregar_casos())
    assert relatorio_.dentro_do_piso() == [], relatorio_
    fora = {r.caso.id for r in respostas if r.caso.abster and not r.absteve}
    conhecidos = {r.caso.id for r in respostas if r.caso.conhecido}
    assert fora <= conhecidos, f"pergunta de fora que ganhou resposta: {fora - conhecidos}"


def _resposta(caso: Caso, *ids: set[str]) -> Resposta:
    return Resposta(caso, tuple(frozenset(i) for i in ids), "", 1.0, 1.0, 1.0, 0.0)


def test_as_metricas_com_numeros_conhecidos() -> None:
    dois = Caso("a", "?", ("x", "y"))
    um = Caso("b", "?", ("z",))
    fora = Caso("c", "?", ())
    respostas = [
        _resposta(dois, {"q"}, {"x"}, {"y", "w"}),
        _resposta(um, {"q"}, {"q"}, {"q"}, {"q"}, {"q"}, {"z"}),
        _resposta(fora),
    ]
    assert revocacao(respostas) == pytest.approx((1.0 + 0.0) / 2)
    assert mrr(respostas) == pytest.approx((1 / 2 + 1 / 6) / 2)
    assert 0 < ndcg(respostas) < 1
    assert acerto_de_abstencao(respostas) == 1.0
    assert revocacao([]) == mrr([]) == ndcg([]) == acerto_de_abstencao([]) == 0.0
    assert respostas[2].absteve
    assert respostas[0].posicao("y") == 3


def test_relatorio_conta_os_erros() -> None:
    respondeu_o_que_nao_devia = _resposta(Caso("c", "?", ()), {"x"})
    nao_achou = _resposta(Caso("d", "?", ("z",)), {"x"})
    absteve = _resposta(Caso("e", "?", ("z",)))
    rel = relatorio("teste", [respondeu_o_que_nao_devia, nao_achou, absteve])
    assert len(rel.erros) == 3
    assert rel.acerto_abstencao == pytest.approx(1 / 3, abs=1e-3)
    assert rel.dentro_do_piso()
    vazio = relatorio("vazio", [])
    assert (vazio.latencia_p50_ms, vazio.latencia_p95_ms) == (0.0, 0.0)


def test_casos_com_id_repetido_nao_entram(tmp_path: Path) -> None:
    arquivo = tmp_path / "casos.yaml"
    arquivo.write_text("- {id: a, pergunta: x}\n- {id: a, pergunta: y}\n", "utf-8")
    with pytest.raises(ValueError, match="mesmo id"):
        carregar_casos(arquivo)


def test_tabela_mostra_a_coluna_indisponivel() -> None:
    rel = Relatorio("n", 1, 0.5, 0.25, 0.125, 1.0, 2.0, 3.0)
    texto = tabela([("n-gramas", rel), ("modelo", None)])
    assert "| revocação em 5 | 0,500 | indisponível |" in texto


def test_calibrar_devolve_limiares_que_acertam(sessao: Sessao) -> None:
    casos = [c for c in carregar_casos() if c.id in {"despensa-quanto-paguei", "fora-capital"}]
    limiares, rel = calibrar(sessao, vetorizador_ngramas(), casos)
    assert rel.acerto_abstencao == 1.0
    assert 0 < limiares.evidencia_minima <= limiares.evidencia_segura


def test_main_so_com_os_n_gramas_grava_o_relatorio(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saida = tmp_path / "recuperacao.json"
    assert main(["--vetorizador", "ngramas", "--saida", str(saida)]) == 0
    impresso = capsys.readouterr().out
    assert "n-gramas com hash" in impresso
    assert "dentro do piso" in impresso
    gravado = json.loads(saida.read_text("utf-8"))
    assert gravado["ngramas"]["revocacao_5"] >= PISO["revocacao_5"]


def test_main_sem_o_modelo_diz_que_ele_nao_esta_disponivel(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(recuperacao, "vetorizador_neural", lambda: None)
    monkeypatch.setattr(recuperacao, "carregar_casos", lambda: carregar_casos()[:3])
    assert main(["--vetorizador", "neural"]) == 0
    assert "indisponível" in capsys.readouterr().out


def test_main_com_o_modelo_que_nao_carrega_nao_finge_a_coluna(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(recuperacao, "vetorizador_neural", vetorizador_ngramas)
    monkeypatch.setattr(recuperacao, "carregar_casos", lambda: carregar_casos()[:3])
    assert main(["--vetorizador", "neural", "--calibrar"]) == 0
    impresso = capsys.readouterr().out
    assert "indisponível" in impresso
    assert "calibração (ngramas)" in impresso


def test_main_reprova_abaixo_do_piso(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(recuperacao, "PISO", {**PISO, "revocacao_5": 1.01})
    monkeypatch.setattr(recuperacao, "carregar_casos", lambda: carregar_casos()[:3])
    assert main(["--vetorizador", "ngramas"]) == 1
    assert "abaixo do piso" in capsys.readouterr().out


def test_o_modelo_so_quando_o_pacote_existe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda _nome: None)
    assert recuperacao.vetorizador_neural(tmp_path) is None
