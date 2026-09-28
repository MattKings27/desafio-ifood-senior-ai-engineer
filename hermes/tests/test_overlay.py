"""O overlay de configuração do Hermes e o que o bootstrap faz com ele.

Existe por causa de um defeito real: a primeira versão do overlay trazia
`plugins.enabled: true`, e `plugins.enabled` é uma **lista de nomes de plugin**.
O booleano substituiu `[guardrail-numerico]` e desligou o guard-rail numérico em
silêncio: o arquivo que existe para tornar a configuração reprodutível teria
reproduzido uma configuração quebrada em toda máquina que rodasse o bootstrap.

O que estes testes protegem é o tipo de cada chave, as decisões que o overlay
justifica e o comportamento da fusão. A fusão e as skills desligadas vêm de
`hermes/configurar_perfil.py`, o mesmo arquivo que o bootstrap roda, e não de uma
cópia dele.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[2]
OVERLAY = RAIZ / "hermes" / "config.overlay.yaml"
SKILLS_DA_CONSULTORIA = RAIZ / "hermes" / "skills"


def _configurar_perfil() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "configurar_perfil", RAIZ / "hermes" / "configurar_perfil.py"
    )
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


configurar_perfil = _configurar_perfil()


@pytest.fixture(scope="module")
def overlay() -> dict:
    return yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))


def test_overlay_existe_e_e_yaml_valido(overlay: dict) -> None:
    assert isinstance(overlay, dict)
    assert overlay


def test_versiona_o_modelo_e_o_esforco(overlay: dict) -> None:
    """O modelo e o esforço não podem viver só em prosa; o esforço a medição confirma."""
    assert overlay["model"]["default"] == "claude-fable-5-1"
    assert overlay["model"]["provider"] == "anthropic"
    assert overlay["agent"]["reasoning_effort"] == "medium"


def test_ferramentas_do_motor_sem_ida_e_volta_para_ler_o_esquema(overlay: dict) -> None:
    """Sem a busca de ferramentas, o modelo usa a ferramenta do motor na primeira chamada.

    Com a busca ligada ("auto", o padrão), cada ferramenta nova custa uma ida e
    volta ao modelo só para o `tool_describe`. A chave é texto: `off` sem aspas
    o YAML lê como `False`, e o Hermes só entende o booleano no nível de cima.
    """
    assert overlay["tools"]["tool_search"]["enabled"] == "off"


def test_a_reserva_tem_a_forma_do_esquema(overlay: dict) -> None:
    """Lista de pares provider e model: entrada sem um dos dois o Hermes ignora calado."""
    reserva = overlay["fallback_providers"]
    assert isinstance(reserva, list)
    assert reserva[0] == {"provider": "anthropic", "model": "claude-opus-5-5"}
    assert all(set(entrada) >= {"provider", "model"} for entrada in reserva)
    assert "fallback_model" not in overlay, "a chave antiga duplicaria a reserva"


def _chaves(no: Any) -> set[str]:
    if isinstance(no, dict):
        return set(no) | {c for v in no.values() for c in _chaves(v)}
    if isinstance(no, list):
        return {c for v in no for c in _chaves(v)}
    return set()


def test_sem_parametro_de_amostragem(overlay: dict) -> None:
    """Fable 5.1, Opus 5.5 e Opus 5 recusam amostragem com erro 400."""
    assert not _chaves(overlay) & {"temperature", "top_p", "top_k"}


def test_plugins_enabled_e_lista_de_nomes(overlay: dict) -> None:
    """O defeito que este arquivo de teste existe para impedir de voltar."""
    habilitados = overlay["plugins"]["enabled"]
    assert isinstance(habilitados, list), (
        "plugins.enabled é lista de nomes; um booleano aqui apaga a lista "
        "e desliga o guard-rail numérico sem nenhum aviso"
    )
    assert "guardrail-numerico" in habilitados


def test_a_consultora_nao_reescreve_as_proprias_skills(overlay: dict) -> None:
    """Sem lembrete de criar skill e com a escrita de skill esperando aprovação."""
    assert overlay["skills"]["creation_nudge_interval"] == 0
    assert overlay["skills"]["write_approval"] is True


def test_nao_declara_chave_de_skill_que_nao_existe(overlay: dict) -> None:
    """`skills` não tem `enabled` no esquema do Hermes. Inventar chave é ruído."""
    assert "enabled" not in overlay["skills"]


def test_a_lista_de_skills_desligadas_nao_e_fixa(overlay: dict) -> None:
    """Lista fixa envelhece a cada versão do Hermes: o bootstrap a calcula da pasta."""
    assert "disabled" not in overlay["skills"]


def test_memoria_so_para_preferencia_de_conversa(overlay: dict) -> None:
    """O dossiê é a fonte da verdade; o USER.md guarda só preferência de conversa."""
    memoria = overlay["memory"]
    assert "enabled" not in memoria, "memory usa memory_enabled e user_profile_enabled"
    assert memoria["memory_enabled"] is False
    assert memoria["user_profile_enabled"] is True
    assert memoria["nudge_interval"] == 0, (
        "a revisão em segundo plano escreveria fatos da cozinha"
    )


def test_nenhuma_credencial_no_overlay() -> None:
    """Este arquivo é versionado: segredo aqui vira segredo no GitHub."""
    bruto = OVERLAY.read_text(encoding="utf-8").lower()
    for proibido in ("api_key", "token", "secret", "password", "sk-", "credential"):
        assert proibido not in bruto, (
            f"{proibido!r} não pode aparecer num arquivo versionado"
        )


def test_limites_de_memoria_explicam_por_que_o_dossie_existe(overlay: dict) -> None:
    """1.375 caracteres não cabem o perfil de cozinha inteiro; daí o SQLite."""
    assert overlay["memory"]["user_char_limit"] == 1375
    assert overlay["memory"]["memory_char_limit"] == 2200


def test_a_agente_nao_tem_arquivo_terminal_nem_computador(overlay: dict) -> None:
    """Ela vasculhou a pasta pessoal atrás da planilha quando tinha essas ferramentas."""
    desligados = set(overlay["agent"]["disabled_toolsets"])
    assert {
        "file",
        "terminal",
        "code_execution",
        "computer_use",
        "browser",
    } <= desligados
    assert "web" not in desligados, "pesquisar receita na web é o §2.1"
    assert "skills" not in desligados, "é por ele que ela abre as skills da consultoria"
    assert "memory" not in desligados


# --------------------------------------------------------------------------- #
# A fusão                                                                      #
# --------------------------------------------------------------------------- #

fundir = configurar_perfil.fundir


def test_fusao_preserva_o_que_nao_esta_no_overlay() -> None:
    """Credencial e preferência que o `--clone` trouxe não podem sumir."""
    perfil = {
        "model": {"default": "outro", "provider": "anthropic"},
        "auth": {"chave": "nao-me-apague"},
        "terminal": {"backend": "docker"},
    }
    fundir(perfil, {"model": {"default": "claude-fable-5-1"}})

    assert perfil["model"]["default"] == "claude-fable-5-1"
    assert perfil["model"]["provider"] == "anthropic"
    assert perfil["auth"]["chave"] == "nao-me-apague"
    assert perfil["terminal"]["backend"] == "docker"


def test_fusao_substitui_lista_inteira() -> None:
    """Lista é substituída, não concatenada: "metade da antiga" nunca é o certo."""
    perfil = {"plugins": {"enabled": ["velho"], "disabled": ["x"]}}
    fundir(perfil, {"plugins": {"enabled": ["guardrail-numerico"]}})

    assert perfil["plugins"]["enabled"] == ["guardrail-numerico"]
    assert perfil["plugins"]["disabled"] == ["x"]


def test_fusao_e_idempotente(overlay: dict) -> None:
    """Rodar o bootstrap duas vezes tem que dar o mesmo resultado."""
    perfil: dict = {"model": {"provider": "anthropic"}}

    fundir(perfil, overlay)
    uma_vez = yaml.safe_dump(perfil, sort_keys=True)
    fundir(perfil, overlay)

    assert yaml.safe_dump(perfil, sort_keys=True) == uma_vez


def test_fusao_nao_apaga_chave_ausente_no_overlay() -> None:
    """A fusão não remove: é por isso que tirar chave do overlay não a desfaz.

    Consequência prática: quando uma chave errada entra no overlay e é aplicada,
    tirá-la do arquivo não limpa o perfil de quem já rodou o bootstrap. Foi o que
    aconteceu com `skills.enabled`, e teve que ser removido à mão.
    """
    perfil = {"skills": {"creation_nudge_interval": 15, "enabled": True}}
    fundir(perfil, {"skills": {"creation_nudge_interval": 0}})
    assert "enabled" in perfil["skills"]


# --------------------------------------------------------------------------- #
# As skills desligadas e o perfil inteiro                                      #
# --------------------------------------------------------------------------- #


def _skill(pasta: Path, categoria: str, diretorio: str, nome: str | None) -> None:
    alvo = pasta / categoria / diretorio
    alvo.mkdir(parents=True)
    cabecalho = f"---\nname: {nome}\ndescription: x\n---\n" if nome else ""
    (alvo / "SKILL.md").write_text(f"{cabecalho}# {diretorio}\n", encoding="utf-8")


@pytest.fixture
def perfil(tmp_path: Path) -> Path:
    """Um perfil clonado: skills genéricas do Hermes e as da consultoria já copiadas."""
    pasta = tmp_path / "perfil"
    skills = pasta / "skills"
    _skill(skills, "productivity", "notion", "notion")
    _skill(skills, "software-development", "spike", "spike")
    _skill(skills, "email", "himalaya", None)  # sem cabeçalho: vale o nome da pasta
    _skill(skills, "autonomous-ai-agents", "hermes-agent", "hermes-agent")
    for arquivo in SKILLS_DA_CONSULTORIA.rglob("SKILL.md"):
        destino = skills / arquivo.relative_to(SKILLS_DA_CONSULTORIA)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(arquivo.read_text(encoding="utf-8"), encoding="utf-8")
    (pasta / "config.yaml").write_text(
        "# veio do --clone\n"
        "model:\n  default: claude-opus-5\n  provider: anthropic\n"
        "auth:\n  chave: nao-me-apague\n"
        "skills:\n  disabled: [velha]\n",
        encoding="utf-8",
    )
    return pasta


def test_desliga_todas_as_skills_do_perfil_menos_as_da_consultoria(
    perfil: Path,
) -> None:
    desligadas = configurar_perfil.skills_desligadas(
        perfil / "skills", SKILLS_DA_CONSULTORIA
    )

    assert desligadas == ["himalaya", "notion", "spike"]
    nossas = configurar_perfil.nomes_das_skills(SKILLS_DA_CONSULTORIA)
    assert len(nossas) == 5
    assert not nossas & set(desligadas)
    assert "hermes-agent" not in desligadas, (
        "o Hermes não deixa desligar; listar seria fingir"
    )


def test_o_perfil_configurado_e_o_mesmo_na_segunda_vez(
    perfil: Path, tmp_path: Path
) -> None:
    config = perfil / "config.yaml"
    argv = ["configurar_perfil.py", str(config), str(tmp_path / "venv"), str(RAIZ)]

    assert configurar_perfil.main(argv) == 0
    primeira = config.read_text(encoding="utf-8")
    assert configurar_perfil.main(argv) == 0
    assert config.read_text(encoding="utf-8") == primeira

    dados = yaml.safe_load(primeira)
    assert dados["auth"]["chave"] == "nao-me-apague"
    assert dados["model"]["default"] == "claude-fable-5-1"
    assert dados["fallback_providers"][0]["model"] == "claude-opus-5-5"
    assert dados["skills"]["disabled"] == ["himalaya", "notion", "spike"]
    assert dados["skills"]["creation_nudge_interval"] == 0
    mise = dados["mcp_servers"]["mise"]
    assert mise["args"] == ["-m", "gateway.principal"]
    assert mise["env"]["MISE_DOSSIE"] == str(RAIZ / ".estado" / "dossie.db")
    assert primeira.startswith("# veio do --clone"), (
        "o comentário do perfil continua lá"
    )
