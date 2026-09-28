"""A prova dos preços de referência e das medidas do IBGE: sem rede, com o que foi gravado.

`make conferir-referencias` busca as páginas de verdade. Aqui a mesma prova roda
com o JSON-LD gravado de cada produto e as linhas gravadas da tabela do IBGE:
preço mudado no arquivo, produto trocado ou linha inventada reprovam.
"""

from __future__ import annotations

import io
import json
import struct
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import conferir_referencias as conferencia


def test_todo_numero_de_referencia_tem_prova_gravada() -> None:
    lista = conferencia.citacoes()
    resultado, fontes = conferencia.conferir(lista, conferencia.ler_gravadas())
    sem_prova = [(c.id, problema) for c, problema in resultado if problema]
    assert not sem_prova
    assert len({c.url for c in lista}) == len(fontes)
    precos = [c for c in lista if c.tipo == "preco"]
    medidas = [c for c in lista if c.tipo == "linha"]
    assert len(precos) >= 150, "cada preço de referência tem várias fontes de São Paulo"
    assert len(medidas) >= 20
    ids = [c.id for c in lista]
    assert len(ids) == len(set(ids))


def test_o_arquivo_de_precos_tem_a_forma_que_o_motor_le() -> None:
    from mise.referencias import precos_do_arquivo

    dados = json.loads(conferencia.PRECOS.read_text("utf-8"))
    lidos = precos_do_arquivo(dados["precos"])
    assert len(lidos.precos) == len(dados["precos"]), "nenhum preço recusado pelo motor"
    for preco in lidos.precos:
        assert all(f.api.startswith("https://") for f in preco.fontes)
        assert preco.texto.startswith(
            ("preço médio em São Paulo: R$ ", "preço em São Paulo: R$ ")
        )
        assert preco.texto.endswith("; a senhora pode corrigir")
    sites = {m["site"] for m in dados["mercados"]}
    assert len(sites) >= 3
    assert all(m["cep"][:2] in {"01", "13", "14"} for m in dados["mercados"])


def test_preco_mudado_no_arquivo_perde_a_prova(tmp_path: Path) -> None:
    dados = json.loads(conferencia.PRECOS.read_text("utf-8"))
    fonte = dados["precos"][0]["fontes"][0]
    fonte["preco"] = "0.99"
    fonte["trecho"] = '"Price":0.99'
    arquivo = tmp_path / "precos.json"
    arquivo.write_text(json.dumps(dados, ensure_ascii=False), "utf-8")
    resultado, _ = conferencia.conferir(
        conferencia.citacoes(arquivo), conferencia.ler_gravadas()
    )
    assert resultado[0][1].startswith("o preço mudou")


def test_produto_trocado_e_linha_inventada_nao_provam() -> None:
    ler = conferencia.ler_gravadas()
    original = conferencia.citacoes()
    preco = next(c for c in original if c.tipo == "preco")
    linha = next(c for c in original if c.tipo == "linha")
    trocado = conferencia.Citacao(
        preco.id,
        preco.url,
        "preco",
        preco.trecho,
        registro={**preco.registro, "produto": "Outro produto 200g"},
    )
    inventada = conferencia.Citacao(
        linha.id, linha.url, "linha", linha.trecho + " | 999"
    )
    resultado, _ = conferencia.conferir([trocado, inventada], ler)
    assert resultado[0][1].startswith("o produto da resposta é outro")
    assert resultado[1][1] == "a linha não está mais na tabela"


def test_fonte_que_nao_foi_gravada_nao_prova(tmp_path: Path) -> None:
    arquivo = tmp_path / "gravadas.json"
    arquivo.write_text(json.dumps({"gravado_em": "2026-09-27", "fontes": {}}), "utf-8")
    lista = [
        conferencia.Citacao("x:1", "https://exemplo.com.br/a", "linha", "um trecho")
    ]
    resultado, fontes = conferencia.conferir(lista, conferencia.ler_gravadas(arquivo))
    assert fontes == {}
    assert "não foi gravada" in resultado[0][1]


def test_gravar_guarda_so_o_produto_da_resposta(tmp_path: Path) -> None:
    preco = next(c for c in conferencia.citacoes() if c.tipo == "preco")
    resposta = json.dumps(
        {
            "products": [
                {"productId": "outro", "productName": "x"},
                {
                    "productId": preco.registro["id"],
                    "productName": preco.registro["produto"],
                    "description": "texto longo que não se guarda",
                    "items": [
                        {
                            "measurementUnit": "kg"
                            if preco.registro["a_granel"]
                            else "un",
                            "unitMultiplier": 1,
                            "sellers": [
                                {
                                    "commertialOffer": {
                                        "Price": float(preco.registro["preco"]),
                                        "AvailableQuantity": 5,
                                    }
                                }
                            ],
                        }
                    ],
                },
            ]
        },
        separators=(",", ":"),
    )
    destino = tmp_path / "gravadas.json"
    conferencia.gravar(
        [preco], {preco.url: resposta}, destino, conferencia.dt.date(2026, 9, 27)
    )
    gravado = json.loads(destino.read_text("utf-8"))
    (prova,) = gravado["fontes"][preco.url]["prova"]
    assert "description" not in prova
    resultado, _ = conferencia.conferir([preco], conferencia.ler_gravadas(destino))
    assert resultado[0][1] == ""


def test_atualizar_refaz_as_fontes_pela_busca_e_tira_o_que_nao_tem(
    tmp_path: Path,
) -> None:
    from retrieval.precos import Mercado, Pesquisa

    mercado = Mercado("Mambo", "www.mambo.com.br", "01310-100", "São Paulo")
    produto = {
        "productId": "7",
        "productName": "Creme de Leite Italac 200g",
        "linkText": "creme-de-leite-italac-200g",
        "items": [
            {
                "measurementUnit": "un",
                "unitMultiplier": 1,
                "sellers": [
                    {"commertialOffer": {"Price": 3.49, "AvailableQuantity": 9}}
                ],
            }
        ],
    }

    def ler(url: str, _cabecalhos: object) -> str:
        if "regions" in url:
            return json.dumps([{"id": "v2.A", "sellers": [{"id": "l"}]}])
        if "creme" in url:
            return json.dumps({"products": [produto]})
        return json.dumps({"products": []})

    arquivo = tmp_path / "precos.json"
    arquivo.write_text(
        json.dumps(
            {
                "precos": [
                    {
                        "ingrediente": "creme de leite",
                        "embalagem": "caixinha",
                        "busca": {
                            "termo": "creme de leite",
                            "exigir": ["creme", "leite"],
                        },
                        "fontes": [],
                    },
                    {
                        "ingrediente": "trufa",
                        "embalagem": "pacote",
                        "busca": {"termo": "trufa branca"},
                        "fontes": [],
                    },
                    {
                        "ingrediente": "fica",
                        "embalagem": "pacote",
                        "fontes": [{"x": 1}],
                    },
                ]
            }
        ),
        "utf-8",
    )
    pesquisa = Pesquisa([mercado], ler, conferencia.dt.date(2026, 9, 27))
    avisos = conferencia.atualizar(arquivo, pesquisa, ["creme de leite", "trufa"])
    dados = json.loads(arquivo.read_text("utf-8"))
    assert [p["ingrediente"] for p in dados["precos"]] == ["creme de leite", "fica"]
    assert dados["precos"][0]["fontes"][0]["produto"] == "Creme de Leite Italac 200g"
    assert avisos == [
        "creme de leite: só 1 mercado de São Paulo tem",
        "trufa: nenhum mercado de São Paulo tem, saiu",
    ]


def _xls_minimo() -> bytes:
    """Uma planilha .xls de uma aba, com duas linhas: o bastante para o leitor."""
    textos = ["CEBOLA", "Cebola - unidade média"]
    sst = struct.pack("<II", 2, 2) + b"".join(
        struct.pack("<HB", len(t), 0) + t.encode("latin-1") for t in textos
    )
    registros = [
        (0x0809, b"\x00" * 16),
        (0x00FC, sst),
        (0x0809, b"\x00" * 16),
        (0x0203, struct.pack("<HHHd", 0, 0, 0, 6705701.0)),
        (0x00FD, struct.pack("<HHHI", 0, 1, 0, 0)),
        (0x027E, struct.pack("<HHHI", 0, 2, 0, (70 << 2) | 0x02)),
        (0x00FD, struct.pack("<HHHI", 0, 3, 0, 1)),
        (0x00BD, struct.pack("<HHHIH", 1, 0, 0, (44 << 2) | 0x03, 0)),
        (0x000A, b""),
    ]
    livro = b"".join(struct.pack("<HH", t, len(d)) + d for t, d in registros)
    setor = 512
    livro += b"\x00" * (-len(livro) % setor)
    setores_do_livro = len(livro) // setor
    diretorio = setores_do_livro
    fat_setor = setores_do_livro + 1
    fat = list(range(1, setores_do_livro)) + [0xFFFFFFFE, 0xFFFFFFFE, 0xFFFFFFFD]
    fat += [0xFFFFFFFF] * (setor // 4 - len(fat))
    entrada = "Workbook".encode("utf-16-le") + b"\x00\x00"
    registro = entrada.ljust(64, b"\x00") + struct.pack("<HB", len(entrada), 2)
    registro = registro.ljust(0x74, b"\x00") + struct.pack("<II", 0, len(livro))
    registro = registro.ljust(128, b"\x00")
    cabecalho = bytearray(512)
    cabecalho[:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    struct.pack_into("<H", cabecalho, 0x1E, 9)
    struct.pack_into("<II", cabecalho, 0x2C, 1, diretorio)
    struct.pack_into("<II", cabecalho, 0x44, 0xFFFFFFFE, 0)
    difat = [fat_setor] + [0xFFFFFFFF] * 108
    struct.pack_into("<109I", cabecalho, 0x4C, *difat)
    dir_setor = registro.ljust(setor, b"\x00")
    fat_bytes = struct.pack(f"<{setor // 4}I", *fat)
    return bytes(cabecalho) + livro + dir_setor + fat_bytes


def test_o_leitor_de_xls_le_textos_numeros_e_rk() -> None:
    linhas = conferencia.celulas_do_xls(_xls_minimo())
    assert linhas == [[6705701.0, "CEBOLA", 70.0, "Cebola - unidade média"], [0.44]]
    pacote = io.BytesIO()
    with zipfile.ZipFile(pacote, "w") as zipado:
        zipado.writestr("tabela.xls", _xls_minimo())
    texto = conferencia.texto_da_tabela(pacote.getvalue())
    assert texto.splitlines() == [
        "6705701 | CEBOLA | 70 | Cebola - unidade média",
        "0.44",
    ]


def test_arquivo_que_nao_e_xls_e_recusado() -> None:
    with pytest.raises(ValueError, match="não é uma planilha"):
        conferencia.celulas_do_xls(b"PK\x03\x04 isso nao e um xls")
