"""Prova que cada foto da plataforma continua no Commons, com a licença e o autor ditos.

As fotos dos 37 itens da planilha (`dados/fotos_ingredientes.json`) e as dos
equipamentos e técnicas da cozinha (`dados/fotos_cozinha.json`, com `--cozinha`)
vêm do Wikimedia Commons, só com licença livre (CC0, domínio público, CC BY,
CC BY-SA), e a tela mostra o crédito "Foto: <autor>, <licença>, Wikimedia
Commons". Para cada linha, este script pergunta à API do Commons pelo arquivo e
confere:

- que o arquivo existe e a página dele é a que a linha diz;
- que o endereço da imagem é o que a API devolve para a largura combinada
  (960 px nos ingredientes, a miniatura de 250 px na cozinha, sem os
  parâmetros de campanha `utm_*` que ela acrescenta);
- que a licença é a que a linha diz, que ela é livre e que não há restrição
  (marca registrada, direito de imagem);
- que o autor é o que a página diz, e que o tipo é JPEG, PNG ou WebP.

    python scripts/conferir_fotos.py              # pergunta à API agora
    python scripts/conferir_fotos.py --gravar     # e grava as respostas
    python scripts/conferir_fotos.py --gravadas   # confere com o que foi gravado
    python scripts/conferir_fotos.py --cozinha    # o mesmo, com as fotos da cozinha

O que `--gravar` guarda (`scripts/tests/fixtures/fotos_commons.json`, e
`fotos_cozinha_commons.json` com `--cozinha`) é a parte
de cada resposta que a conferência usa, com a data. É com ela que os testes
refazem a prova sem rede: se alguém mudar uma licença, um autor ou um endereço
no arquivo das fotos, ele deixa de bater com a resposta gravada, e o teste
reprova.
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

RAIZ: Final = Path(__file__).resolve().parents[1]
ARQUIVO: Final = RAIZ / "dados" / "fotos_ingredientes.json"
GRAVADAS: Final = RAIZ / "scripts" / "tests" / "fixtures" / "fotos_commons.json"
#: As fotos dos equipamentos e das técnicas da cozinha, em miniatura.
ARQUIVO_DA_COZINHA: Final = RAIZ / "dados" / "fotos_cozinha.json"
GRAVADAS_DA_COZINHA: Final = (
    RAIZ / "scripts" / "tests" / "fixtures" / "fotos_cozinha_commons.json"
)

API: Final = "https://commons.wikimedia.org/w/api.php"
AGENTE: Final = "SaborDaMaria/1.0 (conferencia das licencas das fotos)"
LARGURA: Final = 960
#: A cozinha mostra a foto pequena, ao lado do nome: basta a miniatura padrão de 250 px.
LARGURA_DA_COZINHA: Final = 250
TIPOS: Final = frozenset({"image/jpeg", "image/png", "image/webp"})
#: A API do Commons pede calma assim.
LIMITE_DA_API: Final = 429

#: Pergunta à API pelo arquivo e devolve a parte da resposta que a conferência usa.
Consulta = Callable[[str], dict[str, Any]]


def fotos(caminho: Path | None = None) -> list[dict[str, Any]]:
    """As linhas do arquivo de fotos, na ordem do arquivo."""
    dados = json.loads((caminho or ARQUIVO).read_text(encoding="utf-8"))
    return list(dados["fotos"])


def texto_puro(bruto: str) -> str:
    """O autor como a página escreve, sem HTML: `<a ...>Fulana</a>` vira `Fulana`."""
    sem_tags = re.sub(r"<[^>]+>", " ", bruto)
    return " ".join(html.unescape(sem_tags).split())


def sem_rastreio(url: str) -> str:
    """O endereço sem os parâmetros de campanha (`utm_*`) que a API põe na miniatura."""
    partes = urllib.parse.urlsplit(url)
    fica = [
        (chave, valor)
        for chave, valor in urllib.parse.parse_qsl(partes.query, keep_blank_values=True)
        if not chave.startswith("utm_")
    ]
    return urllib.parse.urlunsplit(partes._replace(query=urllib.parse.urlencode(fica)))


def _valor(meta: Mapping[str, Any], campo: str) -> str:
    bruto = meta.get(campo)
    return str(bruto.get("value") or "") if isinstance(bruto, Mapping) else ""


def resumo_da_resposta(resposta: Mapping[str, Any]) -> dict[str, Any]:
    """Da resposta da API, só o que a conferência usa. Arquivo que não existe vira `{}`."""
    paginas = resposta.get("query", {}).get("pages", [])
    pagina = paginas[0] if paginas else {}
    if pagina.get("missing") or not pagina.get("imageinfo"):
        return {}
    info = pagina["imageinfo"][0]
    meta = info.get("extmetadata", {})
    return {
        "arquivo": pagina.get("title", ""),
        "pagina": info.get("descriptionurl", ""),
        "imagem": sem_rastreio(info.get("thumburl") or info.get("url", "")),
        "mime": info.get("mime", ""),
        "licenca": _valor(meta, "LicenseShortName"),
        "licenca_url": _valor(meta, "LicenseUrl") or None,
        "autor": texto_puro(_valor(meta, "Artist")),
        "restricoes": _valor(meta, "Restrictions"),
    }


def consultar_na_rede(
    arquivo: str,
    *,
    largura: int = LARGURA,
    tentativas: int = 4,
    dormir: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """A resposta da API do Commons para o arquivo, buscada agora.

    A API limita a frequência (HTTP 429): espera o que ela pede (`Retry-After`,
    ou alguns segundos) e tenta de novo, poucas vezes.
    """
    from retrieval.rede import abridor

    consulta = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime|size",
            "iiurlwidth": str(largura),
            "titles": arquivo,
        }
    )
    pedido = urllib.request.Request(f"{API}?{consulta}", headers={"User-Agent": AGENTE})
    for tentativa in range(tentativas):
        try:
            with abridor().open(pedido, timeout=20) as resposta:
                return resumo_da_resposta(json.loads(resposta.read()))
        except urllib.error.HTTPError as erro:
            if erro.code != LIMITE_DA_API or tentativa == tentativas - 1:
                raise
            espera = erro.headers.get("Retry-After", "") if erro.headers else ""
            dormir(float(espera) if espera.isdigit() else 5.0 * (tentativa + 1))
    raise AssertionError("inalcançável")  # pragma: no cover


def problemas(foto: Mapping[str, Any], resposta: Mapping[str, Any]) -> list[str]:
    """O que não bate entre a linha do arquivo e o que o Commons diz do arquivo."""
    from mise.fotos import LICENCA_LIVRE, foto_do_registro

    if not resposta:
        return ["o arquivo não existe mais no Commons"]
    achados: list[str] = []
    try:
        foto_do_registro(foto)
    except ValueError as erro:
        achados.append(str(erro))
    for campo in ("pagina", "imagem", "licenca", "autor"):
        if foto.get(campo) != resposta.get(campo):
            achados.append(
                f"{campo}: a linha diz {foto.get(campo)!r}, o Commons diz {resposta.get(campo)!r}"
            )
    if not LICENCA_LIVRE.match(str(resposta.get("licenca", ""))):
        achados.append(f"a licença {resposta.get('licenca')!r} não é livre")
    if resposta.get("restricoes"):
        achados.append(f"o arquivo tem restrição: {resposta['restricoes']}")
    if resposta.get("mime") not in TIPOS:
        achados.append(f"o tipo {resposta.get('mime')!r} não é JPEG, PNG nem WebP")
    return achados


def conferir(
    lista: Sequence[Mapping[str, Any]], consultar: Consulta
) -> tuple[list[tuple[str, list[str]]], dict[str, dict[str, Any]]]:
    """Cada foto com o que não bate (lista vazia se bate), e as respostas usadas."""
    respostas: dict[str, dict[str, Any]] = {}
    resultado: list[tuple[str, list[str]]] = []
    for foto in lista:
        arquivo = str(foto.get("arquivo", ""))
        try:
            resposta = respostas.setdefault(arquivo, consultar(arquivo))
        except (OSError, ValueError) as erro:
            resultado.append(
                (
                    str(foto.get("item_id")),
                    [f"não consegui perguntar ao Commons: {erro}"],
                )
            )
            continue
        resultado.append((str(foto.get("item_id")), problemas(foto, resposta)))
    return resultado, respostas


def ler_gravadas(caminho: Path | None = None) -> Consulta:
    """Uma consulta que responde com o que `--gravar` guardou."""
    gravadas = json.loads((caminho or GRAVADAS).read_text(encoding="utf-8"))[
        "respostas"
    ]

    def consultar(arquivo: str) -> dict[str, Any]:
        if arquivo not in gravadas:
            raise ValueError(f"sem resposta gravada para {arquivo}")
        return dict(gravadas[arquivo])

    return consultar


def gravar(
    respostas: Mapping[str, Mapping[str, Any]], caminho: Path | None = None
) -> Path:
    """Grava as respostas usadas, com a data, e devolve onde gravou."""
    destino = caminho or GRAVADAS
    destino.parent.mkdir(parents=True, exist_ok=True)
    dados = {
        "conferido_em": dt.datetime.now(tz=dt.UTC).date().isoformat(),
        "respostas": dict(sorted(respostas.items())),
    }
    destino.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return destino


def main(argv: Sequence[str] | None = None) -> int:
    partes = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    partes.add_argument(
        "--gravar", action="store_true", help="grava as respostas da API"
    )
    partes.add_argument(
        "--gravadas", action="store_true", help="confere com as respostas gravadas"
    )
    partes.add_argument(
        "--cozinha",
        action="store_true",
        help="as fotos dos equipamentos e técnicas da cozinha",
    )
    args = partes.parse_args(argv)
    arquivo, gravadas = (
        (ARQUIVO_DA_COZINHA, GRAVADAS_DA_COZINHA)
        if args.cozinha
        else (ARQUIVO, GRAVADAS)
    )
    consultar: Consulta = consultar_na_rede
    if args.gravadas:
        consultar = ler_gravadas(gravadas)
    elif args.cozinha:
        consultar = functools.partial(consultar_na_rede, largura=LARGURA_DA_COZINHA)
    resultado, respostas = conferir(fotos(arquivo), consultar)
    ruins = [(item, achados) for item, achados in resultado if achados]
    for item, achados in resultado:
        print(f"{'✓' if not achados else '✗'} {item}")
        for achado in achados:
            print(f"    {achado}")
    if args.gravar and not args.gravadas:
        destino = gravar(respostas, gravadas)
        print(f"gravei {len(respostas)} respostas em {destino}")
    print(
        f"{len(resultado) - len(ruins)} de {len(resultado)} fotos conferidas no Commons."
    )
    return 1 if ruins else 0


if __name__ == "__main__":
    sys.exit(main())
