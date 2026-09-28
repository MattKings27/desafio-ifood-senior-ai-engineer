"""Perfil da cozinha e ordenação das perguntas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mise import perfil_historico
from mise.elicitacao import montar_plano
from mise.perfil import PERGUNTAS_OPERACIONAIS
from mise.serializacao import _resposta, protegido
from mise.taxonomia import EQUIPAMENTOS_POR_ID, TECNICAS_POR_ID

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

    from mise.mcp_server import Sessao


def registrar(servidor: MCPServer, sessao: Sessao) -> None:
    """Perfil da cozinha e ordenação das perguntas."""

    # --- perfil e elicitação ---------------------------------------------- #

    @servidor.tool()
    @protegido
    async def consultar_perfil() -> str:
        """O que já sabemos sobre a cozinha dela: equipamentos, técnicas e limites.

        `ela_confirmou` é o que ela respondeu. `pressuposto` é o que o sistema
        supõe de qualquer cozinha e ninguém perguntou: nunca diga a ela que ela
        disse algo que está em `pressuposto`. Restrição `null` é desconhecida.
        `ela_disse_que_nao_sabe` é o que ela respondeu "não sei": ela respondeu,
        e a resposta foi essa.
        """
        p = sessao.perfil
        ultimos = perfil_historico.ultimos_por_item(sessao.dossie).values()
        tem = [(i, EQUIPAMENTOS_POR_ID[i].nome) for i in p.equipamentos_conhecidos]
        domina = [(i, TECNICAS_POR_ID[i].nome) for i in p.tecnicas_dominadas]
        return _resposta(
            {
                "completude": f"{p.completude:.0%}",
                "resumo": p.resumo(),
                "ela_confirmou": {
                    "tem": sorted(n for i, n in tem if not p.pressuposto(i)),
                    "domina": sorted(n for i, n in domina if not p.pressuposto(i)),
                    "nao_tem": sorted(EQUIPAMENTOS_POR_ID[i].nome for i in p.equipamentos_ausentes),
                    "nao_domina": sorted(TECNICAS_POR_ID[i].nome for i in p.tecnicas_ausentes),
                },
                "pressuposto": {
                    "tem": sorted(n for i, n in tem if p.pressuposto(i)),
                    "domina": sorted(n for i, n in domina if p.pressuposto(i)),
                },
                "restricoes": {
                    campo: getattr(p.restricoes, campo) for campo in PERGUNTAS_OPERACIONAIS
                },
                "ainda_em_aberto": len(p.equipamentos_em_aberto) + len(p.tecnicas_em_aberto),
                "ela_disse_que_nao_sabe": sorted(
                    e.texto for e in perfil_historico.itens_que_ela_nao_sabe(ultimos)
                ),
            }
        )

    @servidor.tool()
    @protegido
    async def registrar_resposta(tipo: str, campo: str, resposta: str) -> str:
        """Grava o que a Dona Maria respondeu à pergunta do portão.

        `tipo` e `campo` são os que `avaliar_receita` ou `proxima_pergunta`
        devolveram. `resposta`:
        - equipamento, tecnica: "tem" ou "nao_tem" (sim/não também valem)
        - operacional: um número (bocas, litros, porções, aparelhos), ou
          sim/não para `tem_gas_sobrando`; `tempo_max_por_fornada_min` vai em
          horas, como ela disse ("2 horas", "1,5 hora", "1h30"; um número
          sozinho é em horas), e o motor guarda em minutos
        - gosto: `campo` é o prato; "gosta" ou "nao_gosta"
        - cozinha: o sim dela à pergunta de confirmar o que toda cozinha tem
          (a que vem em `confirmar_a_cozinha` de `avaliar_receita`, ou na recusa
          do aceite e da compra); `campo` é o `receita_id`, ou "toda_cozinha"
          para confirmar tudo o que ainda é suposto; `resposta` é "tem". O item
          que ela não tiver vai sozinho, como equipamento ou técnica
        - em qualquer tipo, "nao_sei" quando ela diz que não sabe: apaga a
          resposta anterior e o item fica em aberto, e o portão pergunta de novo
          quando uma receita precisar. Vale também para o que toda cozinha tem
          (fogão, panela, geladeira): ele deixa de ser suposto. "Não sei" nunca
          vira "não tem"; já o "não tem" dela bloqueia as receitas que precisam
          do item, inclusive do que toda cozinha tem.
        A resposta traz `impacto`: as receitas em avaliação que passaram a dar,
        as que deixaram de dar e as que continuam dependendo de uma resposta.
        Pergunta de ingrediente não passa por aqui: preço do que falta vai em
        `registrar_preco_mercado`, com a quantidade que o preço compra; peso de
        embalagem ou medida em gramas entra na receita, reenviada ao portão.
        Resposta que não dá para entender ("talvez", "mais ou menos") é recusada,
        não adivinhada: pergunte de outro jeito.
        Para modo de preparo, rendimento e tempo de cozimento (`tempo_cozimento_min`),
        reenvie a receita em `avaliar_receita` com o campo preenchido.
        """
        return _resposta(sessao.responder(tipo, campo, resposta))

    @servidor.tool()
    @protegido
    async def proxima_pergunta() -> str:
        """A pergunta que decide mais pratos agora, entre as candidatas em avaliação.

        Perguntar na ordem certa é o que separa uma conversa de um formulário.
        `ela_disse_que_nao_sabe` verdadeiro quer dizer que ela já respondeu
        "não sei" a esta pergunta.
        """
        plano = montar_plano(
            list(sessao.candidatas.values()),
            sessao.perfil,
            sessao.despensa,
            avaliador=sessao.avaliar,
        )
        if not plano:
            return _resposta(
                {
                    "ha_pergunta": False,
                    "resumo": plano.resumo(),
                    "aptas": list(plano.aptas),
                    "bloqueadas": list(plano.bloqueadas),
                }
            )
        melhor = plano.proxima
        assert melhor is not None
        tipo = melhor.pergunta.tipo.name.lower()
        # A pergunta do gosto é sobre um prato, e `registrar_resposta` grava o gosto
        # pelo prato: o campo que volta é o prato, não a palavra "gosto".
        campo = (
            melhor.receitas_afetadas[0]
            if tipo == "gosto" and melhor.receitas_afetadas
            else melhor.campo
        )
        return _resposta(
            {
                "ha_pergunta": True,
                "pergunta": melhor.texto,
                "tipo": tipo,
                "campo": campo,
                "ela_disse_que_nao_sabe": perfil_historico.ela_disse_que_nao_sabe(
                    sessao.dossie, tipo, campo
                ),
                "por_que_esta": melhor.justificativa(),
                "pratos_afetados": list(melhor.receitas_afetadas),
                "seguintes": [p.texto for p in plano.proximas(3)[1:]],
                "resumo": plano.resumo(),
            }
        )


__all__ = ["registrar"]
