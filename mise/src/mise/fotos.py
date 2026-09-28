"""As fotos da plataforma: a dos itens da planilha, a da cozinha e a das receitas, com o crédito.

A tela nunca carrega foto de outro endereço: recebe `{url, credito}`, com a
`url` no proxy da API (`/motor/imagens/<chave>`), e a API só serve foto de
endereço que o servidor registrou. Há três registros, e só estes três:

- **Os itens da planilha.** Uma foto do Wikimedia Commons para cada um dos 37
  itens, com licença livre (CC0, domínio público, CC BY ou CC BY-SA), o autor e
  a linha de crédito ("Foto: <autor>, <licença>, Wikimedia Commons"), num
  arquivo versionado ao lado da planilha (`dados/fotos_ingredientes.json`).
  Cada linha foi conferida na API do Commons, e `make conferir-fotos` confere
  de novo. O item sem foto livre que o mostre de verdade fica sem foto, com o
  motivo no arquivo (`sem_foto`), e o item que ela acrescenta também não tem:
  a tela mostra o gradiente com o ícone da categoria.
- **A cozinha.** Uma miniatura do Commons para cada equipamento e técnica do
  vocabulário (`mise.taxonomia`), com as mesmas regras de licença e crédito,
  em `dados/fotos_cozinha.json`, ao lado da planilha; `make
  conferir-fotos-cozinha` confere de novo. O item sem foto livre que o mostre
  de verdade fica sem foto, com o motivo (`sem_foto`), e a tela mostra o ícone.
- **As receitas.** A foto que a página declara na receita estruturada, que o
  catálogo guardou quando o servidor leu a página (`Catalogo.fotos`).

A regra da chave é a do catálogo (`mise.catalogo.chave_da_imagem`): os 32
primeiros caracteres hexadecimais do sha256 do endereço original.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlsplit

from mise.catalogo import chave_da_imagem, rota_da_imagem

if TYPE_CHECKING:
    from mise.despensa import Despensa, Ingrediente
    from mise.mcp_server import Sessao

logger = logging.getLogger(__name__)

#: O arquivo das fotos dos itens, ao lado da planilha.
ARQUIVO_DAS_FOTOS: Final = "fotos_ingredientes.json"
#: Outro arquivo de fotos, no lugar do que fica ao lado da planilha.
VAR_FOTOS: Final = "MISE_FOTOS"
#: O arquivo das fotos dos equipamentos e técnicas da cozinha, ao lado da planilha.
ARQUIVO_DAS_FOTOS_DA_COZINHA: Final = "fotos_cozinha.json"
#: Outro arquivo de fotos da cozinha, no lugar do que fica ao lado da planilha.
VAR_FOTOS_DA_COZINHA: Final = "MISE_FOTOS_COZINHA"

#: As licenças que deixam a plataforma mostrar a foto dando o crédito.
LICENCA_LIVRE: Final = re.compile(
    r"^(CC0( 1\.0)?|Public domain|Domínio público|PD[\w .-]*"
    r"|CC BY(-SA)?( \d(\.\d)?)?( (?!nc\b|nd\b)[a-z]{2}| igo)?)$",
    re.IGNORECASE,
)
#: Os endereços de onde as fotos dos itens vêm (e só deles): o do arquivo e o da miniatura.
HOSTS_DAS_FOTOS: Final = frozenset({"upload.wikimedia.org", "thumb.wikimedia.org"})
#: A página de cada foto, com o autor e a licença.
HOST_DAS_PAGINAS: Final = "commons.wikimedia.org"

#: O crédito da foto de uma receita cuja página não diz o nome do site.
CREDITO_DA_PAGINA: Final = "Foto: a página da receita"


@dataclass(frozen=True, slots=True)
class Foto:
    """Uma foto que a API pode servir: o endereço original, o crédito e de onde veio."""

    url: str
    credito: str
    licenca: str | None = None
    #: A página que mostra a foto com o autor e a licença, ou a página da receita.
    fonte_url: str | None = None
    #: A foto que a página de uma receita declarou (e não a de um item da planilha):
    #: se chegar a imagem genérica do site, a receita fica sem foto.
    da_receita: bool = False

    @property
    def chave(self) -> str:
        return chave_da_imagem(self.url)

    def para_tela(self) -> dict[str, str]:
        """`{url, credito}`: a forma de `imagem` em todos os contratos da tela."""
        return {"url": rota_da_imagem(self.url), "credito": self.credito}

    def credito_json(self) -> dict[str, str | None]:
        """`GET /api/imagens/{chave}/credito`: `{credito, licenca, fonte_url}`."""
        return {"credito": self.credito, "licenca": self.licenca, "fonte_url": self.fonte_url}


def _host(url: str) -> str | None:
    """O host de um endereço https, ou `None` (outro esquema, endereço quebrado)."""
    try:
        partes = urlsplit(url)
    except ValueError:
        return None
    return partes.hostname if partes.scheme == "https" else None


def foto_do_registro(bruto: Mapping[str, Any]) -> Foto:
    """Uma linha do arquivo de fotos, conferida. Linha fora da regra é `ValueError`.

    A regra: a imagem no `upload.wikimedia.org`, a página no Commons, licença
    livre, autor dito e o crédito na forma "Foto: <autor>, <licença>, Wikimedia
    Commons".
    """
    campos = {nome: bruto.get(nome) for nome in ("item_id", "imagem", "pagina", "licenca", "autor")}
    textos = {nome: valor.strip() for nome, valor in campos.items() if isinstance(valor, str)}
    item_id = textos.get("item_id") or "?"
    if len(textos) < len(campos) or not all(textos.values()):
        raise ValueError(f"{item_id}: falta item_id, imagem, página, licença ou autor")
    if _host(textos["imagem"]) not in HOSTS_DAS_FOTOS:
        raise ValueError(f"{item_id}: a imagem precisa ser do Wikimedia (https://upload ou thumb)")
    if _host(textos["pagina"]) != HOST_DAS_PAGINAS:
        raise ValueError(f"{item_id}: a página precisa ser https://{HOST_DAS_PAGINAS}/...")
    licenca = textos["licenca"]
    if not LICENCA_LIVRE.match(licenca):
        raise ValueError(f"{item_id}: licença que não é livre: {licenca!r}")
    credito = f"Foto: {textos['autor']}, {licenca}, Wikimedia Commons"
    if bruto.get("credito") != credito:
        raise ValueError(f"{item_id}: o crédito precisa ser {credito!r}")
    return Foto(url=textos["imagem"], credito=credito, licenca=licenca, fonte_url=textos["pagina"])


@functools.lru_cache(maxsize=8)
def ler_fotos(caminho: Path) -> Mapping[str, Foto]:
    """As fotos do arquivo, pelo id do item. Sem arquivo, nenhuma foto.

    Lido uma vez por processo, na primeira tela que pede uma foto. Uma linha
    fora da regra fica de fora (com aviso no log): foto sem licença livre ou
    sem crédito não aparece.
    """
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.warning("não consegui ler as fotos dos itens em %s", caminho, exc_info=True)
        return {}
    fotos: dict[str, Foto] = {}
    for bruto in dados.get("fotos", []) if isinstance(dados, dict) else []:
        try:
            foto = foto_do_registro(bruto)
        except ValueError as erro:
            logger.warning("foto de item recusada: %s", erro)
            continue
        fotos[str(bruto["item_id"])] = foto
    return fotos


def caminho_das_fotos(
    despensa: Despensa,
    ambiente: Mapping[str, str] | None = None,
    *,
    variavel: str = VAR_FOTOS,
    arquivo: str = ARQUIVO_DAS_FOTOS,
) -> Path | None:
    """`MISE_FOTOS`, ou o arquivo de fotos ao lado da planilha; `None` sem planilha."""
    amb = os.environ if ambiente is None else ambiente
    explicito = amb.get(variavel, "").strip()
    if explicito:
        return Path(explicito).expanduser()
    if despensa.origem is None:
        return None
    return Path(despensa.origem).parent / arquivo


def fotos_dos_itens(despensa: Despensa) -> Mapping[str, Foto]:
    """As fotos dos itens da planilha desta despensa, pelo id do item."""
    caminho = caminho_das_fotos(despensa)
    return ler_fotos(caminho.resolve()) if caminho is not None else {}


def imagem_do_item(despensa: Despensa, item: Ingrediente) -> dict[str, str] | None:
    """A `imagem` do item na tela, ou `None` (o item que ela acrescentou não tem foto)."""
    foto = fotos_dos_itens(despensa).get(item.id)
    return foto.para_tela() if foto is not None else None


def fotos_da_cozinha(despensa: Despensa) -> Mapping[str, Foto]:
    """As miniaturas dos equipamentos e técnicas, pelo id do vocabulário.

    `MISE_FOTOS_COZINHA`, ou `fotos_cozinha.json` ao lado da planilha: o mesmo
    formato e as mesmas regras das fotos dos itens.
    """
    caminho = caminho_das_fotos(
        despensa, variavel=VAR_FOTOS_DA_COZINHA, arquivo=ARQUIVO_DAS_FOTOS_DA_COZINHA
    )
    return ler_fotos(caminho.resolve()) if caminho is not None else {}


def foto_pela_chave(sessao: Sessao, chave: str) -> Foto | None:
    """A foto registrada com esta chave: de um item da planilha, da cozinha ou de uma receita lida.

    É a pergunta do proxy de imagens antes de baixar qualquer coisa: chave que
    não está aqui não vira download.
    """
    for foto in (
        *fotos_dos_itens(sessao.planilha).values(),
        *fotos_da_cozinha(sessao.planilha).values(),
    ):
        if foto.chave == chave:
            return foto
    for da_receita in sessao.catalogo.fotos():
        if da_receita.chave == chave:
            return Foto(
                url=da_receita.imagem_url,
                credito=da_receita.credito or CREDITO_DA_PAGINA,
                fonte_url=da_receita.pagina,
                da_receita=True,
            )
    return None


__all__ = [
    "ARQUIVO_DAS_FOTOS",
    "ARQUIVO_DAS_FOTOS_DA_COZINHA",
    "CREDITO_DA_PAGINA",
    "HOSTS_DAS_FOTOS",
    "HOST_DAS_PAGINAS",
    "LICENCA_LIVRE",
    "VAR_FOTOS",
    "VAR_FOTOS_DA_COZINHA",
    "Foto",
    "caminho_das_fotos",
    "foto_do_registro",
    "foto_pela_chave",
    "fotos_da_cozinha",
    "fotos_dos_itens",
    "imagem_do_item",
    "ler_fotos",
]
