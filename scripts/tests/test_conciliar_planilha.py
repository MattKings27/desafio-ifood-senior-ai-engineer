"""A conciliação com a planilha: o arquivo de verdade, lido cru, contra a plataforma inteira.

`dados/despensa_dona_maria.xlsx` é, byte a byte, a planilha que a Dona Maria
entregou (o sha256 está aqui). A conciliação lê as duas abas com o openpyxl, faz
a conta de referência de novo e compara com o que a plataforma mostra, num
dossiê novo: zero divergência. Uma mudança dela na despensa já é divergência, e
o código de saída diz isso.
"""

from __future__ import annotations

import hashlib
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import conciliar_planilha as conciliacao

#: O sha256 da planilha original: qualquer mudança no arquivo reprova aqui.
SHA256_DA_PLANILHA = "56df15d6fd2da64901534b48124ab1da43428849e019607577ead1211db3c8d2"


def test_a_planilha_e_a_original_byte_a_byte() -> None:
    assert (
        hashlib.sha256(conciliacao.PLANILHA.read_bytes()).hexdigest()
        == SHA256_DA_PLANILHA
    )


def test_a_leitura_crua_das_duas_abas() -> None:
    linhas = conciliacao.ler_planilha()
    assert len(linhas) == 37
    assert sum((linha.pago for linha in linhas), Decimal(0)) == Decimal("663.39")
    por_nome = {linha.nome: linha for linha in linhas}
    alcaparras = por_nome["Alcaparras"]
    assert (alcaparras.comprado_na_base, alcaparras.custo_texto) == (
        Decimal(2),
        "R$ 41,00/kg",
    )
    azeite = por_nome["Azeite de oliva extra virgem"]
    assert (azeite.comprado_na_base, azeite.custo) == (Decimal("0.5"), Decimal("61.98"))
    ovos = por_nome["Ovos"]
    assert (ovos.unidade_da_compra.base, ovos.custo) == ("un", Decimal("0.8"))
    cobertura = por_nome["Cobertura de chocolate"]
    assert cobertura.sem_peso
    assert cobertura.custo is None


@pytest.mark.parametrize(
    ("rotulo", "fator", "base"),
    [
        ("kg", Decimal(1), "kg"),
        ("g", Decimal("0.001"), "kg"),
        ("L", Decimal(1), "L"),
        ("balde 2kg", Decimal(2), "kg"),
        ("un 500g", Decimal("0.5"), "kg"),
        ("un 100ml", Decimal("0.1"), "L"),
        ("un", Decimal(1), "un"),
    ],
)
def test_a_unidade_normalizada(rotulo: str, fator: Decimal, base: str) -> None:
    unidade = conciliacao.interpretar(rotulo)
    assert (unidade.fator, unidade.base) == (fator, base)


def test_unidade_que_ninguem_le_e_erro() -> None:
    with pytest.raises(ValueError, match="não sei ler"):
        conciliacao.interpretar("pacote grande")


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("1 balde de 2 kg por R$ 82,00", (Decimal(2), Decimal("82.00"))),
        ("30 unidades por R$ 24,00", (Decimal(30), Decimal("24.00"))),
        ("200 g por R$ 2,16", (Decimal("0.2"), Decimal("2.16"))),
        ("1 embalagem de 500 ml por R$ 30,99", (Decimal("0.5"), Decimal("30.99"))),
        ("1 embalagem por R$ 79,90", (Decimal(1), Decimal("79.90"))),
        ("1,5 kg por R$ 42,00", (Decimal("1.5"), Decimal("42.00"))),
        ("uma coisa qualquer", None),
    ],
)
def test_a_compra_como_a_tela_escreve(
    texto: str, esperado: tuple[Decimal, Decimal] | None
) -> None:
    assert conciliacao.comprado_do_texto(texto) == esperado


def test_a_plataforma_num_dossie_novo_bate_com_a_planilha() -> None:
    with conciliacao.fonte_em_processo() as fonte:
        relatorio = conciliacao.conciliar(fonte)
    assert relatorio.divergencias == []
    texto = relatorio.texto(fonte.descricao)
    assert "0 divergências" in texto
    assert "Total pago: R$ 663,39" in texto
    assert "Complementos: R$ 80,00, restam R$ 80,00" in texto
    assert "Cobertura de chocolate: 1 un em estoque" in texto
    # A embalagem sem peso na planilha não vira pergunta: o peso vem estimado, com a fonte.
    assert "peso estimado pela página do supermercado, com a fonte" in texto
    assert "0 respondidos pela senhora" in texto
    assert "nenhum prato no cardápio" in texto
    assert len(relatorio.itens) == 37


def test_uma_mudanca_dela_na_despensa_e_divergencia() -> None:
    with conciliacao.fonte_em_processo() as fonte:
        fonte.sessao.editavel.corrigir("arroz-branco-tipo-1", estoque=Decimal(4))
        relatorio = conciliacao.conciliar(fonte)
    assert any("Arroz branco tipo 1: estoque 4" in d for d in relatorio.divergencias)
    assert any("mudanças na despensa: 1" in d for d in relatorio.divergencias)


def test_depois_de_restaurar_a_plataforma_volta_a_bater_com_a_planilha() -> None:
    with conciliacao.fonte_em_processo() as fonte:
        cliente = fonte.cliente
        cliente.put("/api/perfil/equipamentos/forno", json={"estado": "tem"})
        cliente.delete("/api/despensa/itens/sal")
        assert conciliacao.conciliar(fonte).divergencias
        resposta = cliente.post("/api/dados/restaurar", json={"confirmar": True}).json()
        assert resposta["ok"], resposta
        relatorio = conciliacao.conciliar(fonte)
    assert relatorio.divergencias == []


def test_o_codigo_de_saida(capsys: pytest.CaptureFixture[str]) -> None:
    assert conciliacao.main([]) == 0
    assert "0 divergências" in capsys.readouterr().out


def test_api_fora_do_ar_nao_conclui(capsys: pytest.CaptureFixture[str]) -> None:
    assert conciliacao.main(["--api", "http://127.0.0.1:9"]) == 1
    assert "não consegui conciliar" in capsys.readouterr().err
