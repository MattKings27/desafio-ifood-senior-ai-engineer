"""O registro das ferramentas por área.

O servidor tinha mil e quinhentas linhas e toda ferramenta nova precisava
editá-lo. Agora cada área registra as suas; estes testes garantem que a divisão
não perdeu, duplicou nem mudou nenhuma ferramenta.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mise import mcp_server, serializacao
from mise.ferramentas import (
    REGISTRADORES,
    avaliacoes,
    cardapio,
    conhecimento,
    descoberta,
    despensa,
    estimativa,
    orcamento,
    perfil,
    preco,
    receitas,
)
from mise.mcp_server import abrir_sessao, construir_servidor

PLANILHA = Path(__file__).resolve().parents[3] / "dados" / "despensa_dona_maria.xlsx"

POR_AREA = {
    despensa: {
        "diagnostico_despensa",
        "custo_unitario",
        "converter_medida_culinaria",
        "consultar_planilha",
        "atualizar_despensa",
    },
    perfil: {"consultar_perfil", "registrar_resposta", "proxima_pergunta"},
    receitas: {"avaliar_receita", "comparar_candidatas", "buscar_receita_na_web"},
    descoberta: {"pauta_de_descoberta"},
    avaliacoes: {"registrar_avaliacao_da_receita"},
    preco: {
        "calcular_cmv",
        "cenarios_preco",
        "testar_sensibilidade",
        "registrar_preco_mercado",
        "consultar_precos_de_mercado",
        "buscar_preco_na_web",
    },
    estimativa: {"estimar_preco_preliminar"},
    conhecimento: {"consultar_conhecimento"},
    orcamento: {"consultar_orcamento", "registrar_compra"},
    cardapio: {"registrar_decisao", "registrar_gosto", "consultar_gostos", "consultar_cardapio"},
}


class ServidorQueAnota:
    """Só guarda os nomes que cada registrador declara, sem montar schema."""

    def __init__(self) -> None:
        self.nomes: list[str] = []

    def tool(self) -> Any:
        def decorar(fn: Any) -> Any:
            self.nomes.append(fn.__name__)
            return fn

        return decorar


@pytest.fixture
def sessao(tmp_path: Path) -> Any:
    s = abrir_sessao(planilha=PLANILHA, banco=tmp_path / "dossie.db")
    yield s
    s.dossie.fechar()


@pytest.mark.parametrize("area", list(POR_AREA), ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_cada_area_registra_so_as_suas(area: Any, sessao: Any) -> None:
    servidor = ServidorQueAnota()
    area.registrar(servidor, sessao)
    assert set(servidor.nomes) == POR_AREA[area]
    assert len(servidor.nomes) == len(set(servidor.nomes))


def test_os_registradores_cobrem_todas_as_areas_uma_vez() -> None:
    assert REGISTRADORES == tuple(area.registrar for area in POR_AREA)


async def test_nenhuma_ferramenta_some_ou_se_repete(sessao: Any) -> None:
    servidor = construir_servidor(sessao)
    nomes = [t.name for t in await servidor.list_tools()]
    assert len(nomes) == len(set(nomes)) == 27
    assert set(nomes) == set().union(*POR_AREA.values())


@pytest.mark.parametrize(
    "nome",
    [
        "_avaliacao_json",
        "_erro_json",
        "_reais",
        "_receita_json",
        "_resposta",
        "prato_para_auditoria",
        "protegido",
    ],
)
def test_serializacao_continua_importavel_do_servidor(nome: str) -> None:
    """Quem importava estes nomes de `mise.mcp_server` (a API HTTP) continua funcionando."""
    assert getattr(mcp_server, nome) is getattr(serializacao, nome)
    assert nome in mcp_server.__all__
