"""Prova que cada preço de referência e cada medida caseira continuam na fonte.

Confere duas coisas que a plataforma usa no lugar de uma pergunta a ela:

- os preços de referência (`dados/precos_de_referencia.json`): cada fonte de
  cada preço é um produto num supermercado de São Paulo, com a consulta da API
  do mercado (a busca VTEX com a região de um CEP de São Paulo). A resposta tem
  de trazer o mesmo produto, com o mesmo nome, o mesmo preço no trecho literal
  (`"Price":3.79`), em estoque, vendido do mesmo jeito (a peso ou embalado);
- as medidas caseiras (`mise.unidades.MEDIDAS_DE_REFERENCIA`): a linha da
  tabela de medidas referidas do IBGE (POF 2008-2009, planilha `.xls` dentro de
  um `.zip`), letra por letra, lida por um leitor de `.xls` daqui mesmo; ou a
  linha da tabela de porções do USDA (FoodData Central, SR Legacy, `.csv`
  dentro de um `.zip`), "id | alimento | quantidade | medida | gramas";
- o peso estimado das embalagens que a planilha não diz
  (`mise.embalagens.EMBALAGENS_DE_REFERENCIA`): a página do produto, como a do
  preço, com o tamanho no nome e o preço que fez a escolha.

Consulta que não vem, preço que mudou ou linha que sumiu reprova: o número fica
sem prova.

    python scripts/conferir_referencias.py              # busca as fontes agora
    python scripts/conferir_referencias.py --gravar     # e grava a prova de cada uma
    python scripts/conferir_referencias.py --gravadas   # confere com o que foi gravado
    python scripts/conferir_referencias.py --atualizar  # refaz as fontes pela busca de agora

O que `--gravar` guarda (`scripts/tests/fixtures/referencias_paginas.json`) é o
produto de cada resposta de mercado e o pedaço da tabela do IBGE em volta de
cada linha citada, com a data: é com isso que os testes refazem a prova sem
rede. `--atualizar` procura de novo, com a busca guardada em cada preço
(`retrieval.precos`), e regrava as fontes: nunca inventa, e o preço sem mercado
nenhum sai do arquivo. A consulta se apresenta com um agente genérico, sem e-mail.
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import gzip
import io
import json
import struct
import sys
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

RAIZ: Final = Path(__file__).resolve().parents[1]
PRECOS: Final = RAIZ / "dados" / "precos_de_referencia.json"
GRAVADAS: Final = RAIZ / "scripts" / "tests" / "fixtures" / "referencias_paginas.json"

#: Quanto da tabela, antes e depois de cada linha citada, a gravação guarda.
MARGEM: Final = 200

#: Como a busca se apresenta: genérico, sem contato pessoal.
AGENTE: Final = "Mozilla/5.0 (compatible; SaborDaMaria-conferencia/1.0)"

#: A página mais longa que se aceita baixar, e o tempo máximo de espera.
TAMANHO_MAXIMO: Final = 8 * 1024 * 1024
TEMPO_LIMITE: Final = 30.0


# --------------------------------------------------------------------------- #
# Buscar                                                                       #
# --------------------------------------------------------------------------- #


def _ipv4_primeiro(host: str, porta: int) -> list[str]:
    """Os endereços do nome, o IPv4 primeiro: sem rota IPv6, o primeiro endereço não conecta."""
    from retrieval.rede import resolver_pelo_sistema

    return sorted(
        resolver_pelo_sistema(host, porta), key=lambda endereco: ":" in endereco
    )


def baixar(url: str) -> bytes:
    """Os bytes da página, pelo abridor seguro (só endereço público), já sem gzip."""
    from retrieval.rede import abridor

    requisicao = urllib.request.Request(
        url, headers={"User-Agent": AGENTE, "Accept": "text/html,application/zip,*/*"}
    )
    with abridor(_ipv4_primeiro).open(requisicao, timeout=TEMPO_LIMITE) as resposta:
        bruto: bytes = resposta.read(TAMANHO_MAXIMO + 1)
    if len(bruto) > TAMANHO_MAXIMO:
        raise urllib.error.URLError(f"página grande demais: {url}")
    return gzip.decompress(bruto) if bruto[:2] == b"\x1f\x8b" else bruto


# --------------------------------------------------------------------------- #
# A planilha .xls do IBGE                                                      #
# --------------------------------------------------------------------------- #

_OLE: Final = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_FIM_DA_CADEIA: Final = 0xFFFFFFFE
_REGISTRO_SST: Final = 0x00FC
_REGISTRO_CONTINUE: Final = 0x003C
_REGISTRO_BOF: Final = 0x0809
_REGISTRO_LABELSST: Final = 0x00FD
_REGISTRO_NUMBER: Final = 0x0203
_REGISTRO_RK: Final = 0x027E
_REGISTRO_MULRK: Final = 0x00BD
_FLUXO: Final = 2
_ENTRADA: Final = 128
_DIFAT_NO_CABECALHO: Final = 109


def _livro_do_xls(bruto: bytes) -> bytes:
    """O fluxo `Workbook` de um arquivo OLE2 (o `.xls` antigo)."""
    if not bruto.startswith(_OLE):
        raise ValueError("não é uma planilha .xls")
    tamanho = 1 << struct.unpack_from("<H", bruto, 0x1E)[0]
    setores_da_fat, inicio_do_diretorio = struct.unpack_from("<II", bruto, 0x2C)
    inicio_da_difat, setores_da_difat = struct.unpack_from("<II", bruto, 0x44)

    def setor(numero: int) -> bytes:
        return bruto[(numero + 1) * tamanho : (numero + 2) * tamanho]

    difat = list(struct.unpack_from(f"<{_DIFAT_NO_CABECALHO}I", bruto, 0x4C))
    proximo = inicio_da_difat
    for _ in range(setores_da_difat):
        entradas = struct.unpack(f"<{tamanho // 4}I", setor(proximo))
        difat.extend(entradas[:-1])
        proximo = entradas[-1]
    fat: list[int] = []
    for numero in difat[:setores_da_fat]:
        fat.extend(struct.unpack(f"<{tamanho // 4}I", setor(numero)))

    def cadeia(inicio: int) -> bytes:
        partes: list[bytes] = []
        numero = inicio
        while numero != _FIM_DA_CADEIA:
            if len(partes) > len(fat):
                raise ValueError("a cadeia de setores da planilha está quebrada")
            partes.append(setor(numero))
            numero = fat[numero]
        return b"".join(partes)

    diretorio = cadeia(inicio_do_diretorio)
    for inicio in range(0, len(diretorio), _ENTRADA):
        entrada = diretorio[inicio : inicio + _ENTRADA]
        nome_em_bytes = struct.unpack_from("<H", entrada, 0x40)[0]
        nome = entrada[: max(0, nome_em_bytes - 2)].decode("utf-16-le", "replace")
        if nome in ("Workbook", "Book") and entrada[0x42] == _FLUXO:
            primeiro, bytes_do_fluxo = struct.unpack_from("<II", entrada, 0x74)
            return cadeia(primeiro)[:bytes_do_fluxo]
    raise ValueError("a planilha .xls não tem o livro")


def _registros(livro: bytes) -> Iterator[tuple[int, bytes]]:
    posicao = 0
    while posicao + 4 <= len(livro):
        tipo, tamanho = struct.unpack_from("<HH", livro, posicao)
        yield tipo, livro[posicao + 4 : posicao + 4 + tamanho]
        posicao += 4 + tamanho


class _Pedacos:
    """Lê o SST por cima dos registros CONTINUE: o texto partido volta com o byte de opções."""

    def __init__(self, partes: list[bytes]) -> None:
        self.partes = partes
        self.indice = 0
        self.posicao = 0

    def ler(self, quantos: int) -> bytes:
        saida = b""
        while quantos > 0:
            while self.posicao >= len(self.partes[self.indice]):
                self.indice += 1
                self.posicao = 0
            pedaco = self.partes[self.indice][self.posicao : self.posicao + quantos]
            saida += pedaco
            self.posicao += len(pedaco)
            quantos -= len(pedaco)
        return saida

    def letras(self, quantas: int, largas: bool) -> str:
        saida: list[str] = []
        while quantas > 0:
            if self.posicao >= len(self.partes[self.indice]):
                self.indice += 1
                largas = bool(self.partes[self.indice][0] & 1)
                self.posicao = 1
            parte = self.partes[self.indice]
            largura = 2 if largas else 1
            cabem = min(quantas, (len(parte) - self.posicao) // largura)
            bruto = parte[self.posicao : self.posicao + cabem * largura]
            saida.append(bruto.decode("utf-16-le" if largas else "latin-1"))
            self.posicao += cabem * largura
            quantas -= cabem
        return "".join(saida)


def _textos_do_sst(partes: list[bytes]) -> list[str]:
    leitor = _Pedacos(partes)
    _, unicos = struct.unpack("<II", leitor.ler(8))
    textos: list[str] = []
    for _ in range(unicos):
        letras, opcoes = struct.unpack("<HB", leitor.ler(3))
        corridas = struct.unpack("<H", leitor.ler(2))[0] if opcoes & 0x08 else 0
        fonetica = struct.unpack("<i", leitor.ler(4))[0] if opcoes & 0x04 else 0
        textos.append(leitor.letras(letras, bool(opcoes & 0x01)))
        leitor.ler(4 * corridas + fonetica)
    return textos


def _rk(valor: int) -> float:
    if valor & 0x02:
        numero = float(struct.unpack("<i", struct.pack("<I", valor))[0] >> 2)
    else:
        numero = struct.unpack("<d", struct.pack("<Q", (valor & 0xFFFFFFFC) << 32))[0]
    return numero / 100 if valor & 0x01 else numero


def celulas_do_xls(bruto: bytes) -> list[list[object]]:
    """As linhas de todas as abas, só com as células que têm valor, na ordem da planilha."""
    registros = list(_registros(_livro_do_xls(bruto)))
    textos: list[str] = []
    for indice, (tipo, dados) in enumerate(registros):
        if tipo == _REGISTRO_SST:
            partes = [dados]
            for tipo_seguinte, seguinte in registros[indice + 1 :]:
                if tipo_seguinte != _REGISTRO_CONTINUE:
                    break
                partes.append(seguinte)
            textos = _textos_do_sst(partes)
            break
    linhas: dict[tuple[int, int], dict[int, object]] = {}
    aba = -1
    for tipo, dados in registros:
        if tipo == _REGISTRO_BOF:
            aba += 1
        elif tipo == _REGISTRO_LABELSST:
            linha, coluna, _, indice_do_texto = struct.unpack_from("<HHHI", dados)
            linhas.setdefault((aba, linha), {})[coluna] = textos[indice_do_texto]
        elif tipo == _REGISTRO_NUMBER:
            linha, coluna, _, numero = struct.unpack_from("<HHHd", dados)
            linhas.setdefault((aba, linha), {})[coluna] = numero
        elif tipo == _REGISTRO_RK:
            linha, coluna, _, valor = struct.unpack_from("<HHHI", dados)
            linhas.setdefault((aba, linha), {})[coluna] = _rk(valor)
        elif tipo == _REGISTRO_MULRK:
            linha, primeira = struct.unpack_from("<HH", dados)
            for k in range((len(dados) - 6) // 6):
                _, valor = struct.unpack_from("<HI", dados, 4 + 6 * k)
                linhas.setdefault((aba, linha), {})[primeira + k] = _rk(valor)
    return [
        [celulas[c] for c in sorted(celulas)] for _, celulas in sorted(linhas.items())
    ]


def _celula(valor: object) -> str:
    """ "70", "4.4", "CEBOLA": o número inteiro sem ".0", como a tabela mostra."""
    if isinstance(valor, float):
        return str(int(valor)) if valor.is_integer() else repr(valor)
    return str(valor).strip()


def texto_do_usda(pacote: zipfile.ZipFile) -> str:
    """Cada porção do SR Legacy do USDA: "id | alimento | quantidade | medida | gramas"."""
    import csv

    def ler(fim: str) -> list[dict[str, str]]:
        nome = next(n for n in pacote.namelist() if n.endswith(fim))
        return list(csv.DictReader(io.StringIO(pacote.read(nome).decode("utf-8"))))

    alimentos = {r["fdc_id"]: r["description"] for r in ler("/food.csv")}
    return "\n".join(
        " | ".join(
            (
                r["fdc_id"],
                alimentos.get(r["fdc_id"], ""),
                r["amount"],
                r["modifier"],
                r["gram_weight"],
            )
        )
        for r in ler("/food_portion.csv")
    )


def texto_da_tabela(bruto: bytes) -> str:
    """Cada linha da planilha do `.zip`, com as células separadas por " | ", uma por linha.

    O `.zip` do USDA traz `.csv`, e não `.xls`: cada porção vira uma linha, com
    a descrição do alimento (`texto_do_usda`).
    """
    with zipfile.ZipFile(io.BytesIO(bruto)) as pacote:
        if any(n.endswith("/food_portion.csv") for n in pacote.namelist()):
            return texto_do_usda(pacote)
        nome = next(n for n in pacote.namelist() if n.lower().endswith(".xls"))
        planilha = pacote.read(nome)
    linhas = (
        " | ".join(t for v in linha if (t := _celula(v)))
        for linha in celulas_do_xls(planilha)
    )
    return "\n".join(linha for linha in linhas if linha)


# --------------------------------------------------------------------------- #
# O que se cita                                                                #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Citacao:
    """Um número que a plataforma usa, e a fonte que tem de dizê-lo."""

    id: str
    url: str
    #: `preco` (o produto e o preço na resposta da API do mercado), `linha` (a
    #: linha da tabela do IBGE ou do USDA) ou `pagina` (o trecho literal na página
    #: do produto, como o preço no JSON-LD).
    tipo: str
    trecho: str
    #: A fonte do preço, como o arquivo guarda (`retrieval.precos.Fonte.registro`).
    registro: dict[str, Any] = field(default_factory=dict)


def _id_da_fonte(preco: dict[str, Any], fonte: dict[str, Any]) -> str:
    return f"preco:{preco['ingrediente']}:{preco['embalagem']}:{fonte['site']}"


def citacoes(precos: Path = PRECOS) -> list[Citacao]:
    """Cada fonte de cada preço de referência, as medidas caseiras e as embalagens do motor."""
    from mise.embalagens import EMBALAGENS_DE_REFERENCIA
    from mise.unidades import MEDIDAS_DE_REFERENCIA

    todas = [
        Citacao(_id_da_fonte(p, f), f["api"], "preco", f["trecho"], registro=f)
        for p in json.loads(precos.read_text("utf-8"))["precos"]
        for f in p.get("fontes", [])
    ]
    todas += [
        Citacao(
            f"medida:{m.ingredientes[0]}:{m.medida or 'unidade'}",
            m.fonte.url,
            "linha",
            m.trecho,
        )
        for m in MEDIDAS_DE_REFERENCIA
    ]
    todas += [
        Citacao(f"embalagem:{e.itens[0]}", e.url, "pagina", e.trecho)
        for e in EMBALAGENS_DE_REFERENCIA
    ]
    return todas


#: Lê a fonte pelo endereço: a resposta da API do mercado ou o texto da tabela.
Leitor = Callable[[str], str]


def ler_da_rede(url: str) -> str:
    """A resposta da API do mercado; a tabela do IBGE como texto, uma linha por linha."""
    if url.lower().endswith(".zip"):
        return texto_da_tabela(baixar(url))
    from retrieval.precos import ler_da_rede as ler_do_mercado

    return ler_do_mercado(url, {})


def _problema(citacao: Citacao, fonte: str) -> str:
    """ "" quando a fonte prova o número; senão, o porquê."""
    if citacao.tipo == "linha":
        return (
            ""
            if citacao.trecho in fonte.splitlines()
            else "a linha não está mais na tabela"
        )
    if citacao.tipo == "pagina":
        return "" if citacao.trecho in fonte else "o trecho não está mais na página"
    from retrieval.precos import problema_na_resposta

    return problema_na_resposta(citacao.registro, fonte)


def conferir(
    lista: Sequence[Citacao], ler: Leitor
) -> tuple[list[tuple[Citacao, str]], dict[str, str]]:
    """Cada citação com o resultado ("" quando a fonte prova) e o texto de cada fonte lida."""
    from retrieval.precos import PrecoNaoVeio

    fontes: dict[str, str] = {}
    falhas: dict[str, str] = {}
    urls = list(dict.fromkeys(c.url for c in lista))
    with ThreadPoolExecutor(max_workers=8) as executor:
        futuros = {url: executor.submit(ler, url) for url in urls}
    for url, futuro in futuros.items():
        try:
            fontes[url] = futuro.result()
        except (
            urllib.error.URLError,
            OSError,
            ValueError,
            KeyError,
            StopIteration,
            PrecoNaoVeio,
        ) as erro:
            falhas[url] = f"a fonte não veio ({erro})"
    resultado = [
        (c, falhas[c.url] if c.url in falhas else _problema(c, fontes[c.url]))
        for c in lista
    ]
    return resultado, fontes


# --------------------------------------------------------------------------- #
# Gravar e ler o que foi gravado                                               #
# --------------------------------------------------------------------------- #


def _produto_enxuto(citacao: Citacao, fonte: str) -> str:
    """Da resposta do mercado, só o produto citado, com o que a prova confere."""
    resposta = json.loads(fonte)
    for produto in resposta.get("products") or ():
        if str(produto.get("productId")) != str(citacao.registro.get("id")):
            continue
        item = (produto.get("items") or [{}])[0]
        ofertas = [
            {"commertialOffer": {k: v["commertialOffer"].get(k) for k in _OFERTA}}
            for v in item.get("sellers") or ()
            if isinstance(v, dict) and isinstance(v.get("commertialOffer"), dict)
        ]
        enxuto = {
            "productId": produto.get("productId"),
            "productName": produto.get("productName"),
            "items": [
                {
                    "measurementUnit": item.get("measurementUnit"),
                    "unitMultiplier": item.get("unitMultiplier"),
                    "sellers": ofertas,
                }
            ],
        }
        return json.dumps(
            {"products": [enxuto]}, ensure_ascii=False, separators=(",", ":")
        )
    return ""


_OFERTA: Final = ("Price", "ListPrice", "AvailableQuantity")


def _prova(citacoes_da_fonte: list[Citacao], fonte: str) -> list[str]:
    """O que a gravação guarda da fonte: o produto da resposta, ou as linhas em volta."""
    if citacoes_da_fonte[0].tipo == "preco":
        enxuto = _produto_enxuto(citacoes_da_fonte[0], fonte)
        return [enxuto] if enxuto else []
    if citacoes_da_fonte[0].tipo == "pagina":
        trecho = citacoes_da_fonte[0].trecho
        inicio = fonte.find(trecho)
        return (
            [fonte[max(0, inicio - 120) : inicio + len(trecho) + 120]]
            if inicio >= 0
            else []
        )
    linhas = fonte.splitlines()
    pedacos: list[str] = []
    for citacao in citacoes_da_fonte:
        if citacao.trecho in linhas:
            meio = linhas.index(citacao.trecho)
            pedacos.append("\n".join(linhas[max(0, meio - 1) : meio + 2]))
    return pedacos


def gravar(
    lista: Sequence[Citacao], fontes: dict[str, str], destino: Path, hoje: dt.date
) -> None:
    por_url: dict[str, list[Citacao]] = {}
    for citacao in lista:
        por_url.setdefault(citacao.url, []).append(citacao)
    gravado = {
        "gravado_em": hoje.isoformat(),
        "fontes": {
            url: {"tipo": cits[0].tipo, "prova": _prova(cits, fontes[url])}
            for url, cits in sorted(por_url.items())
            if url in fontes
        },
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(gravado, ensure_ascii=False, indent=1) + "\n", "utf-8"
    )


def ler_gravadas(origem: Path = GRAVADAS) -> Leitor:
    """Um leitor que devolve a prova gravada de cada fonte, sem rede."""
    fontes: dict[str, Any] = json.loads(origem.read_text("utf-8"))["fontes"]

    def ler(url: str) -> str:
        if url not in fontes:
            raise ValueError("a fonte não foi gravada")
        registro = fontes[url]
        if registro["tipo"] == "preco":
            return "".join(registro["prova"])
        return "\n".join(registro["prova"])

    return ler


# --------------------------------------------------------------------------- #
# Procurar de novo nos mercados de São Paulo                                   #
# --------------------------------------------------------------------------- #


def _no_mercado(pesquisa: Any, procura: Any, mercado: Any) -> Any:
    return pesquisa.no_mercado(mercado, procura)


def atualizar(precos: Path, pesquisa: Any, so: Sequence[str] = ()) -> list[str]:
    """Refaz as fontes de cada preço pela busca guardada nele, nos mercados de São Paulo.

    Nunca inventa: a fonte é o produto que a busca escolheu, com a consulta que
    prova o preço. O preço que ficou sem fonte nenhuma sai do arquivo.
    """
    from retrieval.precos import Procura

    dados = json.loads(precos.read_text("utf-8"))
    mantidos: list[dict[str, Any]] = []
    avisos: list[str] = []
    for registro in dados["precos"]:
        if so and registro["ingrediente"] not in so:
            mantidos.append(registro)
            continue
        procura = Procura.do_registro(registro["busca"])
        mercados = list(pesquisa.mercados)
        with ThreadPoolExecutor(max_workers=len(mercados)) as executor:
            achadas = list(
                executor.map(
                    functools.partial(_no_mercado, pesquisa, procura), mercados
                )
            )
        registro["fontes"] = [f.registro() for f in achadas if f is not None]
        if not registro["fontes"]:
            avisos.append(
                f"{registro['ingrediente']}: nenhum mercado de São Paulo tem, saiu"
            )
            continue
        if len(registro["fontes"]) < 2:
            avisos.append(f"{registro['ingrediente']}: só 1 mercado de São Paulo tem")
        mantidos.append(registro)
    dados["precos"] = mantidos
    precos.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return avisos


def main(argumentos: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument(
        "--gravar", action="store_true", help="grava a prova de cada fonte"
    )
    modo.add_argument(
        "--gravadas", action="store_true", help="confere com o que foi gravado"
    )
    modo.add_argument(
        "--atualizar",
        nargs="*",
        metavar="INGREDIENTE",
        help="refaz as fontes pela busca nos mercados de São Paulo (todos, ou só os citados)",
    )
    parser.add_argument(
        "--arquivo", type=Path, default=GRAVADAS, help="onde gravar ou ler"
    )
    parser.add_argument(
        "--precos", type=Path, default=PRECOS, help="o arquivo dos preços"
    )
    opcoes = parser.parse_args(argumentos)
    hoje = dt.datetime.now(tz=dt.UTC).date()

    if opcoes.atualizar is not None:
        from retrieval.precos import Pesquisa

        pesquisa = Pesquisa(hoje=hoje)
        for aviso in atualizar(opcoes.precos, pesquisa, opcoes.atualizar):
            print(aviso)
        for falha in pesquisa.falhas:
            print(f"aviso: {falha}")
        print(f"preços atualizados em {opcoes.precos}")
        return 0

    lista = citacoes(opcoes.precos)
    ler = ler_gravadas(opcoes.arquivo) if opcoes.gravadas else ler_da_rede
    resultado, fontes = conferir(lista, ler)
    for citacao, problema in resultado:
        marca = "ok   " if not problema else "FALTA"
        detalhe = f"  ({problema})" if problema else ""
        print(f"{marca} {citacao.id}{detalhe}")
    falhas = [c for c, problema in resultado if problema]
    origem = "fontes gravadas" if opcoes.gravadas else "fontes buscadas agora"
    precos = [c for c, _ in resultado if c.tipo == "preco"]
    precos_ok = [c for c, problema in resultado if c.tipo == "preco" and not problema]
    print(
        f"\n{len(precos_ok)} de {len(precos)} preços de mercados de São Paulo provados, "
        f"{len(resultado) - len(falhas)} de {len(resultado)} números provados "
        f"em {len(fontes)} {origem}"
    )
    if opcoes.gravar:
        if falhas:
            print("nada foi gravado: há número sem prova")
            return 1
        gravar(lista, fontes, opcoes.arquivo, hoje)
        print(f"gravado em {opcoes.arquivo}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
