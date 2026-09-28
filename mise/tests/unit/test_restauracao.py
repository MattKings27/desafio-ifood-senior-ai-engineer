"""Restaurar o dossiê: as linhas dela saem, o catálogo volta à página, e o arquivo fica.

A rota da tela (`gateway.rotas.dados`) guarda a cópia e esvazia as conversas;
aqui é o motor: o que sai de cada tabela, o que o catálogo guarda da página, o
catálogo antigo sem a página guardada, e a cópia do SQLite com o que está no
WAL. A despensa em cache de outra conexão é refeita na leitura seguinte.
"""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from mise.catalogo import voltar_ao_que_foi_lido
from mise.dinheiro import Dinheiro
from mise.dossie import Decisao
from mise.perfil import Gosto
from mise.restauracao import TABELAS_DELA, restaurar_dossie

sys.path.insert(0, str(Path(__file__).resolve().parent))

import receitas_de_teste as rt


def test_restaurar_tira_o_que_e_dela_e_deixa_a_pagina(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    rt.cozinha_confirmada(sessao)
    carne = rt.da_web(sessao, rt.CARNE_URL, rt.CARNE)
    sessao.catalogo.completar(
        carne.slug,
        replace(carne.receita, rendimento_porcoes=9),
        [("rendimento_porcoes", "9 porções")],
    )
    ditada = rt.ditada(sessao, **rt.ARROZ_COM_FRANGO)
    sessao.dossie.registrar_gosto(ditada.nome, Gosto.GOSTA)
    sessao.dossie.registrar_decisao(ditada.nome, Decisao.RECUSADO)
    sessao.dossie.registrar_gasto("coco ralado", Dinheiro(Decimal("5.50")))
    sessao.editavel.acabou("sal")
    assert "Sal" in sessao.despensa.itens
    assert sessao.despensa.itens["Sal"].estoque.valor == 0

    restaurado = restaurar_dossie(sessao.dossie)

    assert restaurado.mudou
    assert set(restaurado.apagadas) <= set(TABELAS_DELA)
    assert restaurado.apagadas["decisoes"] == 1
    assert restaurado.apagadas["gastos"] == 1
    assert restaurado.apagadas["gostos"] == 1
    assert restaurado.apagadas["perfil"] == 1
    assert restaurado.apagadas["despensa_eventos"] == 1
    assert (restaurado.catalogo.ditas, restaurado.catalogo.sem_as_respostas) == (1, 1)
    assert restaurado.catalogo.mantidas == 1
    voltou = sessao.catalogo.obter(carne.slug)
    assert voltou is not None
    assert voltou.respostas == ()
    assert voltou.receita == carne.receita
    assert sessao.catalogo.obter(ditada.slug) is None
    assert sessao.dossie.orcamento().restante == Dinheiro(Decimal(80))
    assert sessao.dossie.historico() == ()
    # A despensa em cache nesta conexão só é refeita quando alguém pede.
    sessao.editavel.recarregar()
    assert sessao.despensa.itens["Sal"].estoque.valor == 1

    de_novo = restaurar_dossie(sessao.dossie)
    assert not de_novo.mudou
    sessao.dossie.fechar()


def test_outra_conexao_ve_o_recomeco_sem_recarregar(tmp_path: Path) -> None:
    """O agente é outro processo: o `data_version` muda e a despensa dele é refeita."""
    sessao = rt.sessao_nova(tmp_path)
    consultora = rt.sessao_nova(tmp_path)
    sessao.editavel.acabou("sal")
    assert consultora.despensa.itens["Sal"].estoque.valor == 0
    restaurar_dossie(sessao.dossie)
    assert consultora.despensa.itens["Sal"].estoque.valor == 1
    sessao.dossie.fechar()
    consultora.dossie.fechar()


def test_catalogo_antigo_sem_a_pagina_guardada(tmp_path: Path) -> None:
    """A receita completada antes da coluna da página sai: a resposta dela não fica escondida."""
    sessao = rt.sessao_nova(tmp_path)
    carne = rt.da_web(sessao, rt.CARNE_URL, rt.CARNE)
    milho = rt.da_web(sessao, rt.MILHO_URL, rt.MILHO)
    with sessao.dossie.transacao() as cur:
        cur.execute("UPDATE catalogo SET receita_lida = NULL")
        cur.execute(
            'UPDATE catalogo SET respostas = \'[{"campo": "x"}]\' WHERE slug = ?', (carne.slug,)
        )
        volta = voltar_ao_que_foi_lido(cur)
    assert (volta.sem_a_pagina, volta.mantidas) == (1, 1)
    assert sessao.catalogo.obter(milho.slug) is not None
    assert sessao.catalogo.obter(carne.slug) is None
    sessao.dossie.fechar()


def test_a_copia_do_dossie_leva_o_que_esta_no_wal(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    sessao.dossie.registrar_decisao("Arroz com frango", Decisao.ADIADO)
    copia = sessao.dossie.copiar_para(tmp_path / "copias" / "agora" / "dossie.db")
    with closing(sqlite3.connect(copia)) as conexao:
        assert conexao.execute("SELECT prato FROM decisoes").fetchall() == [("Arroz com frango",)]
    sessao.dossie.fechar()
