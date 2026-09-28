"""Servidor MCP: a única porta pela qual o agente acessa o motor.

O Hermes conversa; este servidor decide e calcula. A separação é deliberada e
está na assinatura das ferramentas: não existe tool que devolva um preço sem
antes ter passado pelo portão de viabilidade, porque `calcular_cmv` recusa
receita não aprovada.

Todas as respostas são JSON com três garantias:

- **derivação junto do número**: nenhum valor aparece sem a conta que o
  produziu, para o agente poder mostrar à Dona Maria e ela poder discordar;
- **estimativa com fonte, nunca chute**: o que a planilha e a receita não dizem
  (o peso de uma embalagem, uma medida, o preço do que falta) vem estimado, com
  a fonte e dito como estimativa, e sem fonte não há número; à Dona Maria só se
  pergunta gosto, equipamento, técnica e rotina;
- **erro tipado**: falha vem com `erro`, `categoria` e, quando cabe, a
  pergunta que destrava, em vez de stack trace.
"""

from __future__ import annotations

import logging
import math
import os
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, TypeVar

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    # Só para tipagem: o import real é tardio porque o pacote `mcp` custa ~300 ms
    # a carregar, e o motor precisa ser importável sem ele (testes, CLI, dashboard).
    from mcp.server.mcpserver import MCPServer
    from retrieval.extrator import ReceitaExtraida

from mise import __version__, perfil_historico
from mise.avaliacoes import Avaliacoes
from mise.casamento import Estrategia, casar, motivo_do_sinonimo
from mise.catalogo import (
    Catalogo,
    LinhaRelida,
    OrigemNoCatalogo,
    PaginaLida,
    ReceitaDoCatalogo,
    TemposDaReceita,
    chave_do_nome,
    id_da_receita,
    reler_as_linhas,
    semear_o_catalogo,
)
from mise.certeza import (
    TODA_COZINHA,
    Acao,
    ItemSuposto,
    exigir_cozinha_confirmada,
    pressupostos_da_cozinha,
    pressupostos_da_receita,
    texto_da_confirmacao,
)
from mise.cmv import CMV, calcular
from mise.complemento import completar, diferencas, responder, responder_peso
from mise.despensa import Despensa, carregar_despensa
from mise.despensa_editavel import DespensaEditavel
from mise.despensa_json import slug_da_receita
from mise.dinheiro import Dinheiro
from mise.dossie import Canal, Decisao, Dossie, OrigemPreco, PrecoMercado, RegistroDecisao
from mise.elicitacao import CAMPOS_DA_RECEITA
from mise.erros import Ausente, ContaNaoConfere, ErroDeDados, ErroDeUso, ErroMise
from mise.perfil import (
    FORMATOS_OPERACIONAIS,
    PERGUNTAS_OPERACIONAIS,
    Gosto,
    PerfilCozinha,
    Posse,
    TipoDeCampo,
    minutos_ditos,
)
from mise.preco import RETENCAO, TAXA_PLATAFORMA, lucro_em, montar_cenarios
from mise.receita import IngredienteReceita, Origem, Receita
from mise.referencias import PrecosDeReferencia, precos_da_despensa

# A serialização mora em `mise.serializacao`; os nomes continuam importáveis
# daqui (estão em `__all__`) para quem já os usava, como a API HTTP.
from mise.serializacao import (
    _avaliacao_json,
    _erro_json,
    _reais,
    _receita_json,
    _resposta,
    prato_para_auditoria,
    protegido,
)
from mise.taxonomia import equipamento, tecnica
from mise.viabilidade import PORCAO_PADRAO_G, Avaliacao, PesoPedido, avaliar

NOME_SERVIDOR: Final = "mise"

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

INSTRUCOES: Final = """\
Ferramentas do Sabor da Maria: a despensa, a cozinha, as receitas, o preço e o
cardápio da Dona Maria, lidos e gravados nos mesmos dados que ela vê nas telas.

Nunca calcule custo, preço, margem ou orçamento de cabeça: os números daqui saem
da planilha dela com a conta que os produziu, e é essa conta que se mostra a ela.
Receita da internet entra pela página que buscar_receita_na_web lê e daí em
diante se chama pelo receita_id, sem redigitar. Preço final, compra e aceite só
valem para o prato que avaliar_receita liberou; a recusa vem com a pergunta que
falta.

Despensa
diagnostico_despensa: o que ela tem, onde o dinheiro está parado e o que a planilha não resolve.
custo_unitario: o custo por quilo, litro ou unidade de um item, com a conta.
consultar_planilha: a planilha dela em texto, com as mudanças, a conta de hoje e o extrato.
atualizar_despensa: anota o que ela contou que mudou na despensa e devolve o antes e o depois.
converter_medida_culinaria: quanto pesa uma xícara ou uma colher daquele ingrediente.

Cozinha
consultar_perfil: a cozinha dela, separando o que ela confirmou do que é só pressuposto.
proxima_pergunta: a pergunta que decide mais pratos agora, com o motivo e as opções.
registrar_resposta: grava a resposta dela sobre a cozinha e o sim ao que toda cozinha tem.

Receitas
buscar_receita_na_web: lê a página de uma receita, guarda com a fonte e devolve o receita_id.
avaliar_receita: confere se ela consegue fazer a receita e recebe o que ela disse sobre ela.
comparar_candidatas: as receitas em avaliação lado a lado, e o catálogo separado como na tela.
registrar_gosto: se ela gosta de fazer um prato e o impedimento que ela vê.
consultar_gostos: o que ela já disse de cada prato.
registrar_avaliacao_da_receita: gosto, estrelas e notas dela, com a pontuação e o ranking.
pauta_de_descoberta: as buscas prontas por pratos clássicos e pelo dinheiro parado, e os limites.
consultar_conhecimento: busca nas telas e na base de cozinha; trechos com fonte, ou "não sei".

Preço
estimar_preco_preliminar: um preço preliminar, com premissas e fontes; diga que é preliminar.
calcular_cmv: o custo de ingrediente de uma porção, linha a linha, da receita liberada.
cenarios_preco: três caminhos de preço com a taxa de 10% aberta, para ela escolher.
testar_sensibilidade: a conta de um preço que ela propôs e quanto de alta no insumo ele aguenta.
registrar_decisao: o que ela decidiu sobre um prato (aceito, recusado, adiado), com o preço dela.

Compras e cardápio
buscar_preco_na_web: o preço médio em São Paulo do que falta sem preço; nunca pergunte a ela.
registrar_preco_mercado: o preço que ela disser do que falta comprar (nunca perguntado).
consultar_precos_de_mercado: as cotações que ela já deu.
consultar_orcamento: quanto resta dos R$ 80,00 de complementos.
registrar_compra: o que ela comprou para um prato liberado; sai do orçamento e vira estoque.
consultar_cardapio: os pratos que ela aceitou, com o preço, o lucro e a trilha.
"""


# --------------------------------------------------------------------------- #
# Modelos de entrada
# --------------------------------------------------------------------------- #


class IngredienteEntrada(BaseModel):
    """Uma linha da lista de ingredientes de uma receita."""

    texto: str = Field(description="A linha como está escrita na receita original")
    nome: str = Field(description="Só o nome do ingrediente, sem quantidade")
    quantidade: float | None = Field(
        default=None, description="Quantidade numérica; omita para 'a gosto'"
    )
    medida: str = Field(
        default="", description="Unidade: g, kg, ml, xicara, colher de sopa, ovo, dente de alho"
    )
    opcional: bool = Field(default=False, description="Ingrediente dispensável na receita")
    item_da_despensa: str | None = Field(
        default=None,
        description="Só quando ela corrige a decisão sobre o item parecido ('considerei que X "
        "não é o seu Y'): o nome do item da despensa que ela disse ser esta linha (Y), "
        'ou "" se ela disse que não é. Omita em todos os outros casos.',
    )
    peso: str | None = Field(
        default=None,
        description="Só quando ela mesma corrige o peso de uma linha (o peso de referência "
        "que a conferência usou, com o receita_id e o texto da linha): o peso que ela disse, "
        "em gramas ou quilos ('300 g', '0,3 kg'). Nunca um palpite. Omita nos outros casos.",
    )
    por_unidade: bool | None = Field(
        default=None,
        description="Junto de peso: true quando é o peso de uma unidade (um peito, uma "
        "colher), que é o que a pergunta pede; false quando é o da linha inteira (as duas "
        "colheres juntas). Omitido, vale o que ela disse ('cada', 'as duas'), senão uma unidade.",
    )

    def para_dominio(self) -> IngredienteReceita:
        """O ingrediente do motor. Sem quantidade, a linha original é interpretada.

        A tela manda a linha como ela colou ("2 xícaras de farinha") e um nome,
        sem quantidade. Tratar isso como "a gosto" zerava o custo do prato
        inteiro. Quem decide se é "a gosto" é o texto, não a ausência do campo.

        Quando a leitura separa uma medida, o nome que ela extrai vale mais que
        o palpite de quem mandou: de "2 colheres de sopa de óleo" a tela
        adivinhava "sopa de óleo", e o prato pedia para comprar sopa de óleo.
        """
        if self.quantidade is not None:
            return IngredienteReceita(
                texto_original=self.texto,
                nome=self.nome,
                quantidade=Decimal(str(self.quantidade)),
                medida=self.medida,
                opcional=self.opcional,
                item_da_despensa=self.item_da_despensa,
            )
        from retrieval.quantidades import interpretar_linha  # noqa: PLC0415

        lida = interpretar_linha(self.texto)
        return IngredienteReceita(
            texto_original=self.texto,
            nome=lida.nome if lida.medida else (self.nome.strip() or lida.nome),
            quantidade=lida.quantidade,
            medida=lida.medida,
            observacao=lida.observacao,
            opcional=self.opcional or lida.opcional,
            # A linha que a leitura não entendeu continua não entendida: vira
            # pergunta a ela, e não "a gosto" em silêncio.
            entendida=lida.entendida,
            item_da_despensa=self.item_da_despensa,
        )


class ReceitaEntrada(BaseModel):
    """Uma receita digitada por quem chama: a que ela dita, ou a resposta dela sobre uma guardada.

    Receita da internet não entra por aqui: entra pela página que o servidor
    lê (`buscar_receita_na_web`) e depois é chamada pelo `receita_id`. Por isso
    a receita digitada é sempre "como a senhora me passou", mesmo que venha com
    um endereço: endereço digitado não é procedência, é só um texto.
    """

    nome: str
    ingredientes: list[IngredienteEntrada]
    rendimento_porcoes: int | None = Field(
        default=None,
        ge=1,
        description="Quantas porções a receita ORIGINAL rende. Crítico: o delivery "
        "vende 1 porção. Omita se ninguém disse: a avaliação pergunta em vez de chutar.",
    )
    modo_preparo: list[str] = Field(
        default_factory=list,
        description="Os passos. São lidos para inferir forno, batedeira, técnicas.",
    )
    tempo_preparo_min: int | None = Field(
        default=None,
        ge=0,
        description="Tempo de preparo que a receita declara (prepTime), a mão na massa "
        "antes do fogo. Não é tempo no fogo: não decide se cabe na cozinhada dela.",
    )
    tempo_cozimento_min: int | None = Field(
        default=None,
        ge=0,
        description="Tempo de cozimento que a receita declara (cookTime), com fogo ou "
        "forno ligado. Vale quando os passos não dizem o tempo. Omita se ninguém disse.",
    )
    tempo_total_min: int | None = Field(
        default=None,
        ge=0,
        description="Tempo total que a receita declara (totalTime), com as esperas de "
        "geladeira e descanso. Não é tempo no fogo.",
    )
    url: str | None = Field(
        default=None,
        description="Só para achar a receita que o servidor já leu desse endereço. "
        "Receita da internet entra por buscar_receita_na_web e se chama pelo receita_id; "
        "a receita digitada é a que ela dita, e nunca vira receita da internet.",
    )
    fonte: str | None = Field(
        default=None,
        description="Ignorada: a fonte de uma receita vem da página que o servidor leu.",
    )

    def para_dominio(self) -> Receita:
        """A receita como ela passou: sem endereço e sem fonte, mesmo que tenham vindo.

        Um endereço digitado marcava a receita como da internet, e a receita
        redigitada pelo modelo, com as quantidades que ele quisesse, passava a
        ter a procedência de uma página que ninguém leu. Só a página que o
        servidor buscou é da internet (`Sessao.receita_da_web`).
        """
        return Receita(
            nome=self.nome,
            ingredientes=tuple(i.para_dominio() for i in self.ingredientes),
            rendimento_porcoes=self.rendimento_porcoes or 1,
            rendimento_informado=self.rendimento_porcoes is not None,
            origem=Origem.INFORMADA_POR_ELA,
            modo_preparo=tuple(self.modo_preparo),
            tempo_preparo_min=self.tempo_preparo_min,
            tempo_cozimento_min=self.tempo_cozimento_min,
            tempo_total_min=self.tempo_total_min,
        ).com_exigencias_detectadas()


# --------------------------------------------------------------------------- #
# Estado da sessão
# --------------------------------------------------------------------------- #


#: Recebe o prato (linhas, custo, e opcionalmente preço e lucro) e devolve o
#: parecer: `confere`, `observacao`, `divergencias`, `por`.
Auditor = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class Sessao:
    """Despensa, dossiê e receitas candidatas da consultoria em curso.

    `planilha` é a despensa que ela entregou, e não muda. A despensa de agora
    (`despensa`) é a planilha com as mudanças dela, que moram no dossiê: é lida
    de lá a cada uso, com cache, e por isso o servidor MCP do agente e a API da
    tela, processos diferentes, enxergam a mudança um do outro.
    """

    planilha: Despensa
    dossie: Dossie
    #: Quem refaz a conta de forma independente antes de um preço sair. Vem de
    #: fora: o motor não importa o auditor, senão a auditoria conferiria o código
    #: com ele mesmo. O gateway injeta (A2A ou em processo).
    auditor: Auditor | None = None
    #: Por onde as ações desta sessão chegam: cada ponto de entrada define o seu
    #: (a API da tela, `tela`; o servidor MCP do agente, `conversa`), e decisões e
    #: compras gravam de onde vieram.
    canal: Canal = Canal.CONVERSA
    #: Onde a planilha em texto (`despensa.txt`) é regravada a cada mudança;
    #: `None` não grava arquivo nenhum.
    arquivo_txt: Path | None = None
    #: Procura nos mercados de São Paulo o preço do que falta sem referência,
    #: quando a receita é guardada ou avaliada (`mise.precos_na_web`). Os pontos
    #: de entrada ligam; os testes e a avaliação ficam sem rede.
    pesquisar_precos_ao_guardar: bool = False
    #: Quem procura o preço: `None` é a rede de verdade (`retrieval.precos`).
    pesquisador_de_precos: Any = None
    #: As mudanças dela sobre a planilha (`mise.despensa_editavel`).
    editavel: DespensaEditavel = field(init=False, repr=False)
    _transcricao: str | None = field(default=None, init=False, repr=False)
    _catalogo: Catalogo | None = field(default=None, init=False, repr=False)
    _avaliacoes: Avaliacoes | None = field(default=None, init=False, repr=False)
    _precos_na_web: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.editavel = DespensaEditavel(self.dossie, self.planilha)

    @property
    def despensa(self) -> Despensa:
        """A despensa de agora: a planilha com as mudanças dela.

        É o mesmo objeto enquanto nada muda no dossiê (nenhum processo gravou
        nada desde a última leitura), e um novo depois de qualquer mudança.
        """
        return self.editavel.despensa

    def mudar_despensa(
        self, operacao: Callable[[DespensaEditavel], _T]
    ) -> tuple[_T, dict[str, Any]]:
        """Faz uma mudança na despensa e diz o que ela fez com as receitas em avaliação.

        As receitas são avaliadas antes e depois (a avaliação não grava nada), e
        a planilha em texto é regravada em seguida.
        """
        from mise.despensa_json import receitas_afetadas, vereditos  # noqa: PLC0415

        antes = vereditos(self)
        resultado = operacao(self.editavel)
        afetadas = receitas_afetadas(antes, vereditos(self))
        self.atualizar_planilha_txt()
        return resultado, afetadas

    def planilha_txt(self) -> tuple[int, str]:
        """A versão e o texto da planilha de agora (`.estado/despensa.txt`), sem gravar."""
        from mise.planilha_txt import montar_texto, transcrever_planilha  # noqa: PLC0415

        origem = self.planilha.origem
        if self._transcricao is None and origem is not None:
            try:
                self._transcricao = transcrever_planilha(origem)
            except ErroMise as erro:
                logger.warning("não consegui transcrever a planilha: %s", erro)
        estado = self.editavel.estado()
        extrato = self.dossie.extrato()
        versao = 1 + len(estado.eventos) + len(extrato)
        texto = montar_texto(
            transcricao=self._transcricao,
            nome_da_planilha=origem.name if origem is not None else "planilha",
            estado=estado,
            orcamento=self.dossie.orcamento(),
            extrato=extrato,
            agora=self.dossie.agora(),
            versao=versao,
        )
        return versao, texto

    def atualizar_planilha_txt(self) -> tuple[int, str]:
        """Regrava `despensa.txt` com a despensa e o orçamento de agora.

        O arquivo é derivado do dossiê: se não der para gravar (disco cheio,
        pasta sem permissão), a mudança dela já está salva e continua valendo, e
        o aviso vai para o log.
        """
        from mise.planilha_txt import escrever_atomico  # noqa: PLC0415

        versao, texto = self.planilha_txt()
        if self.arquivo_txt is not None:
            try:
                escrever_atomico(self.arquivo_txt, texto)
            except OSError as erro:
                logger.warning("não consegui gravar %s: %s", self.arquivo_txt, erro)
        return versao, texto

    def auditar(self, prato: dict[str, Any]) -> dict[str, Any] | None:
        """O parecer do auditor sobre um prato; recusa se ele discordar.

        Auditor indisponível devolve `confere: None` e a conta segue, marcada
        como não conferida: a do motor continua correta, só não teve segunda
        opinião. Discordância é outra coisa, e para o preço.
        """
        if self.auditor is None:
            return None
        parecer = self.auditor(prato)
        if parecer.get("confere") is False:
            raise ContaNaoConfere(str(prato.get("prato", "")), parecer)
        return parecer

    @property
    def candidatas(self) -> dict[str, Receita]:
        """As receitas em avaliação, lidas do dossiê: sobrevivem entre turnos."""
        return self.dossie.candidatas()

    def guardar(self, receita: Receita) -> Receita:
        self.dossie.guardar_candidata(receita)
        return receita

    # -- receitas: o catálogo e as que estão em avaliação ------------------- #

    @property
    def catalogo(self) -> Catalogo:
        """O catálogo de receitas deste dossiê: tudo o que o servidor leu ou ela ditou."""
        if self._catalogo is None:
            self._catalogo = Catalogo(self.dossie)
        return self._catalogo

    def candidata_por_id(self, receita_id: str) -> Receita:
        """A receita em avaliação com este id; `Ausente` se nenhuma tem.

        O id é o `slug` do contrato da tela (`mise.catalogo.id_da_receita`): 16
        hex do endereço canônico, ou o slug do nome da receita que ela ditou. A
        receita que está no catálogo mas nunca passou pela conferência também é
        `Ausente` aqui, com o recado de chamar `avaliar_receita` antes: preço e
        compra só saem de receita conferida.
        """
        procurado = receita_id.strip().lower()
        for receita in self.candidatas.values():
            if slug_da_receita(receita) == procurado:
                return receita
        guardada = self.catalogo.obter(procurado)
        if guardada is not None:
            raise Ausente(
                f"{guardada.nome} ainda não passou pela conferência; "
                "chame avaliar_receita com este receita_id antes",
                receita_id=receita_id,
            )
        raise Ausente(
            "não encontrei essa receita entre as que estão em avaliação",
            receita_id=receita_id,
            em_avaliacao=", ".join(sorted(self.candidatas)) or "nenhuma",
        )

    def receita_por_id(self, receita_id: str) -> Receita:
        """A receita com este id, em avaliação ou só no catálogo; `Ausente` se não há."""
        procurado = receita_id.strip().lower()
        for receita in self.candidatas.values():
            if slug_da_receita(receita) == procurado:
                return receita
        guardada = self.catalogo.obter(procurado)
        if guardada is None:
            raise Ausente("não encontrei essa receita", receita_id=receita_id)
        return guardada.receita

    def receita_para_avaliar(
        self, receita_id: str | None, entrada: ReceitaEntrada | None
    ) -> tuple[Receita, str | None]:
        """A receita que a conferência vai avaliar, e um recado para quem chamou (ou `None`).

        - Só o `receita_id`: a receita guardada, como está.
        - O `receita_id` e a `receita`: a guardada, com o que ela respondeu
          (`mise.complemento`): o rendimento ou o preparo que a página não
          trazia, ou quanto vai de uma linha que a leitura não entendeu. O resto
          da receita guardada não muda.
        - Só a `receita`, sem endereço: a receita que ela dita, guardada no
          catálogo como "dita". Ditada de novo com o mesmo nome, é a correção dela.
        - Só a `receita`, com o endereço de uma página já lida: como se viesse o
          `receita_id` dessa página. Endereço que o servidor não leu é recusado:
          receita da internet só entra pela página que o servidor busca.
        """
        if entrada is None:
            if receita_id is None or not receita_id.strip():
                raise ErroDeUso(
                    "informe a receita: o receita_id que buscar_receita_na_web devolveu, "
                    "ou a receita que ela ditou"
                )
            return self.receita_por_id(receita_id), None
        if (receita_id is None or not receita_id.strip()) and (entrada.url or "").strip():
            lida = self.catalogo.por_url(entrada.url or "")
            if lida is None:
                raise ErroDeUso(
                    "não li esse endereço, e receita da internet só entra pela página que eu "
                    "mesma leio. Chame buscar_receita_na_web com o endereço e use o receita_id "
                    "que ela devolve; se a receita é da senhora, mande sem o endereço",
                    url=entrada.url,
                )
            receita_id = lida.slug
        if receita_id is not None and receita_id.strip():
            return self._completar(receita_id, entrada)
        if any(i.peso is not None for i in entrada.ingredientes):
            raise ErroDeUso(
                "o peso que ela disse de uma linha vai com o receita_id da receita, depois "
                "que a conferência perguntou ('Não sei quanto pesa ...')"
            )
        nova = entrada.para_dominio()
        # Escrita de novo (a tela de pôr preço, a cada conferência): o peso e o
        # "é o meu item" que ela já disse das linhas iguais continuam valendo.
        anterior = self.catalogo.obter(id_da_receita(nova))
        if anterior is not None and not anterior.da_internet:
            nova = _com_os_pesos(nova, anterior.receita)
        self._conferir_o_que_ela_confirmou(nova)
        ditada = self.catalogo.guardar_dita(nova)
        return ditada.receita, None

    def peso_pedido(self, receita: Receita, linha: IngredienteReceita) -> PesoPedido | None:
        """O peso que a conferência pede desta linha, sem contar o que ela já disse.

        É a pergunta de medida da linha ("Não sei quanto pesa um peito de
        frango"), quando um peso em gramas a responde, ou a medida de
        referência da tabela do IBGE que ela pode corrigir ("1 peito" = 180 g).
        A linha que se converte sozinha, sem referência, não pede peso, e o que
        ela já disse pode ser corrigido.
        """
        chave = chave_do_nome(linha.texto_original)
        sem_o_peso = replace(
            receita,
            ingredientes=tuple(
                replace(i, peso_g=None) if chave_do_nome(i.texto_original) == chave else i
                for i in receita.ingredientes
            ),
        )
        avaliacao = self.avaliar(sem_o_peso)
        for pergunta in avaliacao.perguntas:
            if pergunta.peso is not None and chave_do_nome(pergunta.campo) == chave:
                return pergunta.peso
        for ajuste in avaliacao.ajustes:
            if (
                ajuste.corrigir_peso is not None
                and chave_do_nome(ajuste.ingrediente.texto_original) == chave
            ):
                return ajuste.corrigir_peso
        return None

    def parecido_da_linha(self, receita: Receita, linha: IngredienteReceita) -> str | None:
        """O item da despensa de "A receita pede alcatra. É o seu miolo de alcatra?", se há."""
        casamento = casar(linha.nome, self.despensa, contexto=receita.nome)
        decidido = casamento.estrategia is Estrategia.PARCIAL or bool(
            motivo_do_sinonimo(linha.nome)
        )
        if decidido and casamento.item is not None:
            return casamento.item.nome
        return None

    def _conferir_o_que_ela_confirmou(self, receita: Receita) -> None:
        """Só vale confirmar o item que a conferência perguntou, e nenhum outro.

        Sem isto, uma linha "alcatra" podia ser dada como o bacon dela, e o custo
        do prato sairia de um item que ela nunca confirmou.
        """
        for linha in receita.ingredientes:
            if not linha.item_da_despensa:
                continue
            parecido = self.parecido_da_linha(receita, linha)
            if parecido != linha.item_da_despensa:
                raise ErroDeUso(
                    f"a linha {linha.texto_original!r} não tem pergunta sobre "
                    f"{linha.item_da_despensa!r}: só confirmo o item que a conferência "
                    "perguntou ('É o seu ...?'), com o nome como veio na pergunta"
                    + (f" ({parecido!r})" if parecido else ""),
                    linha=linha.texto_original,
                )

    def _completar(self, receita_id: str, entrada: ReceitaEntrada) -> tuple[Receita, str | None]:
        """A receita guardada com as respostas dela que vieram junto do id.

        O peso que ela disse de uma linha (`peso`) vai pela mesma porta da tela
        (`responder_sobre_a_receita`), antes do resto: só entra na linha que a
        conferência perguntou. Se não veio mais nada, a resposta acaba aí.
        """
        guardada = self.catalogo.obter(receita_id.strip().lower())
        if guardada is None:
            # Receita em avaliação de antes do catálogo: vale como está.
            return self.candidata_por_id(receita_id), (
                "essa receita é de antes do catálogo: avaliei como estava guardada"
            )
        pesos = [i for i in entrada.ingredientes if i.peso is not None]
        anotados: list[str] = []
        for linha in pesos:
            guardada = self.responder_sobre_a_receita(
                guardada.slug,
                linha.texto,
                linha.peso or "",
                por_unidade=linha.por_unidade,
                peso=True,
            )
            anotados.append(guardada.respostas[-1].valor)
        so_pesos = len(pesos) == len(entrada.ingredientes) and not (
            entrada.rendimento_porcoes or entrada.modo_preparo or entrada.tempo_cozimento_min
        )
        if pesos and so_pesos:
            return guardada.receita, _recado(anotados)
        nova = entrada.para_dominio()
        self._conferir_o_que_ela_confirmou(replace(nova, nome=guardada.nome))
        if not guardada.da_internet:
            if chave_do_nome(nova.nome) != chave_do_nome(guardada.nome):
                raise ErroDeUso(
                    f"o receita_id é de {guardada.nome!r} e a receita que veio é "
                    f"{nova.nome!r}; para outra receita, mande sem o receita_id",
                    receita_id=receita_id,
                )
            ditada = replace(_com_os_pesos(nova, guardada.receita), nome=guardada.nome)
            return self.catalogo.guardar_dita(ditada).receita, _recado(anotados)
        complemento = completar(guardada.receita, nova)
        if not complemento.mudou:
            return guardada.receita, _recado(anotados)
        completa = self.catalogo.completar(
            guardada.slug, complemento.receita, complemento.respostas
        )
        anotados += [f"{campo}: {valor}" for campo, valor in complemento.respostas]
        return completa.receita, _recado(anotados)

    def responder_sobre_a_receita(
        self,
        receita_id: str,
        campo: str,
        resposta: str,
        *,
        por_unidade: bool | None = None,
        peso: bool = False,
    ) -> ReceitaDoCatalogo:
        """A resposta dela a uma pergunta da própria receita, gravada no catálogo.

        `campo` é o da pergunta da conferência: `rendimento_porcoes`,
        `tempo_cozimento_min`, `modo_preparo`, ou o texto de uma linha de
        ingrediente: a que a leitura não entendeu (a resposta é quanto vai), a
        que se parece com um item da despensa ("É o seu miolo de alcatra?"; a
        resposta é sim ou não), ou a de medida que não se converte ("Não sei
        quanto pesa um peito de frango"; a resposta é o peso, de uma unidade ou,
        com `por_unidade` falso, da linha inteira). Só entra o que a receita não
        dizia (`mise.complemento`), e a resposta fica anotada na receita como
        dita por ela. A receita em avaliação é atualizada junto.

        Com `por_unidade` dito, ou `peso` (a conversa mandou o peso na linha), a
        resposta é um peso: na linha que não pede peso, é recusada, em vez de
        virar a quantidade da linha.
        """
        guardada = self.catalogo.obter(receita_id.strip().lower())
        if guardada is None:
            raise Ausente("não encontrei essa receita no catálogo", receita_id=receita_id)
        linha = next(
            (
                i
                for i in guardada.receita.ingredientes
                if chave_do_nome(i.texto_original) == chave_do_nome(campo)
            ),
            None,
        )
        # A linha sem quantidade ("manteiga de sua escolha") recebe quanto vai, nunca um peso.
        sem_quantidade = linha is not None and not linha.quantidade
        pedido = (
            self.peso_pedido(guardada.receita, linha)
            if linha is not None and not sem_quantidade
            else None
        )
        if pedido is not None:
            feito = responder_peso(
                guardada.receita, campo, resposta, uma=pedido.uma, por_unidade=por_unidade
            )
        elif por_unidade is not None or peso:
            raise ErroDeUso(
                "Essa linha não pede peso: a medida dela já entra na conta.", campo=campo
            )
        else:
            parecido = (
                self.parecido_da_linha(guardada.receita, linha) if linha is not None else None
            )
            feito = responder(guardada.receita, campo, resposta, parecido=parecido)
        completa = self.catalogo.completar(guardada.slug, feito.receita, feito.respostas)
        if self.dossie.candidata(completa.nome) is not None:
            self.guardar(completa.receita)
        return completa

    def receita_para_custear(
        self, receita_id: str | None, entrada: ReceitaEntrada | None
    ) -> Receita:
        """A receita de que sai o custo: a mesma que passou pela conferência, nunca outra.

        Pelo `receita_id`, a receita guardada. Digitada, só vale se for igual à
        guardada com o mesmo nome (a receita que ela ditou, ou a de uma página
        já lida, pelo endereço): a receita redigitada com outra quantidade faria
        o custo sair de uma receita que a conferência não viu. A diferença é
        recusada dizendo o que mudou, e o recado é usar o `receita_id`.
        """
        if (receita_id is None or not receita_id.strip()) and entrada is not None:
            if (entrada.url or "").strip():
                lida = self.catalogo.por_url(entrada.url or "")
                if lida is None:
                    raise ErroDeUso(
                        "não li esse endereço; receita da internet vai pelo receita_id que "
                        "buscar_receita_na_web devolve",
                        url=entrada.url,
                    )
                receita_id = lida.slug
            else:
                receita_id = self._id_pelo_nome(entrada.nome)
        if receita_id is None or not receita_id.strip():
            raise ErroDeUso(
                "informe a receita: o receita_id que avaliar_receita devolveu, "
                "ou a receita que ela ditou"
            )
        receita = self.receita_por_id(receita_id)
        if entrada is not None and (mudou := diferencas(receita, entrada.para_dominio())):
            raise ErroDeUso(
                f"a receita que veio agora não é a mesma que passou pela conferência "
                f"(muda {', '.join(mudou)}). Use o receita_id {slug_da_receita(receita)} para "
                "eu calcular a receita conferida; se ela mudou a receita, chame "
                "avaliar_receita com a receita nova antes",
                receita_id=slug_da_receita(receita),
            )
        return receita

    def _id_pelo_nome(self, nome: str) -> str:
        """O id da receita com este nome, em avaliação ou no catálogo; pede a conferência antes."""
        em_avaliacao = self.dossie.candidata(nome)
        if em_avaliacao is not None:
            return slug_da_receita(em_avaliacao)
        guardada = self.catalogo.por_nome(nome)
        if guardada is not None:
            return guardada.slug
        raise ErroDeUso(
            f"a receita {nome!r} ainda não passou pela conferência; chame avaliar_receita "
            "com ela antes",
            receita=nome,
        )

    def prato_pedido(self, receita_id: str | None, prato: str | None) -> str:
        """O prato de uma chamada: o da receita do `receita_id`, ou o nome que veio.

        O id vale mais que o nome, que pode vir redigitado ("arroz com FRANGO").
        """
        if receita_id is not None and receita_id.strip():
            return self.candidata_por_id(receita_id).nome
        if prato is not None and prato.strip():
            return prato
        raise ErroDeUso("informe o prato: o receita_id da receita avaliada, ou o nome dela")

    def nome_canonico(self, ingrediente: str) -> str:
        """O nome do item da despensa quando o casamento é confiável; senão o dito.

        "alcatra" vira "Miolo de alcatra". Sem isso, a cotação ou a compra ficava
        guardada com um nome que a avaliação do prato nunca encontra.
        """
        casamento = casar(ingrediente, self.despensa)
        if casamento.confiavel and casamento.item is not None:
            return casamento.item.nome
        return ingrediente.strip()

    def custo_conferido(self, prato: str, informado: float | None = None) -> Dinheiro:
        """O custo por porção que o preço usa, recalculado do prato avaliado.

        Recusa prato que o portão não liberou (a mesma recusa de `calcular_cmv`)
        e recusa um custo informado que não bate com o calculado: preço sobre
        número que o motor não produziu é o erro que o §2.4 existe para evitar.
        """
        custo = self.cmv_conferido(prato).para_precificar
        if informado is not None and abs(Decimal(str(informado)) - custo.valor) > Decimal("0.005"):
            raise ErroDeUso(
                "o custo informado não é o que a conta dá para este prato",
                informado=f"{informado:.2f}",
                calculado=str(custo),
            )
        return custo

    def cmv_conferido(self, prato: str) -> CMV:
        """O custo do prato avaliado, recalculado e passado pelo auditor."""
        receita, avaliacao = self.receita_avaliada(prato)
        cmv = calcular(receita, avaliacao)
        self.auditar(prato_para_auditoria(cmv))
        return cmv

    def decidir(
        self,
        prato: str,
        decisao: str,
        motivo: str = "",
        preco: float | None = None,
        *,
        chave: str | None = None,
        desfaz: int | None = None,
        canal: Canal | None = None,
    ) -> tuple[RegistroDecisao, dict[str, Any]]:
        """A decisão dela, com o preço e o lucro quando é um aceite.

        Aceitar exige o prato aprovado no portão e o preço escolhido. Abaixo do
        mínimo sem prejuízo a decisão ainda é dela, e os detalhes dizem quanto
        ela perde. Recusar e adiar valem sempre.

        O prato é gravado com o nome da receita avaliada ("arroz com FRANGO" vira
        "Arroz com frango"): o cardápio segue a última decisão de cada prato, e
        duas grafias eram dois pratos, um aceito para sempre.

        `chave` é a de idempotência de quem chamou (o `Idempotency-Key` da tela,
        o `id_cliente` de um botão da conversa): a mesma chave não grava duas
        vezes. Sem ela, só a repetição da decisão que vale hoje é ignorada.
        `desfaz` diz qual decisão anterior esta desfaz. `canal`, quando vem,
        vale mais que o da sessão.
        """
        try:
            escolha = Decisao(decisao.strip().lower())
        except ValueError as exc:
            raise ErroDeUso(
                "decisao deve ser 'aceito', 'recusado' ou 'adiado'", recebido=decisao
            ) from exc

        avaliada = self.dossie.candidata(prato)
        nome = avaliada.nome if avaliada is not None else prato.strip()
        detalhes: dict[str, Any] = {}
        if escolha is Decisao.ACEITO:
            if preco is None:
                raise ErroDeUso("para aceitar, informe o preço que ela escolheu", prato=prato)
            self.exigir_cozinha_confirmada(prato, Acao.ACEITAR)
            composicao = self.cmv_conferido(prato)
            cmv = composicao.para_precificar
            cobrado = Dinheiro.de(preco)
            lucro = lucro_em(cobrado, cmv)
            parecer = self.auditar(prato_para_auditoria(composicao, cobrado, lucro))
            da_prejuizo = lucro.valor < 0
            _conferir_prejuizo(prato, da_prejuizo, parecer)
            minimo = montar_cenarios(cmv).preco_minimo
            detalhes = {
                "preco": str(cobrado),
                "cmv_por_porcao": str(cmv),
                "lucro_por_porcao": str(lucro.arredondado()),
                "preco_minimo": str(minimo),
                "da_prejuizo": da_prejuizo,
                **({"aviso": _aviso_de_prejuizo(cobrado, lucro, minimo)} if da_prejuizo else {}),
                "taxa_ifood": str((cobrado * TAXA_PLATAFORMA).arredondado()),
                "ela_recebe": str((cobrado * RETENCAO).arredondado()),
                "auditoria_independente": parecer,
            }
        registro = self.dossie.registrar_decisao(
            nome,
            escolha,
            motivo,
            detalhes,
            # Prefixada: a chave de quem chama nunca colide com as que o dossiê gera.
            chave=f"cliente:{chave}" if chave else None,
            canal=canal or self.canal,
            desfaz=desfaz,
        )
        return registro, detalhes

    def comprar(
        self,
        prato: str,
        ingrediente: str,
        quantidade: float,
        unidade: str,
        valor: float,
        *,
        chave: str | None = None,
        canal: Canal | None = None,
    ) -> dict[str, Any]:
        """Registra uma compra pelo portão: prato confirmado e item que ele precisa.

        `chave` é a de idempotência de quem chamou: a mesma chave não desconta
        duas vezes, e chave nova é compra nova, mesmo igual à anterior. Sem ela,
        a mesma compra repetida em poucos minutos é tratada como repetição.

        O reenvio de uma chave que já entrou devolve o estado de agora sem passar
        pelo portão de novo: o item comprado deixou de faltar, e conferir outra
        vez recusaria a compra que ela de fato fez.
        """
        receita, avaliacao = self.receita_avaliada(prato)
        chave_dela = f"cliente:{chave}" if chave else None
        nome = self.nome_canonico(ingrediente)
        if chave_dela is None or not self.dossie.tem_gasto(chave_dela):
            if not avaliacao.pode_comprar:
                raise ErroDeUso(
                    f"{receita.nome} ainda não está confirmado; comprar agora arrisca "
                    "comprar ingrediente para um prato que ela não consegue fazer",
                    falta_confirmar="; ".join(p.texto for p in avaliacao.perguntas) or "-",
                )
            exigir_cozinha_confirmada(
                receita, self.perfil, Acao.COMPRAR, receita_id=slug_da_receita(receita)
            )
            faltam = {f.nome.casefold(): f.nome for f in avaliacao.faltantes}
            if nome.casefold() not in faltam:
                raise ErroDeUso(
                    f"{nome} não está entre o que {receita.nome} precisa comprar",
                    faltam=", ".join(faltam.values()) or "nada",
                )
            nome = faltam[nome.casefold()]
        estado = self.dossie.registrar_compra(
            nome,
            Decimal(str(quantidade)),
            unidade,
            Dinheiro.de(valor),
            chave=chave_dela,
            canal=canal or self.canal,
        )
        depois = self.avaliar(receita)
        self.atualizar_planilha_txt()
        return {
            "registrado": True,
            "orcamento": str(estado),
            "orcamento_restante": estado.restante,
            "prato": receita.nome,
            "veredito_agora": depois.veredito.rotulo,
            "ainda_falta": [f.nome for f in depois.faltantes],
        }

    def cotar(
        self,
        ingrediente: str,
        valor: float,
        quantidade: float | None = None,
        unidade: str = "",
        origem: str = "informado_por_ela",
    ) -> tuple[PrecoMercado, list[str]]:
        """Guarda a cotação com o nome da despensa. Devolve o que ainda falta nos pratos."""
        try:
            de_onde = OrigemPreco(origem)
        except ValueError:
            validas = ", ".join(o.value for o in OrigemPreco)
            raise ErroDeUso(f"origem desconhecida: {origem}", validas=validas) from None
        nome = self.nome_canonico(ingrediente)
        preco = self.dossie.registrar_preco(
            nome,
            Dinheiro.de(valor),
            de_onde,
            Decimal(str(quantidade)) if quantidade is not None else None,
            unidade,
        )
        faltando = {
            f.nome
            for r in self.candidatas.values()
            for f in self.avaliar(r).faltantes
            if not f.custo_conhecido or f.nome.casefold() == nome.casefold()
        }
        return preco, sorted(faltando)

    def responder(self, tipo: str, campo: str, resposta: str) -> dict[str, Any]:
        """Grava a resposta dela a uma pergunta do portão. Ver `registrar_resposta`.

        A mudança na cozinha vai para o histórico (`perfil_eventos`) com o canal
        desta sessão, e a resposta traz o impacto nas receitas em avaliação.
        """
        tipo = tipo.strip().lower()
        if tipo == "cozinha":
            return self._confirmar_pela_conversa(campo, resposta)
        if campo in CAMPOS_DA_RECEITA:
            raise ErroDeUso(
                f"{campo} faz parte da receita: chame avaliar_receita com o receita_id e, na "
                f"receita, só {campo} preenchido com o que ela respondeu",
                campo=campo,
            )
        if tipo in ("equipamento", "tecnica"):
            mudanca = perfil_historico.mudar_item(
                self.dossie,
                perfil_historico.TipoDeItem(tipo),
                campo,
                _posse_ou_nao_sei(resposta),
                self.canal,
            )
        elif tipo == "operacional":
            if campo not in PERGUNTAS_OPERACIONAIS:
                raise ErroDeUso(f"restrição operacional {campo!r} desconhecida", campo=campo)
            # A mesma faixa da tela: "80 bocas" digitado ou dito errado não bloqueia receita.
            valor = _restricao(campo, resposta)
            mudanca = perfil_historico.mudar_restricao(self.dossie, campo, valor, self.canal)
        elif tipo == "gosto":
            opiniao = self.dossie.registrar_gosto(campo, _gosto(resposta))
            return {"registrado": str(opiniao)}
        elif tipo == "ingrediente":
            # "Quanto custa", "quanto pesa a embalagem" e "quanto dá em gramas"
            # chegam todos como ingrediente; gravar qualquer resposta como preço
            # transformaria um peso em cotação.
            raise ErroDeUso(
                "resposta de ingrediente não é gravada aqui",
                preco="registrar_preco_mercado(ingrediente, valor, quantidade, unidade)",
                peso_da_linha=(
                    "avaliar_receita(receita_id, receita={nome, ingredientes: [{texto: <a "
                    "linha>, nome, peso: '300 g', por_unidade: true}]})"
                ),
                embalagem_da_despensa=(
                    "atualizar_despensa(acao='informar_embalagem', ingrediente, "
                    "conteudo_da_embalagem)"
                ),
                preco_pago_da_despensa=(
                    "atualizar_despensa(acao='corrigir', ingrediente, preco_pago, "
                    "quantidade_comprada)"
                ),
            )
        else:
            raise ErroDeUso(
                "tipo deve ser equipamento, tecnica, operacional, gosto ou cozinha", tipo=tipo
            )

        return {
            "registrado": True,
            "nao_sei": mudanca.nao_sei,
            "perfil": mudanca.depois.resumo(),
            "impacto": perfil_historico.impacto_nas_receitas(self, mudanca).para_json(),
        }

    def exigir_cozinha_confirmada(self, prato: str, acao: Acao) -> None:
        """Recusa o aceite enquanto a receita se apoiar no que toda cozinha tem e ela não confirmou.

        Só depois de o portão liberar: prato que ainda não dá recusa pelo motivo
        dele, e a confirmação da cozinha é a última pergunta, não a primeira.
        """
        receita, avaliacao = self.receita_avaliada(prato)
        if avaliacao.permite_precificar:
            exigir_cozinha_confirmada(
                receita, self.perfil, acao, receita_id=slug_da_receita(receita)
            )

    def confirmar_a_cozinha(
        self,
        *,
        receita_id: str | None = None,
        itens: Sequence[tuple[str, str]] | None = None,
        canal: Canal | None = None,
    ) -> tuple[ItemSuposto, ...]:
        """Ela confirma o que toda cozinha tem; devolve o que foi confirmado.

        - `itens`: estes, um a um (`[(tipo, id)]`), como o "Tenho" de cada item;
        - `receita_id`: o que esta receita usa do suposto, a pergunta do aceite;
        - nenhum dos dois: tudo o que ainda está como suposto ("Tenho tudo isso").

        Cada item vira "tem", dito por ela, com o evento no histórico e o canal
        (`perfil_historico.confirmar_itens`): o mesmo caminho de uma resposta.
        """
        perfil = self.perfil
        if itens is not None:
            confirmar = tuple(_item_a_confirmar(tipo, id_) for tipo, id_ in itens)
        elif receita_id is not None:
            confirmar = pressupostos_da_receita(self._receita_da_confirmacao(receita_id), perfil)
        else:
            confirmar = pressupostos_da_cozinha(perfil)
        perfil_historico.confirmar_itens(
            self.dossie, [(i.tipo, i.id) for i in confirmar], canal or self.canal
        )
        return confirmar

    def _receita_da_confirmacao(self, receita_id: str) -> Receita:
        """A receita pelo id (em avaliação ou no catálogo) ou, na conversa, pelo nome do prato."""
        try:
            return self.receita_por_id(receita_id)
        except Ausente:
            avaliada = self.dossie.candidata(receita_id)
            if avaliada is None:
                raise
            return avaliada

    def _confirmar_pela_conversa(self, campo: str, resposta: str) -> dict[str, Any]:
        """`registrar_resposta(tipo="cozinha")`: o sim dela à pergunta de confirmar a cozinha.

        `campo` é o `receita_id` (ou o nome do prato) do aceite ou da compra, ou
        `toda_cozinha` para tudo o que ainda está como suposto. Só o sim se grava
        assim: o que ela não tem, ou não sabe, vai item por item.
        """
        if not _confirma(resposta):
            raise ErroDeUso(
                "a confirmação da cozinha grava só o sim dela; o que ela não tem, ou não sabe, "
                "vai item por item",
                como="registrar_resposta(tipo='equipamento' ou 'tecnica', campo=<id>, "
                "resposta='nao_tem' ou 'nao_sei')",
            )
        alvo = campo.strip()
        confirmados = self.confirmar_a_cozinha(
            receita_id=None if alvo.lower() == TODA_COZINHA else alvo
        )
        return {
            "registrado": True,
            "confirmados": [i.nome for i in confirmados],
            "texto": texto_da_confirmacao(confirmados),
            "perfil": self.perfil.resumo(),
        }

    def comparar(self) -> dict[str, Any]:
        """As candidatas lado a lado, e o catálogo como na tela. Ver `comparar_candidatas`."""
        from mise import receitas_json  # noqa: PLC0415

        comparacao = []
        for receita in self.candidatas.values():
            avaliacao = self.avaliar(receita)
            quantificados = receita.ingredientes_quantificados
            faltam = {f.nome for f in avaliacao.faltantes if not f.parcial}
            do_estoque = sum((u.custo for u in avaliacao.usos if not u.rotulo), Dinheiro.zero())
            compra = avaliacao.custo_das_compras
            comparacao.append(
                {
                    "receita_id": slug_da_receita(receita),
                    "prato": receita.nome,
                    "fonte": receita.citacao,
                    "veredito": avaliacao.veredito.rotulo,
                    "ingredientes_que_ela_tem": len(quantificados) - len(faltam),
                    "ingredientes_da_receita": len(quantificados),
                    "usa_do_estoque_dela": _reais(do_estoque),
                    "compra_para_completar": _reais(compra) if compra is not None else None,
                    "falta_comprar": [f.nome for f in avaliacao.faltantes],
                    "perguntas_em_aberto": [p.texto for p in avaliacao.perguntas],
                }
            )
        comparacao.sort(key=_ordem_de_aproveitamento)
        return {
            "candidatas": comparacao,
            "catalogo": receitas_json.catalogo_para_a_consultora(self),
            "orcamento_restante": _reais(self.dossie.orcamento().restante),
            "orientacao": (
                "Mostre as que mais aproveitam a despensa e pergunte do que ela gosta. "
                "A escolha é dela. Para dizer o que ela consegue fazer, use só o "
                "'catalogo': 'da_para_fazer' é o que dá; 'usa_so_o_que_tem' usa só o "
                "que ela tem e falta ela responder; 'precisa_comprar' pede compra."
            ),
        }

    # -- o preço do que falta: o arquivo e o que o servidor procurou ------- #

    @property
    def precos_na_web(self) -> Any:
        """Os preços que o servidor procurou nos mercados de São Paulo (`mise.precos_na_web`)."""
        if self._precos_na_web is None:
            from mise.precos_na_web import PrecosNaWeb  # noqa: PLC0415

            self._precos_na_web = PrecosNaWeb(self.dossie, self.pesquisador_de_precos)
        return self._precos_na_web

    def referencias(self) -> PrecosDeReferencia:
        """As referências que o motor lê: as do arquivo primeiro, e as procuradas depois."""
        da_web: PrecosDeReferencia = self.precos_na_web.referencias()
        return precos_da_despensa(self.despensa) + da_web

    def buscar_preco_na_web(self, ingrediente: str) -> dict[str, Any]:
        """Procura o preço médio em São Paulo de um ingrediente, guarda e devolve.

        Bloqueante (rede): a porta MCP chama numa thread.
        """
        if not ingrediente.strip():
            raise ErroDeUso("diga qual ingrediente procurar")
        ja_tem = self.referencias().de(ingrediente)
        if ja_tem:
            from mise.precos_na_web import Achado  # noqa: PLC0415

            return Achado(ingrediente.strip(), ja_tem[0]).json()
        resposta: dict[str, Any] = self.precos_na_web.procurar(ingrediente).json()
        return resposta

    def precificar_o_que_falta(self, receita: Receita) -> list[str]:
        """Procura o preço do que falta sem referência, com prazo; devolve o que procurou.

        Só com `pesquisar_precos_ao_guardar`. O que não achou fica sem preço, e
        nada vira pergunta a ela.
        """
        if not self.pesquisar_precos_ao_guardar:
            return []
        from mise.precos_na_web import DIMENSOES, PRAZO_AO_GUARDAR  # noqa: PLC0415

        referencias = self.referencias()
        pedidos: list[tuple[str, tuple[str, ...]]] = []
        for faltante in self.avaliar(receita).faltantes:
            if faltante.custo_conhecido or referencias.de(faltante.nome):
                continue
            medida = faltante.falta
            dimensao = {"kg": "massa", "L": "volume", "un": "contagem"}.get(
                medida.quantidade.dimensao.value if medida is not None else "", ""
            )
            pedidos.append((faltante.nome, (dimensao,) if dimensao else DIMENSOES))
        achados = self.precos_na_web.procurar_varios(pedidos, PRAZO_AO_GUARDAR)
        return [a.ingrediente for a in achados]

    def receita_da_web(
        self,
        url: str,
        fonte: str = "",
        *,
        origem: OrigemNoCatalogo = OrigemNoCatalogo.CONVERSA,
    ) -> dict[str, Any]:
        """Traz a receita de uma página para o catálogo, com a procedência, e devolve o id.

        É a única porta da receita da internet: o servidor busca a página, lê a
        receita estruturada (JSON-LD ou microdata) e guarda no catálogo. Não
        põe a receita em avaliação: a descoberta traz dezenas, e o agente só
        pergunta sobre as que ela escolheu conversar (`avaliar_receita`).
        Endereço que já está no catálogo não é buscado de novo: volta com
        `ja_conhecida`. `fonte` é ignorada: o site vem da página.

        Bloqueante (rede): a porta MCP chama numa thread; a HTTP roda no pool dela.
        """
        del fonte
        conhecida = self.catalogo.por_url(url) if url.strip() else None
        if conhecida is not None:
            return self._resposta_da_web(conhecida, ja_conhecida=True)

        from retrieval.busca import (  # noqa: PLC0415
            BuscaFalhou,
            ExtracaoFalhou,
            UrlRecusada,
            buscar_receita,
        )

        try:
            achada = buscar_receita(url)
        except UrlRecusada as erro:
            raise ErroDeUso(f"não busco esse endereço: {erro}", url=url) from erro
        except BuscaFalhou as erro:
            raise ErroDeDados(
                f"não consegui trazer a página: {erro}",
                pergunta="Quer tentar outro site, ou a senhora me dita a receita?",
                url=url,
            ) from erro
        except ExtracaoFalhou as erro:
            raise ErroDeDados(
                f"a página abriu, mas não traz a receita em formato estruturado: {erro}",
                pergunta="Esse site não publica a receita de um jeito que eu leia. Tenta outro?",
                url=url,
            ) from erro

        return self._resposta_da_web(self.catalogar(achada, origem), ja_conhecida=False)

    def catalogar(self, achada: ReceitaExtraida, origem: OrigemNoCatalogo) -> ReceitaDoCatalogo:
        """Guarda no catálogo o que o servidor leu de uma página, com a procedência dela.

        O site que vira a fonte da receita é o que a página diz de si (ou o
        domínio), nunca o que quem pediu a busca disse.
        """
        from retrieval.quantidades import VERSAO_DA_LEITURA  # noqa: PLC0415

        pagina = PaginaLida(
            receita=replace(achada.receita, fonte=achada.site or achada.fonte),
            site=achada.site,
            autor=achada.autor,
            imagem_url=achada.imagem_url,
            tempos=TemposDaReceita(achada.preparo_min, achada.cozimento_min, achada.total_min),
            rendimento_texto=achada.rendimento_texto,
            hash_do_conteudo=achada.hash_do_conteudo,
            versao_da_leitura=VERSAO_DA_LEITURA,
        )
        guardada, _ = self.catalogo.guardar_da_web(pagina, origem)
        self.precificar_o_que_falta(guardada.receita)
        return guardada

    def _resposta_da_web(
        self, guardada: ReceitaDoCatalogo, *, ja_conhecida: bool
    ) -> dict[str, Any]:
        receita = guardada.receita
        return {
            "receita_id": guardada.slug,
            "ja_conhecida": ja_conhecida,
            "receita": _receita_json(receita),
            "procedencia": {
                "url": receita.url,
                "fonte": guardada.site,
                "autor": guardada.autor,
                "citacao": receita.citacao,
            },
            "observacao": (
                "cite a fonte ao apresentar e pergunte se ela gosta de fazer; para conferir "
                "se ela consegue, chame avaliar_receita com este receita_id"
            ),
        }

    def receita_avaliada(self, prato: str) -> tuple[Receita, Avaliacao]:
        """A receita já avaliada e o parecer de agora. Erro de uso se nunca foi avaliada.

        É por aqui que as ferramentas de dinheiro e de decisão passam pelo portão:
        elas recebem o nome do prato, não um número, e o motor confere.
        """
        receita = self.dossie.candidata(prato)
        if receita is None:
            raise ErroDeUso(
                f"o prato {prato!r} ainda não foi avaliado; chame avaliar_receita com a receita",
                avaliados=", ".join(sorted(self.candidatas)) or "nenhum",
            )
        return receita, self.avaliar(receita)

    @property
    def perfil(self) -> PerfilCozinha:
        return self.dossie.carregar_perfil()

    def registrar_avaliacao(
        self,
        receita_id: str,
        *,
        gosta: bool | None = None,
        muda_o_gosto: bool = False,
        estrelas: Mapping[str, object] | None = None,
        notas: str | None = None,
    ) -> dict[str, Any]:
        """Grava o que ela achou de uma receita e devolve a avaliação com a posição no ranking.

        Só muda o que veio: o gosto quando `muda_o_gosto` (com `gosta` `None`
        voltando a "ainda não disse"), as estrelas que vieram (`None` apaga a
        estrela) e as notas, se vieram. O gosto é gravado na tabela `gostos`,
        a mesma que a conferência lê, pelo nome do prato. O impedimento que ela
        tinha apontado continua quando ela diz que não gosta ou volta a "não
        disse"; quando ela diz que gosta de novo ("Mudei de ideia"), ele deixa
        de valer, e a resposta diz isso. Tudo é conferido antes de gravar
        qualquer coisa: estrela fora de 1 a 5 não deixa o gosto gravado pela metade.
        """
        from mise import receitas_json  # noqa: PLC0415
        from mise.avaliacoes import TAMANHO_DAS_NOTAS, conferir_estrelas  # noqa: PLC0415

        guardada = receitas_json.guardada_por_slug(self, receita_id)
        conferidas = conferir_estrelas(estrelas or {})
        if notas is not None and len(notas) > TAMANHO_DAS_NOTAS:
            raise ErroDeUso(f"as notas cabem em até {TAMANHO_DAS_NOTAS} letras")
        retirado = ""
        if muda_o_gosto:
            atual = self.dossie.gosto_por(guardada.nome)
            opiniao = {True: Gosto.GOSTA, False: Gosto.NAO_GOSTA, None: Gosto.DESCONHECIDO}[gosta]
            impedimento = atual.impedimento if atual is not None else ""
            if gosta is True and impedimento.strip():
                retirado, impedimento = impedimento, ""
            self.dossie.registrar_gosto(guardada.nome, opiniao, impedimento)
        if conferidas or notas is not None:
            self.avaliacoes.gravar(guardada.slug, estrelas=conferidas, notas=notas)
        return receitas_json.resposta_da_avaliacao(
            self, guardada.slug, anotou=True, impedimento_retirado=retirado
        )

    def avaliador(self) -> Callable[[Receita], Avaliacao]:
        """A conferência de muitas receitas com o estado de agora lido uma vez só.

        É o caminho da grade: a cozinha, a despensa, o orçamento, as cotações,
        as compras e os gostos são lidos uma vez, e cada receita passa pelo
        mesmo portão de `avaliar`. Nada é gravado: ler a grade não põe receita
        nenhuma em avaliação.
        """
        perfil = self.perfil
        despensa = self.despensa
        restante = self.dossie.orcamento().restante
        precos = self.dossie.precos_conhecidos()
        compras = self.dossie.compras()
        referencias = self.referencias()
        porcao_g = self.porcao_g()
        opinioes = {chave_do_nome(o.prato): o for o in self.dossie.gostos()}

        def avaliar_uma(receita: Receita) -> Avaliacao:
            opiniao = opinioes.get(chave_do_nome(receita.nome))
            return avaliar(
                receita,
                perfil,
                despensa,
                orcamento_restante=restante,
                precos=precos,
                compras=compras,
                gosto=opiniao.gosto if opiniao else Gosto.DESCONHECIDO,
                impedimento_dela=opiniao.impedimento if opiniao else "",
                referencias=referencias,
                porcao_g=porcao_g,
            )

        return avaliar_uma

    def porcao_g(self) -> Decimal:
        """O peso de uma porção (`porcao_padrao_g`): o dela, ou a premissa da plataforma.

        Só estima o rendimento da receita que não diz quantas porções rende.
        """
        from mise import parametros  # noqa: PLC0415

        valor = parametros.ler(self.dossie)["porcao_padrao_g"].valor
        return valor if valor is not None else PORCAO_PADRAO_G

    @property
    def avaliacoes(self) -> Avaliacoes:
        """As estrelas e as notas dela sobre as receitas (`mise.avaliacoes`)."""
        if self._avaliacoes is None:
            self._avaliacoes = Avaliacoes(self.dossie)
        return self._avaliacoes

    def avaliar(self, receita: Receita, *, perfil: PerfilCozinha | None = None) -> Avaliacao:
        """O parecer do portão com o estado da sessão. `perfil` troca só a cozinha.

        Com `perfil`, a mesma avaliação sobre outra cozinha: é como se compara o
        antes e o depois de uma resposta dela, com o mesmo orçamento, as mesmas
        compras e o mesmo gosto.
        """
        opiniao = self.dossie.gosto_por(receita.nome)
        despensa = self.despensa
        return avaliar(
            receita,
            self.perfil if perfil is None else perfil,
            despensa,
            orcamento_restante=self.dossie.orcamento().restante,
            precos=self.dossie.precos_conhecidos(),
            compras=self.dossie.compras(),
            gosto=opiniao.gosto if opiniao else Gosto.DESCONHECIDO,
            impedimento_dela=opiniao.impedimento if opiniao else "",
            referencias=self.referencias(),
            porcao_g=self.porcao_g(),
        )


def _recado(anotados: list[str]) -> str | None:
    """O que ficou anotado na receita, para quem chamou; `None` quando nada mudou."""
    if not anotados:
        return None
    return f"anotei na receita o que ela respondeu ({'; '.join(anotados)})"


def _com_os_pesos(nova: Receita, guardada: Receita) -> Receita:
    """A receita ditada de novo, com o que ela já disse de cada linha que não mudou.

    Ditar de novo troca a receita inteira; a linha com o mesmo texto e a mesma
    quantidade continua pesando o que ela disse, e continua sendo (ou não) o
    item da despensa que ela confirmou ("É o seu miolo de alcatra?"), em vez de
    a pergunta voltar. É o que a tela de pôr preço faz a cada conferência: manda
    a receita escrita de novo, sem o que ela respondeu ali mesmo.
    """

    def chave(linha: IngredienteReceita) -> tuple[str, Decimal | None, str]:
        return chave_do_nome(linha.texto_original), linha.quantidade, chave_do_nome(linha.medida)

    ditas = {chave(i): i for i in guardada.ingredientes}

    def com_o_dito(linha: IngredienteReceita) -> IngredienteReceita:
        antes = ditas.get(chave(linha))
        if antes is None:
            return linha
        if linha.peso_g is None and antes.peso_g is not None:
            linha = replace(linha, peso_g=antes.peso_g)
        if linha.item_da_despensa is None and antes.item_da_despensa is not None:
            linha = replace(linha, item_da_despensa=antes.item_da_despensa)
        return linha

    return replace(nova, ingredientes=tuple(com_o_dito(i) for i in nova.ingredientes))


def _conferir_prejuizo(prato: str, da_prejuizo: bool, parecer: dict[str, Any] | None) -> None:
    """O auditor e o motor têm de concordar se o preço dá prejuízo.

    Abaixo do mínimo é escolha dela e não segura o aceite. Mas se as duas contas
    independentes discordam sobre ela perder dinheiro, uma delas está errada, e
    é o tipo de erro que o auditor existe para pegar: um centavo de prejuízo
    escondido pelo arredondamento.
    """
    do_auditor = parecer.get("da_prejuizo") if parecer else None
    if do_auditor is not None and bool(do_auditor) != da_prejuizo:
        motivo = (
            "o motor e o auditor discordam se este preço dá prejuízo "
            f"(motor: {'sim' if da_prejuizo else 'não'}; auditor: {'sim' if do_auditor else 'não'})"
        )
        raise ContaNaoConfere(prato, {**(parecer or {}), "divergencias": [motivo]})


def _aviso_de_prejuizo(cobrado: Dinheiro, lucro: Dinheiro, minimo: Dinheiro) -> str:
    """O que ela perde a esse preço, e o mínimo, no jeito como o agente fala com ela."""
    perda = (-lucro).arredondado()
    quanto = f"perde {perda}" if perda.valor > 0 else "perde menos de um centavo"
    return (
        f"A {cobrado}, a senhora {quanto} em cada porção vendida: depois da taxa de "
        f"{TAXA_PLATAFORMA:.0%}, chega menos do que o ingrediente custa. Para não ter "
        f"prejuízo, o mínimo é {minimo}. A decisão é da senhora."
    )


def abrir_sessao(planilha: str | Path | None = None, banco: str | Path | None = None) -> Sessao:
    """Carrega a despensa e abre o dossiê, honrando as variáveis de ambiente.

    A planilha em texto vai para `MISE_DESPENSA_TXT`, ou para `despensa.txt` ao
    lado do dossiê (`.estado/despensa.txt`), e é gravada já na abertura.
    """
    caminho_planilha = Path(
        planilha or os.environ.get("MISE_PLANILHA", "dados/despensa_dona_maria.xlsx")
    )
    caminho_banco = Path(banco or os.environ.get("MISE_DOSSIE", "~/.mise/dossie.db")).expanduser()
    caminho_txt = os.environ.get("MISE_DESPENSA_TXT")
    sessao = Sessao(
        planilha=carregar_despensa(caminho_planilha),
        dossie=Dossie(caminho_banco),
        arquivo_txt=(
            Path(caminho_txt).expanduser() if caminho_txt else caminho_banco.parent / "despensa.txt"
        ),
    )
    # Num clone novo, o catálogo começa com as receitas já lidas (`MISE_CATALOGO_INICIAL`).
    if semente := os.environ.get("MISE_CATALOGO_INICIAL"):
        semear_o_catalogo(sessao.dossie, Path(semente).expanduser())
    reler_o_catalogo(sessao.dossie)
    sessao.atualizar_planilha_txt()
    return sessao


def reler_o_catalogo(dossie: Dossie) -> tuple[LinhaRelida, ...]:
    """As receitas guardadas com regras de leitura mais antigas, lidas de novo pelas linhas.

    Roda na abertura do servidor (o do agente e o da tela abrem a sessão por
    aqui): quando a leitura das linhas melhora, a receita que já estava no
    catálogo acompanha, sem buscar a página de novo e sem mexer no que ela
    respondeu (`mise.catalogo.reler_as_linhas`). Cada linha que mudou vai para
    o log, com o antes e o depois.
    """
    from retrieval.quantidades import VERSAO_DA_LEITURA, interpretar_linha  # noqa: PLC0415

    relidas = reler_as_linhas(dossie, interpretar_linha, VERSAO_DA_LEITURA)
    for relida in relidas:
        logger.info(
            "linha relida em %s (%s): %r de %s para %s",
            relida.receita,
            relida.onde,
            relida.texto_original,
            relida.antes,
            relida.depois,
        )
    return relidas


# --------------------------------------------------------------------------- #
# Leitura das respostas dela
# --------------------------------------------------------------------------- #


_SIM: Final = frozenset({"tem", "sim", "s", "true", "tenho", "possui", "yes"})
_NAO: Final = frozenset({"nao_tem", "nao tem", "nao", "n", "false", "nao tenho", "no"})
#: "Não sei" é resposta, e não é "não tem": apaga a resposta anterior (ver
#: `PerfilCozinha.sem_resposta`). Só as formas claras; "talvez" e "mais ou menos"
#: continuam recusados, para o agente perguntar de outro jeito.
_NAO_SEI: Final = frozenset(
    {
        "nao sei",
        "nao sei nao",
        "sei nao",
        "sei la",
        "nao lembro",
        "nao tenho certeza",
        "nao sei dizer",
        "desconhecido",
    }
)


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto.strip().lower())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _sim_ou_nao(resposta: str) -> bool:
    chave = _sem_acento(resposta).replace("-", " ").strip(" .!")
    if chave in _SIM:
        return True
    if chave in _NAO:
        return False
    raise ErroDeUso(
        f"não entendi {resposta!r} como sim ou não; pergunte de novo a ela",
        validas="tem, nao_tem, sim, não",
    )


def _nao_sei(resposta: str) -> bool:
    """Ela disse que não sabe: "não sei", "nao_sei", "sei lá"."""
    chave = _sem_acento(resposta).replace("_", " ").replace("-", " ").strip(" .!")
    return " ".join(chave.split()) in _NAO_SEI


#: O sim dela à pergunta de confirmar a cozinha, além do sim de sempre.
_CONFIRMA: Final = frozenset(
    {
        "confirmo",
        "confirma",
        "confirmado",
        "sim confirmo",
        "tenho tudo",
        "tenho tudo isso",
        "tenho sim",
        "sim tenho",
        "sim tenho tudo",
    }
)


def _confirma(resposta: str) -> bool:
    """Ela confirmou o que toda cozinha tem? "Tenho tudo", "confirmo", "sim"; recusa o resto."""
    chave = " ".join(_sem_acento(resposta).replace(",", " ").strip(" .!").split())
    if chave in _CONFIRMA:
        return True
    return not _nao_sei(resposta) and _sim_ou_nao(resposta)


def _posse(resposta: str) -> Posse:
    return Posse.TEM if _sim_ou_nao(resposta) else Posse.NAO_TEM


def _posse_ou_nao_sei(resposta: str) -> Posse | None:
    """Tem, não tem, ou `None` quando ela não sabe."""
    return None if _nao_sei(resposta) else _posse(resposta)


def _item_a_confirmar(tipo: str, id_: str) -> ItemSuposto:
    """Um item que ela confirma pela tela ou pela conversa, conferido no vocabulário."""
    try:
        de_que = perfil_historico.TipoDeItem(tipo.strip().lower())
    except ValueError:
        raise ErroDeUso("só equipamento e técnica se confirmam", tipo=tipo) from None
    if de_que is perfil_historico.TipoDeItem.EQUIPAMENTO:
        return ItemSuposto(de_que, id_, equipamento(id_).nome)
    if de_que is perfil_historico.TipoDeItem.TECNICA:
        return ItemSuposto(de_que, id_, tecnica(id_).nome)
    raise ErroDeUso("só equipamento e técnica se confirmam", tipo=tipo)


def _gosto(resposta: str) -> Gosto:
    if _nao_sei(resposta):
        return Gosto.DESCONHECIDO
    chave = _sem_acento(resposta).replace("_", " ")
    if chave in ("gosta", "gosto", "sim", "gosta de fazer"):
        return Gosto.GOSTA
    if chave in ("nao gosta", "nao gosto", "nao"):
        return Gosto.NAO_GOSTA
    raise ErroDeUso(
        f"não entendi {resposta!r} como gosta ou não gosta", validas="gosta, nao_gosta, nao_sei"
    )


def _numero(campo: str, resposta: str) -> float:
    try:
        valor = float(resposta.strip().replace("R$", "").replace(",", ".").strip())
    except ValueError:
        raise ErroDeUso(f"{campo} precisa de um número, e veio {resposta!r}", campo=campo) from None
    if not math.isfinite(valor):
        raise ErroDeUso(f"{campo} precisa de um número, e veio {resposta!r}", campo=campo)
    if valor < 0:
        raise ErroDeUso(f"{campo} não pode ser negativo", campo=campo)
    return valor


def _restricao(campo: str, resposta: str) -> int | bool | None:
    """No tipo guardado, conferido na faixa da tela; `None` se ela não sabe.

    Sim ou não para o gás; o tempo por cozinhada dito em horas ("2 horas",
    "1,5 hora", "1h30"; um número sozinho é em horas, como a pergunta pede) vira
    minutos; o resto é um número.
    """
    if _nao_sei(resposta):
        return None
    formato = FORMATOS_OPERACIONAIS[campo]
    if formato.tipo is TipoDeCampo.SIM_NAO:
        return formato.conferir(_sim_ou_nao(resposta))
    if formato.tipo is TipoDeCampo.HORAS:
        return formato.no_limite(minutos_ditos(resposta))
    return formato.conferir(round(_numero(campo, resposta)))


def _ordem_de_aproveitamento(candidata: dict[str, Any]) -> tuple[bool, int, float]:
    """Viáveis antes, menos compra antes, mais estoque dela usado antes."""
    return (
        candidata["veredito"] == "BLOQUEADO",
        len(candidata["falta_comprar"]),
        -float(candidata["usa_do_estoque_dela"]["valor"]),
    )


# --------------------------------------------------------------------------- #
# Construção do servidor
# --------------------------------------------------------------------------- #


def construir_servidor(sessao: Sessao, middleware: list[Any] | None = None) -> MCPServer:
    """Monta o MCPServer com as ferramentas do motor.

    `middleware` recebe a pilha de política do gateway (autenticação, escopos,
    rate limit, auditoria). Fica de fora deste módulo de propósito: o motor não
    conhece política, e a política não conhece cozinha.

    As ferramentas vêm de `mise.ferramentas`, uma área por módulo, na ordem de
    `REGISTRADORES`. O import é tardio pelo mesmo motivo do `MCPServer`, e porque
    aqueles módulos importam daqui (`Sessao`, `ReceitaEntrada`).
    """
    from mcp.server.mcpserver import MCPServer as _MCPServer  # noqa: PLC0415

    from mise.ferramentas import REGISTRADORES  # noqa: PLC0415

    servidor = _MCPServer(
        name=NOME_SERVIDOR,
        version=__version__,
        instructions=INSTRUCOES,
        middleware=middleware or [],
    )

    for registrar in REGISTRADORES:
        registrar(servidor, sessao)
    return servidor


def main() -> None:
    """Sobe o motor **sem** política, via stdio.

    Útil para desenvolvimento e teste do motor isolado. Em uso real, o ponto de
    entrada é `gateway.principal`, que envolve este servidor na pilha de
    autenticação, escopos, rate limit e auditoria.

    A direção da dependência é deliberada: o gateway conhece o motor, o motor
    não conhece o gateway. Inverter isso amarraria a regra de negócio à política
    de acesso, e as duas mudam por motivos diferentes.
    """
    from mise.precos_na_web import ligada  # noqa: PLC0415

    sessao = abrir_sessao()
    sessao.pesquisar_precos_ao_guardar = ligada()
    construir_servidor(sessao).run(transport="stdio")


__all__ = [
    "INSTRUCOES",
    "NOME_SERVIDOR",
    "IngredienteEntrada",
    "ReceitaEntrada",
    "Sessao",
    "_avaliacao_json",
    "_erro_json",
    "_reais",
    "_receita_json",
    "_resposta",
    "abrir_sessao",
    "construir_servidor",
    "main",
    "prato_para_auditoria",
    "protegido",
    "reler_o_catalogo",
]
