"""Testes da válvula de escape.

O caso central não é o override aceito: é a label sem justificativa. Se ele
passar batido, a exigência vira decorativa.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import override_de_cobertura as valvula

SECAO = "## Coverage override justification"


def _evento(tmp_path: Path, rotulos: list[str], corpo: str) -> Path:
    caminho = tmp_path / "evento.json"
    caminho.write_text(
        json.dumps(
            {"pull_request": {"labels": [{"name": r} for r in rotulos], "body": corpo}}
        ),
        encoding="utf-8",
    )
    return caminho


def _rodar(monkeypatch, caminho: Path) -> int:
    monkeypatch.setattr(sys, "argv", ["override", "--evento", str(caminho)])
    return valvula.main()


def test_sem_label_o_portao_normal_decide(tmp_path, monkeypatch) -> None:
    assert _rodar(monkeypatch, _evento(tmp_path, [], "qualquer coisa")) == 3


def test_label_com_justificativa_aceita(tmp_path, monkeypatch) -> None:
    corpo = f"## O que muda\nalgo\n\n{SECAO}\nMigracao gerada por ferramenta, sem ramo proprio."
    assert _rodar(monkeypatch, _evento(tmp_path, ["coverage-override"], corpo)) == 0


def test_label_sem_secao_falha_alto(tmp_path, monkeypatch) -> None:
    """O caso que a implementação existe para pegar."""
    assert (
        _rodar(
            monkeypatch, _evento(tmp_path, ["coverage-override"], "## O que muda\nalgo")
        )
        == 1
    )


def test_justificativa_curta_nao_serve(tmp_path, monkeypatch) -> None:
    assert (
        _rodar(monkeypatch, _evento(tmp_path, ["coverage-override"], f"{SECAO}\ncurta"))
        == 1
    )


def test_so_o_comentario_do_template_nao_conta(tmp_path, monkeypatch) -> None:
    """Quem deixa o template intacto não justificou nada."""
    corpo = f"{SECAO}\n<!-- explique aqui por que esta mudanca dispensa cobertura -->"
    assert _rodar(monkeypatch, _evento(tmp_path, ["coverage-override"], corpo)) == 1


def test_label_com_caixa_e_espaco_diferentes(tmp_path, monkeypatch) -> None:
    corpo = f"{SECAO}\nRefatoracao pura, comportamento coberto pelos testes existentes."
    assert _rodar(monkeypatch, _evento(tmp_path, ["  Coverage-Override "], corpo)) == 0


def test_titulo_em_qualquer_nivel(tmp_path, monkeypatch) -> None:
    corpo = (
        "### coverage override JUSTIFICATION\nArquivo gerado, nao ha o que testar aqui."
    )
    assert _rodar(monkeypatch, _evento(tmp_path, ["coverage-override"], corpo)) == 0


def test_para_no_proximo_titulo(tmp_path, monkeypatch) -> None:
    corpo = (
        f"{SECAO}\ncurta\n\n## Riscos\ntexto longo o suficiente para enganar a contagem"
    )
    assert _rodar(monkeypatch, _evento(tmp_path, ["coverage-override"], corpo)) == 1


def test_corpo_nulo_nao_quebra(tmp_path, monkeypatch) -> None:
    caminho = tmp_path / "e.json"
    caminho.write_text(
        json.dumps(
            {"pull_request": {"labels": [{"name": "coverage-override"}], "body": None}}
        ),
        encoding="utf-8",
    )
    assert _rodar(monkeypatch, caminho) == 1


def test_evento_ilegivel_falha(tmp_path, monkeypatch) -> None:
    caminho = tmp_path / "ruim.json"
    caminho.write_text("{nao e json", encoding="utf-8")
    assert _rodar(monkeypatch, caminho) == 1
