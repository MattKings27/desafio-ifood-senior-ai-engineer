"""A redação das transcrições: troca só o que deve, e o JSON continua válido.

As conversas gravadas são relidas pelo teste do guard-rail. Se a redação mexesse
num número, ou quebrasse um arquivo, aquele teste conferiria outra coisa. Aqui
fica provado que ela troca só caminho local e o nome do canal, e que o
repositório não guarda transcrição sem redigir.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redigir_transcricoes as redacao

# Montados por partes, para que este arquivo não carregue um caminho local
# inteiro nem o nome do canal que saiu do escopo.
CASA = "/" + "home/alguem"
DISCO = "/" + "mnt/d/trabalho"
CANAL = "Whats" + "App"


@pytest.mark.parametrize(
    ("antes", "depois"),
    [
        (
            f"{DISCO}/desafio-ifood-senior-ai-engineer/mise/src/a.py",
            "<repo>/mise/src/a.py",
        ),
        (f"{DISCO}/worktrees/conta-e-portao/mise/tests", "<repo>/mise/tests"),
        (f"{DISCO}/sabor-da-maria", "<repo>"),
        (
            f"{CASA}/.hermes/profiles/sabor-da-maria-avaliacao/skills/a/SKILL.md",
            "<home>/.hermes/profiles/sabor-da-maria-avaliacao/skills/a/SKILL.md",
        ),
        (f"{CASA}/.cache/outra/coisa", "<home>/…"),
        (CASA, "<home>"),
        (DISCO, "<home>"),
        (f"Enviar por {CANAL}", "Enviar por [canal]"),
        (
            f"https://api.{CANAL.lower()}.com/send?text=Bolo",
            "https://api.[canal].com/send?text=Bolo",
        ),
    ],
)
def test_troca_cada_caminho_pelo_marcador(antes: str, depois: str) -> None:
    assert redacao.redigir_texto(antes) == depois


def test_nao_mexe_no_resto() -> None:
    texto = (
        "A senhora tem 37 itens e colocou R$ 663,39. Rota /api/conversas/{id}/turnos, "
        "fonte https://www.tudogostoso.com.br/receita/1-bolo.html, arquivo ./docs/LEIA.md."
    )
    assert redacao.redigir_texto(texto) == texto


def _gravar(arquivo: Path, dados: object) -> None:
    arquivo.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def test_caminho_dentro_de_json_aninhado(tmp_path: Path) -> None:
    saida = json.dumps(
        {"arquivo": f"{DISCO}/desafio-ifood-senior-ai-engineer/dados/x.xlsx"}
    )
    arquivo = tmp_path / "execucao-1.json"
    _gravar(
        arquivo,
        {"turnos": [{"resposta": "Custa R$ 7,00.", "chamadas": [{"saida": saida}]}]},
    )

    resultado = redacao.redigir_pasta(tmp_path, gravar=True)

    assert resultado.alterados == [arquivo]
    assert resultado.trocas == 1
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    assert dados["turnos"][0]["resposta"] == "Custa R$ 7,00."
    assert json.loads(dados["turnos"][0]["chamadas"][0]["saida"]) == {
        "arquivo": "<repo>/dados/x.xlsx"
    }
    assert redacao.redigir_pasta(tmp_path, gravar=True).alterados == []


def test_jsonl_linha_a_linha(tmp_path: Path) -> None:
    arquivo = tmp_path / "amostra.jsonl"
    linhas = [
        {"seq": 1, "delta": f"lido de {CASA}/x"},
        {"seq": 2, "delta": "sem caminho"},
    ]
    arquivo.write_text(
        "".join(json.dumps(linha, ensure_ascii=False) + "\n" for linha in linhas),
        encoding="utf-8",
    )

    redacao.redigir_pasta(tmp_path, gravar=True)

    lidas = [json.loads(linha) for linha in arquivo.read_text("utf-8").splitlines()]
    assert lidas == [
        {"seq": 1, "delta": "lido de <home>/…"},
        {"seq": 2, "delta": "sem caminho"},
    ]


def test_recusa_json_que_nao_volta_no_mesmo_formato(tmp_path: Path) -> None:
    arquivo = tmp_path / "x.json"
    bruto = '{"a":   "' + CASA + '"}'
    arquivo.write_text(bruto, encoding="utf-8")

    with pytest.raises(ValueError, match="formato de JSON desconhecido"):
        redacao.redigir_pasta(tmp_path, gravar=True)
    assert arquivo.read_text(encoding="utf-8") == bruto


def test_as_transcricoes_do_repositorio_estao_redigidas(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Quem gravar conversa nova roda a redação antes de versionar."""
    assert redacao.main(["--conferir"]) == 0, capsys.readouterr().out
