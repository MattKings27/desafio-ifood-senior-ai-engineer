"""O que o agente está fazendo, dito para a Dona Maria.

Enquanto o agente trabalha, a tela mostra uma linha do tempo: "olhando sua
despensa" vira "olhei sua despensa" quando a chamada termina. As frases saem
daqui, e não do nome da ferramenta: `mcp__mise__avaliar_receita` não diz nada
para ela, e "portão" ou "CMV" diriam menos ainda. O mesmo catálogo serve ao
histórico.

Regras, todas conferidas em teste:

- toda ferramenta do motor (as de `politica.ESCOPOS`) tem frase, e as do próprio
  Hermes que chegam a este agente também; o resto cai na frase genérica;
- nenhuma palavra interna do sistema (motor, portão, APTO, FALTA INFO,
  BLOQUEADO, veredito, CMV, food cost);
- presente e passado dizem a mesma coisa, com os mesmos marcadores;
- os marcadores (`{prato}`, `{item}`, `{fonte}`, `{consulta}`) vêm dos
  argumentos da chamada, que são texto do modelo. Entram com o dinheiro
  mascarado (o valor vira o caractere que a tela desenha como "R$ ···", o
  mesmo do texto parcial da conversa), numa linha só e curtos. Sem o argumento,
  vale a frase genérica, que toda frase com marcador tem.
"""

from __future__ import annotations

import json
import re
import string
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlsplit

#: O caractere que a tela desenha como "R$ ···": valor que ninguém conferiu.
SENTINELA: Final = ""

#: O mais longo que um argumento entra numa frase.
TAMANHO_DO_DETALHE: Final = 60

#: Os marcadores que uma frase pode ter, todos preenchidos pelos argumentos.
MARCADORES: Final = frozenset({"prato", "item", "fonte", "consulta"})

#: O prefixo que o Hermes põe nas ferramentas do servidor `mise` (`mcp__mise__x`,
#: e `mcp_mise_x` em versões antigas), o mesmo que o guard-rail reconhece.
_DO_MOTOR: Final = re.compile(r"^mcp_{1,2}mise_{1,2}")

#: Dinheiro com cifrão: R$ 1.234,56 · R$12 · r$ 7,5 · US$ 3. O texto é do modelo:
#: na dúvida, mascara (o guard-rail só confere o "R$" maiúsculo).
_COM_CIFRAO: Final = re.compile(r"(?:[a-z]{1,2})?\$\s*\d[\d.,]*", re.IGNORECASE)

#: Dinheiro falado: 6 reais · 4,50 reais · 1 real.
_FALADO: Final = re.compile(r"\b\d[\d.,]*\s*(?:reais|real)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Frase:
    """Uma atividade no presente e no passado, com a versão genérica quando há marcador."""

    rotulo: str
    rotulo_feito: str
    #: A mesma atividade sem o marcador, para quando o argumento não veio.
    generica: tuple[str, str] | None = None

    @property
    def marcadores(self) -> frozenset[str]:
        """Os `{nomes}` que o texto pede."""
        return frozenset(
            nome
            for texto in (self.rotulo, self.rotulo_feito)
            for _, nome, _, _ in string.Formatter().parse(texto)
            if nome
        )

    def textos(self) -> tuple[str, ...]:
        """Todo texto que a frase pode mostrar."""
        return (self.rotulo, self.rotulo_feito, *(self.generica or ()))


def _sem_argumento(rotulo: str, rotulo_feito: str) -> Frase:
    return Frase(rotulo, rotulo_feito)


#: Uma frase por ferramenta do motor: as chaves são as de `politica.ESCOPOS`.
FRASES_DO_MOTOR: Final[Mapping[str, Frase]] = {
    "diagnostico_despensa": _sem_argumento("olhando sua despensa", "olhei sua despensa"),
    "custo_unitario": Frase(
        "conferindo o custo de {item}",
        "conferi o custo de {item}",
        ("conferindo o custo de um ingrediente", "conferi o custo de um ingrediente"),
    ),
    "converter_medida_culinaria": Frase(
        "convertendo a medida de {item}",
        "converti a medida de {item}",
        ("convertendo uma medida da receita", "converti uma medida da receita"),
    ),
    "consultar_perfil": _sem_argumento(
        "olhando o que já sei da sua cozinha", "olhei o que já sei da sua cozinha"
    ),
    "registrar_resposta": _sem_argumento(
        "anotando a resposta da senhora", "anotei a resposta da senhora"
    ),
    "proxima_pergunta": _sem_argumento(
        "separando a próxima pergunta", "separei a próxima pergunta"
    ),
    "avaliar_receita": Frase(
        "conferindo se a senhora consegue fazer {prato}",
        "conferi se a senhora consegue fazer {prato}",
        (
            "conferindo se a senhora consegue fazer a receita",
            "conferi se a senhora consegue fazer a receita",
        ),
    ),
    "comparar_candidatas": _sem_argumento("comparando as receitas", "comparei as receitas"),
    "calcular_cmv": _sem_argumento("calculando o custo por porção", "calculei o custo por porção"),
    "cenarios_preco": _sem_argumento(
        "montando os caminhos de preço", "montei os caminhos de preço"
    ),
    "testar_sensibilidade": _sem_argumento(
        "fazendo a conta desse preço", "fiz a conta desse preço"
    ),
    "consultar_conhecimento": _sem_argumento(
        "consultando as fontes de cozinha", "consultei as fontes de cozinha"
    ),
    "buscar_receita_na_web": Frase(
        "lendo a receita de {fonte}",
        "li a receita de {fonte}",
        ("lendo uma receita da internet", "li uma receita da internet"),
    ),
    "consultar_orcamento": _sem_argumento(
        "vendo quanto resta do orçamento", "vi quanto resta do orçamento"
    ),
    "registrar_compra": Frase(
        "anotando a compra de {item}",
        "anotei a compra de {item}",
        ("anotando a compra", "anotei a compra"),
    ),
    "registrar_decisao": _sem_argumento(
        "guardando a decisão da senhora", "guardei a decisão da senhora"
    ),
    "registrar_gosto": Frase(
        "anotando o que a senhora acha de {prato}",
        "anotei o que a senhora acha de {prato}",
        ("anotando o que a senhora acha do prato", "anotei o que a senhora acha do prato"),
    ),
    "consultar_gostos": _sem_argumento(
        "lembrando do que a senhora gosta de fazer", "lembrei do que a senhora gosta de fazer"
    ),
    "registrar_preco_mercado": Frase(
        "anotando o preço de {item}",
        "anotei o preço de {item}",
        ("anotando o preço", "anotei o preço"),
    ),
    "buscar_preco_na_web": Frase(
        "procurando o preço de {item} nos mercados de São Paulo",
        "procurei o preço de {item} nos mercados de São Paulo",
        (
            "procurando o preço nos mercados de São Paulo",
            "procurei o preço nos mercados de São Paulo",
        ),
    ),
    "consultar_precos_de_mercado": _sem_argumento(
        "olhando os preços anotados", "olhei os preços anotados"
    ),
    "consultar_cardapio": _sem_argumento("olhando o cardápio", "olhei o cardápio"),
    "consultar_planilha": _sem_argumento("lendo a sua planilha", "li a sua planilha"),
    "atualizar_despensa": Frase(
        "atualizando {item} na despensa",
        "atualizei {item} na despensa",
        ("atualizando a despensa", "atualizei a despensa"),
    ),
    "estimar_preco_preliminar": Frase(
        "fazendo uma estimativa do preço de {prato}",
        "fiz uma estimativa do preço de {prato}",
        ("fazendo uma estimativa do preço", "fiz uma estimativa do preço"),
    ),
    # A avaliação chega pelo id da receita, que não é nome para mostrar a ela.
    "registrar_avaliacao_da_receita": _sem_argumento(
        "anotando a avaliação da senhora", "anotei a avaliação da senhora"
    ),
    "pauta_de_descoberta": _sem_argumento(
        "separando o que procurar com o que a senhora tem",
        "separei o que procurar com o que a senhora tem",
    ),
}

_ANOTACOES: Final = _sem_argumento(
    "relendo minhas anotações de trabalho", "reli minhas anotações de trabalho"
)
_PROXIMO_PASSO: Final = _sem_argumento("organizando o próximo passo", "organizei o próximo passo")

#: As ferramentas do próprio Hermes que este agente usa (com os toolsets que o
#: perfil desliga fora), e as utilitárias que ele cria para cada servidor MCP.
FRASES_DA_AGENTE: Final[Mapping[str, Frase]] = {
    "web_search": Frase(
        "pesquisando na internet: {consulta}",
        "pesquisei na internet: {consulta}",
        ("pesquisando na internet", "pesquisei na internet"),
    ),
    "web_extract": Frase(
        "lendo uma página de {fonte}",
        "li uma página de {fonte}",
        ("lendo uma página da internet", "li uma página da internet"),
    ),
    "vision_analyze": _sem_argumento("olhando a foto", "olhei a foto"),
    "skills_list": _ANOTACOES,
    "skill_view": _ANOTACOES,
    "skill_manage": _sem_argumento(
        "ajustando minhas anotações de trabalho", "ajustei minhas anotações de trabalho"
    ),
    "tool_search": _PROXIMO_PASSO,
    "tool_describe": _PROXIMO_PASSO,
    "list_prompts": _PROXIMO_PASSO,
    "get_prompt": _PROXIMO_PASSO,
    "todo_list": _sem_argumento("organizando os próximos passos", "organizei os próximos passos"),
    "memory": _sem_argumento(
        "guardando isso para lembrar depois", "guardei isso para lembrar depois"
    ),
    "session_search": _sem_argumento(
        "lembrando das nossas conversas", "lembrei das nossas conversas"
    ),
    "clarify": _sem_argumento(
        "preparando uma pergunta para a senhora", "preparei uma pergunta para a senhora"
    ),
    "list_resources": _sem_argumento("vendo o que está guardado", "vi o que está guardado"),
    "read_resource": _sem_argumento("lendo o que está guardado", "li o que está guardado"),
    "_thinking": _sem_argumento("pensando no próximo passo", "pensei no próximo passo"),
}

#: Para a ferramenta que nenhum catálogo conhece: a tela nunca mostra o nome cru.
FRASE_GENERICA: Final = _sem_argumento(
    "cuidando do pedido da senhora", "cuidei do pedido da senhora"
)

FRASES: Final[Mapping[str, Frase]] = {**FRASES_DO_MOTOR, **FRASES_DA_AGENTE}


def nome_da_ferramenta(bruto: str) -> str:
    """O nome da ferramenta sem o prefixo que o Hermes põe nas do servidor `mise`."""
    return _DO_MOTOR.sub("", bruto.strip())


def argumentos_da_chamada(argumentos: object) -> Mapping[str, Any]:
    """Os argumentos como dicionário: vêm como objeto ou como texto JSON; o resto é vazio."""
    if isinstance(argumentos, str):
        try:
            argumentos = json.loads(argumentos)
        except ValueError:
            return {}
    return argumentos if isinstance(argumentos, Mapping) else {}


def mascarar_dinheiro(texto: str) -> str:
    """Troca todo valor em reais pelo caractere que a tela desenha como "R$ ···"."""
    return _FALADO.sub(SENTINELA, _COM_CIFRAO.sub(SENTINELA, texto))


def detalhe(valor: object) -> str | None:
    """Um argumento pronto para entrar numa frase: uma linha, sem dinheiro, curto.

    O dinheiro sai antes do corte: cortar primeiro deixaria "18,9" de um
    "18,90 reais" à mostra, sem o "reais" que o identifica.
    """
    if not isinstance(valor, str):
        return None
    limpo = mascarar_dinheiro(" ".join(valor.split()))
    if not limpo:
        return None
    if len(limpo) > TAMANHO_DO_DETALHE:
        return limpo[: TAMANHO_DO_DETALHE - 1].rstrip() + "…"
    return limpo


def _minuscula_inicial(texto: str) -> str:
    """No meio da frase, "Arroz com frango" vira "arroz com frango"; sigla fica como está."""
    primeira = texto.split(" ", 1)[0]
    if len(primeira) > 1 and primeira.isupper():
        return texto
    return texto[:1].lower() + texto[1:]


def valor_no_caminho(argumentos: Mapping[str, Any], caminho: str) -> object:
    """O valor em `receita.nome`, entrando em objeto (ou texto JSON de objeto)."""
    atual: object = argumentos
    for chave in caminho.split("."):
        atual = argumentos_da_chamada(atual).get(chave)
    return atual


def _dominio(url: object) -> str | None:
    """O site de um endereço, sem o `www.`: `tudogostoso.com.br`."""
    if not isinstance(url, str):
        return None
    try:
        host = urlsplit(url.strip()).hostname
    except ValueError:
        return None
    if not host:
        return None
    return host.removeprefix("www.")


def valores_dos_marcadores(argumentos: Mapping[str, Any]) -> dict[str, str]:
    """O que cada marcador mostra, tirado dos argumentos de qualquer ferramenta."""
    urls = argumentos.get("urls")
    primeira_url = urls[0] if isinstance(urls, list) and urls else None
    brutos: dict[str, str | None] = {
        "prato": detalhe(valor_no_caminho(argumentos, "prato"))
        or detalhe(valor_no_caminho(argumentos, "receita.nome")),
        "item": detalhe(argumentos.get("ingrediente")),
        "fonte": detalhe(argumentos.get("fonte"))
        or detalhe(_dominio(argumentos.get("url")))
        or detalhe(_dominio(primeira_url)),
        "consulta": detalhe(argumentos.get("query")),
    }
    valores = {nome: valor for nome, valor in brutos.items() if valor}
    for nome in ("prato", "item"):
        if nome in valores:
            valores[nome] = _minuscula_inicial(valores[nome])
    return valores


def frase_para(ferramenta: str, argumentos: object = None) -> dict[str, str]:
    """`{rotulo, rotulo_feito}` da atividade, com os marcadores preenchidos."""
    frase = FRASES.get(nome_da_ferramenta(ferramenta), FRASE_GENERICA)
    if frase.generica is not None:
        valores = valores_dos_marcadores(argumentos_da_chamada(argumentos))
        if not frase.marcadores <= valores.keys():
            rotulo, feito = frase.generica
            return {"rotulo": rotulo, "rotulo_feito": feito}
        return {
            "rotulo": frase.rotulo.format(**valores),
            "rotulo_feito": frase.rotulo_feito.format(**valores),
        }
    return {"rotulo": frase.rotulo, "rotulo_feito": frase.rotulo_feito}


__all__ = [
    "FRASES",
    "FRASES_DA_AGENTE",
    "FRASES_DO_MOTOR",
    "FRASE_GENERICA",
    "MARCADORES",
    "SENTINELA",
    "TAMANHO_DO_DETALHE",
    "Frase",
    "argumentos_da_chamada",
    "detalhe",
    "frase_para",
    "mascarar_dinheiro",
    "nome_da_ferramenta",
    "valor_no_caminho",
    "valores_dos_marcadores",
]
