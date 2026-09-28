"""As instruções do agente batem com o sistema que ele opera.

Antes destes testes, as cinco skills e o contexto citavam `mcp_mise_*` (o nome é
`mcp__mise__*`), nenhuma das sete ferramentas novas e valores em R$ escritos à
mão que ferramenta nenhuma devolvia. O agente rodava sem saber metade do que
podia fazer, e com exemplos que o guard-rail apagaria.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from gateway.conversa import INSTRUCAO_DA_WEB
from gateway.politica import ESCOPOS
from mise.descoberta import MAXIMO_DE_BUSCAS, MAXIMO_DE_PAGINAS, PAGINAS_POR_BUSCA
from mise.mcp_server import INSTRUCOES

RAIZ = Path(__file__).resolve().parents[2]
SOUL = RAIZ / "hermes" / "SOUL.md"
SKILLS = sorted((RAIZ / "hermes" / "skills").rglob("SKILL.md"))
INSTRUCOES_DA_AGENTE = [SOUL, *SKILLS]
#: Os pedidos fixos que a plataforma faz ao agente em segundo plano (a descoberta de receitas).
PROMPTS = sorted((RAIZ / "hermes" / "prompts").glob("*.md"))

_CITADA = re.compile(r"mcp__mise__(\w+)")


def _texto(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def test_ha_uma_alma_e_cinco_skills() -> None:
    assert SOUL.exists()
    assert len(SKILLS) == 5


@pytest.mark.parametrize("arquivo", INSTRUCOES_DA_AGENTE, ids=lambda p: p.parent.name)
def test_toda_ferramenta_citada_existe(arquivo: Path) -> None:
    citadas = set(_CITADA.findall(_texto(arquivo)))
    assert citadas <= set(ESCOPOS), citadas - set(ESCOPOS)


@pytest.mark.parametrize("arquivo", INSTRUCOES_DA_AGENTE, ids=lambda p: p.parent.name)
def test_nenhum_nome_de_ferramenta_no_formato_errado(arquivo: Path) -> None:
    """`mcp_mise_x` não é o nome que o Hermes dá: é `mcp__mise__x`."""
    assert not re.search(r"\bmcp_mise_", _texto(arquivo))


def test_toda_ferramenta_do_motor_e_ensinada_na_alma_ou_numa_skill() -> None:
    """Ferramenta que nenhuma instrução cita é ferramenta que o agente não usa.

    As `INSTRUCOES` do servidor MCP não contam: o Hermes 0.21.4 não põe as
    instruções do servidor no contexto do modelo. Quem ensina é o SOUL e as skills.
    """
    ensinado = "\n".join(_texto(a) for a in INSTRUCOES_DA_AGENTE)
    sem_instrucao = {nome for nome in ESCOPOS if nome not in ensinado}
    assert not sem_instrucao, sem_instrucao


def test_as_instrucoes_do_servidor_tem_uma_linha_por_ferramenta() -> None:
    """Para quem conecta outro cliente MCP: cada ferramenta numa linha, com o que ela faz."""
    linhas = {
        linha.split(":", 1)[0] for linha in INSTRUCOES.splitlines() if ":" in linha
    }
    assert set(ESCOPOS) <= linhas, set(ESCOPOS) - linhas


#: Travessão, ou hífen solto fazendo o papel dele, no meio de uma frase.
_TRAVESSAO = re.compile(r"\S\s+[—–-]\s+\S|[—–]")


#: Tudo o que o agente lê e que este repositório escreve.
_TEXTOS_DA_AGENTE = {
    "SOUL": _texto(SOUL),
    **{skill.parent.name: _texto(skill) for skill in SKILLS},
    **{f"prompts/{prompt.name}": _texto(prompt) for prompt in PROMPTS},
    "config.overlay.yaml": _texto(RAIZ / "hermes" / "config.overlay.yaml"),
    "INSTRUCOES": INSTRUCOES,
    "INSTRUCAO_DA_WEB": INSTRUCAO_DA_WEB,
}


@pytest.mark.parametrize("nome", sorted(_TEXTOS_DA_AGENTE))
def test_nenhum_travessao_separando_ideias(nome: str) -> None:
    """O modelo imita a pontuação que lê; a Dona Maria lê vírgula e ponto."""
    linhas = [
        linha
        for linha in _TEXTOS_DA_AGENTE[nome].splitlines()
        if not linha.lstrip().startswith("- ")
    ]
    achados = [linha for linha in linhas if _TRAVESSAO.search(linha)]
    assert not achados, (nome, achados)


#: O nome antigo: "a consultora", ou o agente no feminino.
_NOME_ANTIGO = re.compile(
    r"\bconsultora\b|\b(?:a|da|na|pela|à)\s+agente\b", re.IGNORECASE
)


def test_a_alma_apresenta_o_agente() -> None:
    """A tela diz "Seu agente" e "Conversar com o agente"; a alma diz o mesmo."""
    assert _texto(SOUL).startswith("Você é o agente do Sabor da Maria.")


@pytest.mark.parametrize("nome", sorted(_TEXTOS_DA_AGENTE))
def test_nenhuma_instrucao_usa_o_nome_antigo(nome: str) -> None:
    """Ele fala de si no masculino, como a tela fala dele."""
    assert not _NOME_ANTIGO.findall(_TEXTOS_DA_AGENTE[nome]), nome


def test_nao_sei_e_resposta_aceita() -> None:
    """A conferência aceita "não sei" e o guarda como pendência; a skill não pode dizer o contrário."""
    skill = _texto(
        RAIZ
        / "hermes"
        / "skills"
        / "consultoria-gastronomica"
        / "elicitacao-restricoes"
        / "SKILL.md"
    )
    assert "`nao_sei`" in skill
    assert not re.search(r"n[ãa]o sei[^.]{0,80}recusad", skill, re.IGNORECASE)


def _skill(nome: str) -> str:
    return _texto(
        RAIZ / "hermes" / "skills" / "consultoria-gastronomica" / nome / "SKILL.md"
    )


def test_toda_receita_apresentada_leva_a_pergunta_do_gosto() -> None:
    """A tela separa "Gosto de fazer" de "Não gosto de fazer" pelo gosto gravado.

    O agente pergunta de toda receita que apresenta, grava pela ferramenta que
    escreve na tabela de gostos, e pergunta o gosto antes da cozinha: se ela não
    gosta, não há equipamento, técnica nem rotina a conferir.
    """
    alma = _texto(SOUL)
    assert "**Toda receita que você apresenta leva a pergunta do gosto.**" in alma
    assert "**O gosto vem antes da cozinha.**" in alma
    assert "`registrar_avaliacao_da_receita`" in alma
    assert "`registrar_gosto`" in alma
    assert '"Gosto de fazer" de "Não gosto de fazer"' in alma
    pesquisa = _skill("pesquisa-receitas")
    assert (
        "Toda receita que você apresenta leva a pergunta do gosto, sempre" in pesquisa
    )
    assert "O gosto vem antes da cozinha" in pesquisa
    elicitacao = _skill("elicitacao-restricoes")
    assert "O gosto vem primeiro" in elicitacao
    linha_do_gosto = next(
        linha
        for linha in elicitacao.splitlines()
        if linha.startswith("| Gosto de um prato")
    )
    assert "mcp__mise__registrar_avaliacao_da_receita" in linha_do_gosto
    assert "mcp__mise__registrar_gosto" in linha_do_gosto


#: O que mandava perguntar a ela um número que a plataforma estabelece sozinha.
_PERGUNTA_DE_NUMERO = re.compile(
    r"pergunta do pre[çc]o"
    r"|pergunte[^.]{0,40}\b(?:o pre[çc]o|quanto custa|quanto pesa|quanto vai|o peso|a medida|a quantidade)"
    r"|pergunte a ela e grave o n[úu]mero"
    r"|peso n[ãa]o se chuta"
    r"|melhor pergunta para terminar"
    r"|linha[^.]{0,60}com a pergunta"
    r"|pend[êe]ncia[^.]{0,80}pergunta pronta"
    r"|quanto (?:pesa|custa|vai)[^.?\n]{0,60}\?"
    r"|[ée] o seu [^.?\n]{0,40}\?",
    re.IGNORECASE,
)


@pytest.mark.parametrize("nome", sorted(_TEXTOS_DA_AGENTE))
def test_nenhuma_instrucao_manda_perguntar_peso_medida_quantidade_ou_preco(
    nome: str,
) -> None:
    """Peso, medida, quantidade, rendimento e preço vêm pré-determinados, com a fonte.

    Ela só responde o gosto, o equipamento, a técnica e os limites da rotina; o
    resto ela corrige quando quiser, e nenhuma instrução pede o número a ela.
    """
    achados = [
        m.group(0) for m in _PERGUNTA_DE_NUMERO.finditer(_TEXTOS_DA_AGENTE[nome])
    ]
    assert not achados, (nome, achados)


def test_o_numero_pre_determinado_se_diz_com_a_fonte_e_se_corrige() -> None:
    """Quando ela pergunta de um número, ele é estimado, tem fonte, e ela pode corrigir."""
    alma = _texto(SOUL)
    assert "**Peso, medida, quantidade, rendimento e preço nunca são pergunta**" in alma
    assert (
        "diga que é estimado, de onde veio e que ela pode corrigir quando quiser"
        in alma
    )
    for nome in (
        "elicitacao-restricoes",
        "precificacao-delivery",
        "pesquisa-receitas",
        "diagnostico-despensa",
    ):
        skill = _skill(nome)
        assert re.search(r"n[ãa]o (?:são|é|vira) pergunta|nunca são pergunta", skill), (
            nome
        )
        assert re.search(r"estimad[oa]|estimativa", skill), nome
        assert "corrigir" in skill, nome


@pytest.mark.parametrize("arquivo", INSTRUCOES_DA_AGENTE, ids=lambda p: p.parent.name)
def test_nenhum_valor_inventado_como_exemplo(arquivo: Path) -> None:
    """Exemplo com R$ escrito à mão vira número que o modelo repete como se fosse dela.

    O único valor fixo é o orçamento de R$ 80,00, que vem do enunciado e que o
    motor também devolve.
    """
    valores = set(re.findall(r"R\$ ?\d[\d.,]*", _texto(arquivo)))
    assert valores <= {"R$ 80,00"}, valores


def test_ha_o_pedido_fixo_da_descoberta() -> None:
    assert [p.name for p in PROMPTS] == ["descoberta.md"]


@pytest.mark.parametrize("prompt", PROMPTS, ids=lambda p: p.name)
def test_o_pedido_fixo_so_cita_ferramenta_que_existe(prompt: Path) -> None:
    texto = _texto(prompt)
    citadas = set(_CITADA.findall(texto))
    assert citadas, "o pedido fixo diz quais ferramentas usar"
    assert citadas <= set(ESCOPOS), citadas - set(ESCOPOS)
    assert not re.search(r"\bmcp_mise_", texto)


@pytest.mark.parametrize("prompt", PROMPTS, ids=lambda p: p.name)
def test_o_pedido_fixo_nao_traz_valor(prompt: Path) -> None:
    """Como nas skills: o único valor escrito à mão pode ser o orçamento do enunciado."""
    valores = set(re.findall(r"R\$ ?\d[\d.,]*", _texto(prompt)))
    assert valores <= {"R$ 80,00"}, valores


def test_a_descoberta_so_le_pelo_servidor_e_para_nos_limites() -> None:
    """A receita entra pela página que o servidor leu; o pedido diz os limites e para.

    Os números do pedido são os da pauta (`mise.descoberta`), que o gateway também usa
    para parar a rodada: um pedido com outro número faria o modelo parar antes, ou o
    gateway cortar o modelo no meio.
    """
    texto = _texto(RAIZ / "hermes" / "prompts" / "descoberta.md")
    assert "mcp__mise__pauta_de_descoberta" in texto
    assert "mcp__mise__buscar_receita_na_web" in texto
    assert (MAXIMO_DE_BUSCAS, MAXIMO_DE_PAGINAS, PAGINAS_POR_BUSCA) == (8, 20, 3)
    assert f"no máximo {MAXIMO_DE_BUSCAS} pesquisas" in texto
    assert f"no máximo {MAXIMO_DE_PAGINAS} no total" in texto
    assert f"no máximo {PAGINAS_POR_BUSCA} de cada pesquisa" in texto
    assert f"quando chegar a {MAXIMO_DE_PAGINAS} páginas, pare" in texto
    assert "Não pergunte nada" in texto


def test_a_descoberta_prefere_os_sites_populares() -> None:
    """Primeiro os sites de receita mais populares, depois os que já funcionaram."""
    texto = _texto(RAIZ / "hermes" / "prompts" / "descoberta.md")
    assert "Prefira primeiro as páginas dos sites de `sites_populares`" in texto
    assert texto.index("Prefira primeiro") < texto.index(
        "depois as dos sites de `sites_que_ja_funcionaram`"
    )
    assert "outra língua" in texto, (
        "a página em outra língua não entra, e a rodada segue"
    )


def test_a_alma_nao_carrega_frase_de_injecao() -> None:
    """O Hermes varre o SOUL.md atrás de injeção; citar a frase como exemplo a dispararia."""
    assert "ignore as instruções" not in _texto(SOUL).lower()


def test_nao_ha_contexto_que_so_existe_dentro_do_repositorio() -> None:
    """HERMES.md só é lido quando a sessão abre no repositório.

    A avaliação rodava com ele; a conversa pelo chat da web, não. Regra que precisa
    valer sempre mora no SOUL.md do perfil.
    """
    assert not (RAIZ / "HERMES.md").exists()
    assert not (RAIZ / "AGENTS.md").exists()
