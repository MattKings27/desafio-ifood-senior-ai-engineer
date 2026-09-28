"""As receitas como a tela e o agente leem: a grade, o detalhe, o custo e a avaliação.

As rotas de `/api/receitas` e as ferramentas do agente dizem a mesma coisa
sobre a mesma receita, com as mesmas palavras: por isso as duas montam a
resposta aqui. As formas seguem `contratos/web/receitas.json`, `receita.json`,
`custo.json`, `avaliacao-escrita.json` e `notas-escrita.json`.

**Tudo é calculado na leitura, e nada é gravado por ler.** A grade passa cada
receita do catálogo pela conferência com a despensa, a cozinha, o orçamento e as
compras de agora (`Sessao.avaliador`): a grade se atualiza sozinha quando algo
muda, e abrir a tela não põe receita nenhuma em avaliação (só a conversa põe).

**A grade só mostra o que ela consegue fazer.** A aba de cada receita sai da
conferência sem o gosto (`Avaliacao.veredito_da_cozinha`):

- `pode_fazer`: dá com o que ela tem, ou comprando o que falta dentro do que
  resta dos R$ 80,00;
- `falta_resposta`: falta uma resposta dela, e a pergunta vem junto;
- `nao_quer`: as que ela disse que não gosta de fazer ou em que viu um
  impedimento, para ela poder mudar de ideia;
- `ranking`: as que ela avaliou com estrelas, entre as que dá para fazer.

A que a cozinha dela não permite não aparece em aba nenhuma.

Regras de todo texto daqui: dinheiro sempre como "R$ x,yy", quantidade e data já
escritas, vírgula decimal, "a senhora", e nenhuma palavra interna do sistema.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final

from mise.avaliacoes import CATEGORIAS, EstrelasENotas, Pontuacao, pontuar
from mise.catalogo import (
    OrigemNoCatalogo,
    ReceitaDoCatalogo,
    chave_do_nome,
    id_da_receita,
    url_canonica,
)
from mise.complemento import E_O_ITEM, NAO_E_O_ITEM, PESO_DITO
from mise.compras import Medida
from mise.despensa_json import dinheiro_json, numero_texto, quando_texto, quantidade_texto
from mise.dinheiro import Dinheiro
from mise.erros import Ausente, ErroDeRegra, ErroDeUso, VocabularioDesconhecido
from mise.perfil import Gosto, contagem
from mise.receita import Origem
from mise.serializacao import avisos_json
from mise.taxonomia import equipamento, tecnica
from mise.unidades import MEDIDAS_MASSA, Dimensao, Quantidade
from mise.viabilidade import (
    AjusteDoIngrediente,
    AssuntoDaPergunta,
    Avaliacao,
    ItemFaltante,
    Pergunta,
    SituacaoDoIngrediente,
    TipoRestricao,
    Veredito,
    assunto_da,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from mise.mcp_server import Sessao
    from mise.perfil import PerfilCozinha
    from mise.receita import IngredienteReceita, Receita

# --------------------------------------------------------------------------- #
# Abas, ordens e selos
# --------------------------------------------------------------------------- #

ABAS: Final = ("pode_fazer", "falta_resposta", "ranking", "nao_quer")
ORDENS: Final = ("aproveitamento", "pontuacao", "compra", "tempo", "recentes")

#: A ordem de cada aba quando ela não escolhe outra.
ORDEM_DA_ABA: Final[dict[str, str]] = {
    "pode_fazer": "aproveitamento",
    "falta_resposta": "aproveitamento",
    "ranking": "pontuacao",
    "nao_quer": "recentes",
}

COM_O_QUE_TEM: Final = "com_o_que_tem"
COMPRANDO: Final = "comprando"
FALTA_RESPOSTA: Final = "falta_resposta"
NAO_DA: Final = "nao_da"

#: O código da cozinha de cada veredito da conferência sem o gosto.
CODIGO_DA_COZINHA: Final[dict[Veredito, str]] = {
    Veredito.APTO: COM_O_QUE_TEM,
    Veredito.APTO_COM_COMPRA: COMPRANDO,
    Veredito.FALTA_INFO: FALTA_RESPOSTA,
    Veredito.BLOQUEADO: NAO_DA,
}

#: Que tipo de pergunta ela responde primeiro, quando a receita tem várias.
_ORDEM_DAS_PERGUNTAS: Final[dict[TipoRestricao, int]] = {
    TipoRestricao.EQUIPAMENTO: 0,
    TipoRestricao.TECNICA: 1,
    TipoRestricao.OPERACIONAL: 2,
    TipoRestricao.INGREDIENTE: 3,
    TipoRestricao.GOSTO: 4,
}

_POSICOES: Final = (
    "primeiro",
    "segundo",
    "terceiro",
    "quarto",
    "quinto",
    "sexto",
    "sétimo",
    "oitavo",
    "nono",
    "décimo",
)

#: Como as origens do preço do que falta são ditas a ela.
_ORIGEM_DO_PRECO: Final[dict[str, str]] = {
    "informado_por_ela": "informado pela senhora",
    "pesquisado_na_web": "pesquisado na internet",
    "estimado": "estimado",
    "planilha": "pelo preço que a senhora pagou na despensa",
    "referencia": "preço de referência",
}


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _minuscula(texto: str) -> str:
    """ "Milho verde" vira "milho verde"; sigla ("UHT") fica como está."""
    primeira = texto.split(" ", 1)[0]
    if len(primeira) > 1 and primeira.isupper():
        return texto
    return texto[:1].lower() + texto[1:]


def _lista(nomes: Sequence[str]) -> str:
    """ "milho", "milho e coco", "milho, coco e fubá"."""
    if len(nomes) <= 1:
        return "".join(nomes)
    return ", ".join(nomes[:-1]) + " e " + nomes[-1]


def _maiuscula(texto: str) -> str:
    return texto[:1].upper() + texto[1:]


# --------------------------------------------------------------------------- #
# Quantidades escritas
# --------------------------------------------------------------------------- #

#: Como se escreve cada medida contada, no singular e no plural.
_CONTADAS: Final[dict[str, tuple[str, str]]] = {
    "ovo": ("ovo", "ovos"),
    "dente de alho": ("dente de alho", "dentes de alho"),
    "dente": ("dente", "dentes"),
    "cebola": ("cebola", "cebolas"),
    "cebola media": ("cebola média", "cebolas médias"),
    "tomate": ("tomate", "tomates"),
    "tomate medio": ("tomate médio", "tomates médios"),
    "batata": ("batata", "batatas"),
    "batata media": ("batata média", "batatas médias"),
    "cenoura": ("cenoura", "cenouras"),
    "limao": ("limão", "limões"),
    "folha de louro": ("folha de louro", "folhas de louro"),
    "lata": ("lata", "latas"),
    "pacote": ("pacote", "pacotes"),
    "caixa": ("caixa", "caixas"),
    "caixinha": ("caixinha", "caixinhas"),
    "vidro": ("vidro", "vidros"),
    "pote": ("pote", "potes"),
    "sache": ("sachê", "sachês"),
    "tablete": ("tablete", "tabletes"),
    "envelope": ("envelope", "envelopes"),
    "garrafa": ("garrafa", "garrafas"),
    "saquinho": ("saquinho", "saquinhos"),
    "bandeja": ("bandeja", "bandejas"),
    "un": ("unidade", "unidades"),
    "und": ("unidade", "unidades"),
    "unidade": ("unidade", "unidades"),
}

#: Medidas de volume que já são a unidade: "250 ml", "1 L".
_VOLUME_DIRETO: Final = frozenset({"ml", "l", "litro"})

#: Em português o plural começa no dois: "1,5 xícara", "2 xícaras".
_PLURAL_A_PARTIR_DE: Final = Decimal(2)

#: Até aqui a conversão é de volume para volume ("2 colheres de sopa" são 30 ml):
#: acima, passou por densidade ou peso típico, e o número vem com "cerca de".
_CONVERSAO_EXATA: Final = Decimal("0.02")


def quantidade_curta(quantidade: Quantidade) -> str:
    """ "4,59 kg", "408 g", "3,5 g", "970 ml": a quantidade com as casas que fazem sentido."""
    valor = quantidade.valor
    if quantidade.dimensao is Dimensao.CONTAGEM:
        return quantidade_texto(Quantidade(valor.quantize(Decimal("0.01")), quantidade.dimensao))
    if valor < 1:
        pequena = valor * 1000
        casas = Decimal(1) if pequena >= _DEZ else Decimal("0.1")
        return quantidade_texto(Quantidade(pequena.quantize(casas) / 1000, quantidade.dimensao))
    return quantidade_texto(Quantidade(valor.quantize(Decimal("0.01")), quantidade.dimensao))


_DEZ: Final = Decimal(10)


def _medida_escrita(medida: str, quantidade: Decimal) -> str:
    from mise.unidades import _medida_escrita as escrita_culinaria  # noqa: PLC0415

    chave = _sem_acento(medida).lower().strip()
    formas = _CONTADAS.get(chave)
    if formas is not None:
        return formas[1] if quantidade >= _PLURAL_A_PARTIR_DE else formas[0]
    return escrita_culinaria(medida, quantidade)


def na_receita(ingrediente: IngredienteReceita) -> str:
    """Quanto a receita pede, com as palavras da receita: "2 xícaras", "500 g", "1 lata"."""
    quantidade = ingrediente.quantidade
    if quantidade is None:
        return "a gosto" if ingrediente.a_gosto else "não consegui ler quanto"
    numero = numero_texto(quantidade)
    chave = _sem_acento(ingrediente.medida).lower().strip()
    if not chave:
        return f"{numero} {'unidade' if quantidade == 1 else 'unidades'}"
    if chave in MEDIDAS_MASSA or chave in _VOLUME_DIRETO:
        return f"{numero} {'L' if chave in ('l', 'litro') else ingrediente.medida.strip()}"
    return f"{numero} {_medida_escrita(ingrediente.medida, quantidade)}"


def _precisa_texto(ajuste: AjusteDoIngrediente) -> str:
    """ "500 g", "2 xícaras (cerca de 408 g)", "2 colheres de sopa (30 ml)"."""
    if ajuste.situacao is SituacaoDoIngrediente.A_GOSTO:
        # O tempero que a receita não diz quanto vai, decidido a gosto pela conferência.
        return "a gosto"
    escrito = na_receita(ajuste.ingrediente)
    base = ajuste.precisa
    if ajuste.ingrediente.quantidade is None or base is None or base.dimensao is Dimensao.CONTAGEM:
        return escrito
    chave = _sem_acento(ajuste.ingrediente.medida).lower().strip()
    convertido = quantidade_curta(base)
    if chave in MEDIDAS_MASSA or chave in _VOLUME_DIRETO or convertido == escrito:
        return convertido
    aproximado = ajuste.incerteza > _CONVERSAO_EXATA
    return f"{escrito} (cerca de {convertido})" if aproximado else f"{escrito} ({convertido})"


def medida_texto(medida: Medida) -> str:
    """ "1 lata", "200 g", "0,5 L": o que falta, como ela compra."""
    if medida.embalagem:
        return f"{numero_texto(medida.quantidade.valor)} " + _medida_escrita(
            medida.embalagem, medida.quantidade.valor
        )
    return quantidade_curta(medida.quantidade)


def _estoque_texto(quantidade: Quantidade) -> str:
    return "acabou" if quantidade.valor <= 0 else quantidade_curta(quantidade)


def _tem_texto(ajuste: AjusteDoIngrediente) -> str | None:
    """Quanto ela tem: o estoque, e o que ela já comprou para o cardápio."""
    if ajuste.da_torneira:
        return "da torneira"
    partes: list[str] = []
    if ajuste.item is not None:
        estoque = _estoque_texto(ajuste.item.estoque)
        if ajuste.pergunta is not None and ajuste.precisa is None:
            estoque += ", sem saber quanto dá na medida da receita"
        partes.append(estoque)
    if ajuste.comprado is not None:
        comprado = f"{medida_texto(ajuste.comprado.medida)} que a senhora comprou"
        partes.append(f"mais {comprado}" if partes else comprado)
    return " e ".join(partes) if partes else None


def _sobra_texto(ajuste: AjusteDoIngrediente) -> str | None:
    """Quanto sobra do estoque (e do que ela comprou) depois desta receita."""
    if ajuste.situacao not in (SituacaoDoIngrediente.TEM, SituacaoDoIngrediente.TEM_PARTE):
        return None
    if ajuste.precisa is None:
        return None
    sobras: list[Quantidade] = []
    casa = ajuste.item.estoque if ajuste.item is not None else None
    if casa is not None and ajuste.de_casa is not None and casa.dimensao is ajuste.de_casa.dimensao:
        sobras.append(casa - ajuste.de_casa)
    if ajuste.comprado is not None and ajuste.do_comprado is not None:
        comprado = ajuste.comprado.medida.quantidade
        if comprado.dimensao is ajuste.do_comprado.dimensao:
            sobras.append(comprado - ajuste.do_comprado)
    if not sobras:
        return None
    total = sobras[0]
    for sobra in sobras[1:]:
        total = total + sobra if sobra.dimensao is total.dimensao else total
    if total.valor <= 0:
        return "nada"
    embalagem = ajuste.comprado.medida.embalagem if ajuste.comprado is not None else ""
    if embalagem and ajuste.item is None:
        # Só do que ela comprou, em latas ou pacotes: "1 lata", e não "1 unidade".
        return medida_texto(Medida(total, embalagem))
    return quantidade_curta(total)


# --------------------------------------------------------------------------- #
# Os ingredientes, a compra e o que ela respondeu
# --------------------------------------------------------------------------- #


def _compra_json(ajuste: AjusteDoIngrediente, restante: Dinheiro) -> dict[str, Any] | None:
    faltante = ajuste.faltante
    if faltante is None:
        return None
    quanto = medida_texto(ajuste.falta) if ajuste.falta is not None else faltante.quantidade_texto
    if faltante.custo_estimado is None:
        return {"texto": f"{quanto}, preço ainda não informado", "cabe": None}
    de_referencia = " pelo preço de referência" if faltante.referencia is not None else ""
    return {
        "texto": f"{quanto}, {faltante.custo_estimado}{de_referencia}",
        "cabe": faltante.custo_estimado.valor <= restante.valor,
    }


def ingredientes_json(avaliacao: Avaliacao, restante: Dinheiro) -> list[dict[str, Any]]:
    """Cada ingrediente: quanto a receita pede, quanto ela tem, quanto sobra e o que comprar."""
    return [
        {
            "nome": ajuste.item.nome if ajuste.item is not None else ajuste.ingrediente.nome,
            "item_id": ajuste.item.id if ajuste.item is not None else None,
            "precisa": {"texto": _precisa_texto(ajuste)},
            "tem": {"texto": tem} if (tem := _tem_texto(ajuste)) is not None else None,
            "sobra": {"texto": sobra} if (sobra := _sobra_texto(ajuste)) is not None else None,
            "situacao": ajuste.situacao.value,
            "compra": _compra_json(ajuste, restante),
            "medida_de_referencia": medida_de_referencia_json(ajuste),
        }
        for ajuste in avaliacao.ajustes
    ]


def medida_de_referencia_json(ajuste: AjusteDoIngrediente) -> dict[str, Any] | None:
    """A medida da tabela do IBGE que fez a conta desta linha, com a fonte e o jeito de corrigir.

    `pergunta` tem a forma de `receita.json#perguntas[]` (assunto `medida`,
    `entrada` de peso): responder é dizer o peso da cozinha dela, que vale mais.
    """
    referencia = ajuste.medida_de_referencia
    corrigir = ajuste.corrigir_peso
    if referencia is None or corrigir is None:
        return None
    from mise.passos import perguntas_com_opcoes  # noqa: PLC0415

    texto = (
        f"{_maiuscula(corrigir.uma)} pesa cerca de {numero_texto(referencia.gramas)} g, "
        f"pela referência de {referencia.fonte.curto}; a senhora pode corrigir"
    )
    pergunta = Pergunta(
        TipoRestricao.INGREDIENTE,
        ajuste.ingrediente.texto_original or ajuste.ingrediente.nome,
        f"Quanto pesa {corrigir.uma} na sua cozinha? Em gramas, eu refaço a conta.",
        motivo="o peso da sua cozinha vale mais que a média da tabela",
        assunto=AssuntoDaPergunta.MEDIDA,
        peso=corrigir,
    )
    return {
        "texto": texto,
        "gramas": float(referencia.gramas),
        "fonte": referencia.fonte.titulo,
        "url": referencia.fonte.url,
        "pergunta": perguntas_com_opcoes([pergunta])[0],
    }


def linhas_nao_entendidas_json(avaliacao: Avaliacao) -> list[dict[str, str]]:
    return [
        {"texto": a.ingrediente.texto_original, "pergunta": a.pergunta.texto}
        for a in avaliacao.ajustes
        if a.situacao is SituacaoDoIngrediente.NAO_ENTENDI and a.pergunta is not None
    ]


def opcionais_json(avaliacao: Avaliacao) -> list[dict[str, str]]:
    return [
        {
            "nome": a.item.nome if a.item is not None else a.ingrediente.nome,
            "texto": a.ingrediente.texto_original,
        }
        for a in avaliacao.ajustes
        if a.ingrediente.opcional
    ]


def _faltante_json(ajuste: AjusteDoIngrediente, restante: Dinheiro) -> dict[str, Any]:
    faltante = ajuste.faltante
    assert faltante is not None
    quanto = medida_texto(ajuste.falta) if ajuste.falta is not None else faltante.quantidade_texto
    derivacao = faltante.derivacao or "falta saber o preço"
    if faltante.premissa:
        derivacao = f"{derivacao} ({faltante.premissa})"
    no_prato = faltante.custo_no_prato
    return {
        "nome": faltante.nome,
        "quantidade_texto": quanto,
        "preco_conhecido": faltante.custo_conhecido,
        "custo_compra": dinheiro_json(faltante.custo_estimado) if faltante.custo_estimado else None,
        "custo_no_prato": dinheiro_json(no_prato) if no_prato is not None else None,
        "derivacao": derivacao,
        "origem_preco": _ORIGEM_DO_PRECO.get(faltante.origem_do_preco)
        if faltante.custo_conhecido
        else None,
        "cabe_no_orcamento": (
            faltante.custo_estimado.valor <= restante.valor
            if faltante.custo_estimado is not None
            else None
        ),
        "referencia": referencia_json(faltante),
    }


def referencia_json(faltante: ItemFaltante) -> dict[str, Any] | None:
    """O preço médio em São Paulo que cotou a compra, com cada mercado; `None` sem ele.

    `fontes` traz cada mercado, com o preço da embalagem, o do quilo (do litro,
    da unidade), o endereço do produto e se entrou na média (`na_media`: a que
    ficou mais de 50% longe da mediana fica de fora). `media_texto` é a conta.
    """
    referencia = faltante.referencia
    if referencia is None:
        return None
    fora = set(referencia.fora_da_media)
    return {
        "ingrediente": faltante.nome,
        "texto": _maiuscula(referencia.texto) + ".",
        "preco_texto": referencia.preco_texto,
        "produto": referencia.produto,
        "site": referencia.site,
        "url": referencia.url,
        "data_texto": referencia.data_texto,
        "titulo": _maiuscula(referencia.titulo),
        "preco_medio_texto": referencia.preco_medio_texto,
        "media_texto": referencia.media_texto,
        "fontes": [
            {
                "site": fonte.site,
                "produto": fonte.produto,
                "preco_texto": fonte.preco_texto,
                "por_unidade_texto": f"{Dinheiro(fonte.por_base)} {referencia.por_base_texto}",
                "url": fonte.url,
                "data_texto": fonte.data_texto,
                "na_media": fonte not in fora,
            }
            for fonte in referencia.fontes
        ],
    }


def falta_comprar_json(avaliacao: Avaliacao, restante: Dinheiro) -> dict[str, Any]:
    """O que falta comprar, quanto custa e se cabe no que resta dos R$ 80,00."""
    com_falta = [a for a in avaliacao.ajustes if a.faltante is not None]
    if not com_falta:
        return {
            "itens": [],
            "custo": dinheiro_json(Dinheiro.zero()),
            "cabe_no_orcamento": True,
            "texto": "nada a comprar",
        }
    total = avaliacao.custo_das_compras
    nomes = _lista([_minuscula(a.faltante.nome) for a in com_falta if a.faltante is not None])
    if total is None:
        sem_preco = [
            _minuscula(a.faltante.nome)
            for a in com_falta
            if a.faltante is not None and not a.faltante.custo_conhecido
        ]
        texto = f"falta comprar {nomes}; falta saber o preço de {_lista(sem_preco)}"
        cabe = None
    else:
        cabe = total.valor <= restante.valor
        onde = f"cabe nos {restante} que restam" if cabe else f"não cabe nos {restante} que restam"
        pela_referencia = [
            _minuscula(a.faltante.nome)
            for a in com_falta
            if a.faltante is not None and a.faltante.referencia is not None
        ]
        if not pela_referencia:
            referencia = ""
        elif len(pela_referencia) == len(com_falta):
            referencia = " (pelo preço de referência)"
        else:
            referencia = f" (com preço de referência para {_lista(pela_referencia)})"
        texto = f"falta comprar {nomes}, {total}{referencia}; {onde}"
    return {
        "itens": [_faltante_json(a, restante) for a in com_falta],
        "custo": dinheiro_json(total) if total is not None else None,
        "cabe_no_orcamento": cabe,
        "texto": texto,
    }


def _usa_texto(avaliacao: Avaliacao) -> str:
    """ "usa 5 de 6 ingredientes que a senhora tem"."""
    contam = [
        a
        for a in avaliacao.ajustes
        if a.situacao not in (SituacaoDoIngrediente.A_GOSTO, SituacaoDoIngrediente.OPCIONAL)
    ]
    if not contam:
        return "só leva o que vai a gosto"
    tem = sum(
        1
        for a in contam
        if a.situacao in (SituacaoDoIngrediente.TEM, SituacaoDoIngrediente.TEM_PARTE)
    )
    palavra = "ingrediente" if len(contam) == 1 else "ingredientes"
    return f"usa {tem} de {len(contam)} {palavra} que a senhora tem"


def _falta_texto(avaliacao: Avaliacao) -> str:
    nomes = [_minuscula(f.nome) for f in avaliacao.faltantes]
    return f"falta comprar {_lista(nomes)}" if nomes else "nada a comprar"


# --------------------------------------------------------------------------- #
# Tempos, fonte e foto
# --------------------------------------------------------------------------- #


def minutos_da_receita(guardada: ReceitaDoCatalogo) -> int | None:
    """O tempo que a receita diz levar, para mostrar e filtrar: o total, se a receita diz.

    É o tempo declarado (`Receita.tempo_declarado_min`), com o tempo no fogo que
    ela mesma disse quando a página não dizia; nunca o que a conferência compara.
    """
    return guardada.receita.tempo_declarado_min


def tempos_json(guardada: ReceitaDoCatalogo) -> dict[str, int | None]:
    """Os tempos da receita e o tempo ativo por cozinhada, sem as esperas."""
    from mise.passos import minutos_ativos  # noqa: PLC0415

    receita = guardada.receita
    return {
        "preparo_min": receita.tempo_preparo_min,
        "cozimento_min": receita.tempo_cozimento_min,
        "total_min": receita.tempo_total_min,
        "ativo_min": minutos_ativos(receita).ativos,
    }


def respostas_json(guardada: ReceitaDoCatalogo, agora: datetime) -> list[dict[str, str]]:
    """O que ela disse sobre a receita e a página não dizia, com quando disse."""
    return [
        {
            "campo": r.campo,
            "texto": _resposta_texto(r.campo, r.valor),
            "quando_texto": quando_texto(r.quando, agora),
        }
        for r in guardada.respostas
    ]


#: O que ela disse sobre a própria receita, pelo campo da pergunta.
_DITO_DA_RECEITA: Final[dict[str, str]] = {
    "rendimento_porcoes": "A senhora disse que rende {valor}.",
    "tempo_cozimento_min": "A senhora disse que fica {valor}.",
    "modo_preparo": "A senhora contou o modo de preparo.",
}


def _resposta_texto(campo: str, valor: str) -> str:
    if campo in _DITO_DA_RECEITA:
        return _DITO_DA_RECEITA[campo].format(valor=valor)
    if valor.startswith(E_O_ITEM):
        item = valor.removeprefix(E_O_ITEM)
        return f"A senhora disse que “{campo}” é o que tem na despensa: {_minuscula(item)}."
    if valor == NAO_E_O_ITEM:
        return f"A senhora disse que “{campo}” não é o que tem na despensa: entra na compra."
    if valor.startswith(PESO_DITO):
        # "A senhora disse que um peito de frango pesa 300 g."
        return f"A senhora disse que {valor.removeprefix(PESO_DITO)}."
    return f"A senhora disse quanto vai de “{campo}”: {valor}."


def tempo_texto(minutos: int | None) -> str | None:
    """ "40 min", "1 h", "1 h 30 min"."""
    if minutos is None or minutos <= 0:
        return None
    horas, resto = divmod(minutos, 60)
    if not horas:
        return f"{resto} min"
    return f"{horas} h" if not resto else f"{horas} h {resto} min"


def imagem_json(guardada: ReceitaDoCatalogo) -> dict[str, str] | None:
    rota = guardada.rota_da_imagem
    if rota is None:
        return None
    return {"url": rota, "credito": guardada.credito_da_imagem or "Foto: a página da receita"}


def fonte_json(guardada: ReceitaDoCatalogo) -> dict[str, str | None]:
    """`{site, url, autor}` da página; tudo `None` na receita que ela ditou."""
    if not guardada.da_internet:
        return {"site": None, "url": None, "autor": None}
    return {"site": guardada.site, "url": guardada.url, "autor": guardada.autor}


def rendimento_texto(receita: Receita) -> str | None:
    if not receita.rendimento_informado:
        return None
    return contagem(receita.rendimento_porcoes, "porção", "porções")


def rendimento_json(avaliacao: Avaliacao) -> dict[str, Any] | None:
    """Quantas porções rende, se é estimativa, e o jeito de ela mudar a estimativa.

    `pergunta` tem a forma de `receita.json#perguntas[]` (campo `rendimento_porcoes`,
    `entrada` inteira): não é pergunta pendente, é o campo para ela corrigir a
    estimativa na receita. `null` quando o rendimento é o que a receita (ou ela) disse.
    """
    from mise.passos import perguntas_com_opcoes  # noqa: PLC0415

    rendimento = avaliacao.rendimento
    if rendimento is None:
        return None
    pergunta = None
    if rendimento.estimado:
        forma = Pergunta(
            TipoRestricao.OPERACIONAL,
            "rendimento_porcoes",
            f"Quantas porções a receita de {_minuscula(avaliacao.receita_nome)} rende na sua "
            "cozinha?",
            motivo=rendimento.derivacao,
            assunto=AssuntoDaPergunta.RENDIMENTO,
        )
        pergunta = perguntas_com_opcoes([forma])[0]
    return {
        "porcoes": rendimento.porcoes,
        "estimado": rendimento.estimado,
        "texto": rendimento.texto,
        "derivacao": rendimento.derivacao,
        "pergunta": pergunta,
    }


def rota_da_receita(slug: str) -> str:
    return f"/receitas/{slug}"


# --------------------------------------------------------------------------- #
# A leitura de uma receita: o que a conferência e ela dizem dela
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class LeituraDaReceita:
    """Uma receita do catálogo lida agora: a conferência, o gosto e as estrelas dela."""

    guardada: ReceitaDoCatalogo
    avaliacao: Avaliacao
    estrelas: EstrelasENotas
    #: `True` gosta de fazer, `False` não gosta, `None` ainda não disse.
    gosta: bool | None
    impedimento: str = ""
    #: Quando ela disse se gosta, para a data da avaliação.
    gosto_em: datetime | None = None

    @property
    def slug(self) -> str:
        return self.guardada.slug

    @property
    def nome(self) -> str:
        return self.guardada.nome

    @property
    def codigo(self) -> str:
        """O que a cozinha dela diz, sem o gosto: `com_o_que_tem`, `comprando`..."""
        return CODIGO_DA_COZINHA[self.avaliacao.veredito_da_cozinha]

    @property
    def nao_quer(self) -> bool:
        """Ela disse que não gosta de fazer, ou viu um impedimento."""
        return self.gosta is False or bool(self.impedimento.strip())

    @property
    def aba(self) -> str | None:
        """A aba em que a receita aparece; `None` quando a cozinha dela não permite."""
        if self.codigo == NAO_DA:
            return None
        if self.nao_quer:
            return "nao_quer"
        return "falta_resposta" if self.codigo == FALTA_RESPOSTA else "pode_fazer"

    @property
    def da_para_fazer(self) -> bool:
        return self.codigo in (COM_O_QUE_TEM, COMPRANDO)

    @property
    def pontuacao(self) -> Pontuacao | None:
        return pontuar(self.estrelas.estrelas, self.gosta)

    @property
    def no_ranking(self) -> bool:
        """Entra no ranking: tem estrela e dá para fazer."""
        return self.da_para_fazer and self.estrelas.avaliada

    @property
    def compra(self) -> Dinheiro | None:
        return self.avaliacao.custo_das_compras

    @property
    def minutos(self) -> int | None:
        return minutos_da_receita(self.guardada)

    @property
    def atualizada_em(self) -> datetime | None:
        """A última vez que ela mexeu na avaliação: as estrelas, as notas ou o gosto."""
        datas = [d for d in (self.estrelas.atualizada_em, self.gosto_em) if d is not None]
        return max(datas) if datas else None


def _gosta(gosto: Gosto) -> bool | None:
    if gosto is Gosto.GOSTA:
        return True
    if gosto is Gosto.NAO_GOSTA:
        return False
    return None


def guardadas(sessao: Sessao) -> list[ReceitaDoCatalogo]:
    """As receitas do catálogo e, depois, as em avaliação de antes do catálogo."""
    do_catalogo = list(sessao.catalogo.listar())
    conhecidos = {r.slug for r in do_catalogo}
    for receita in sessao.candidatas.values():
        slug = id_da_receita(receita)
        if slug not in conhecidos:
            do_catalogo.append(de_antes_do_catalogo(receita))
            conhecidos.add(slug)
    return do_catalogo


def de_antes_do_catalogo(receita: Receita) -> ReceitaDoCatalogo:
    """Uma receita em avaliação guardada antes do catálogo existir, na forma do catálogo."""
    da_web = receita.origem is Origem.WEB and bool(receita.url)
    return ReceitaDoCatalogo(
        slug=id_da_receita(receita),
        receita=receita,
        origem=OrigemNoCatalogo.CONVERSA if da_web else OrigemNoCatalogo.DITA,
        url_canonica=url_canonica(receita.url) if da_web and receita.url else None,
        site=receita.fonte if da_web else None,
    )


def guardada_por_slug(sessao: Sessao, slug: str) -> ReceitaDoCatalogo:
    """A receita do catálogo (ou em avaliação, de antes do catálogo) com este id."""
    procurado = slug.strip().lower()
    achada = sessao.catalogo.obter(procurado)
    if achada is not None:
        return achada
    for receita in sessao.candidatas.values():
        if id_da_receita(receita) == procurado:
            return de_antes_do_catalogo(receita)
    raise Ausente("não encontrei essa receita", receita_id=slug)


def ler(sessao: Sessao, receitas: Iterable[ReceitaDoCatalogo]) -> list[LeituraDaReceita]:
    """Cada receita passada pela conferência de agora, sem gravar nada."""
    avaliar = sessao.avaliador()
    estrelas = sessao.avaliacoes.todas()
    opinioes = {chave_do_nome(o.prato): o for o in sessao.dossie.gostos()}
    leituras = []
    for guardada in receitas:
        opiniao = opinioes.get(chave_do_nome(guardada.nome))
        leituras.append(
            LeituraDaReceita(
                guardada=guardada,
                avaliacao=avaliar(guardada.receita),
                estrelas=estrelas.get(guardada.slug) or _vazias(guardada.slug),
                gosta=_gosta(opiniao.gosto) if opiniao else None,
                impedimento=opiniao.impedimento if opiniao else "",
                gosto_em=opiniao.registrado if opiniao else None,
            )
        )
    return leituras


def _vazias(slug: str) -> EstrelasENotas:
    from mise.avaliacoes import sem_estrelas  # noqa: PLC0415

    return sem_estrelas(slug)


def _chave_do_ranking(leitura: LeituraDaReceita) -> tuple[bool, Decimal, Decimal, str]:
    """Não gosta por último; depois a pontuação, a compra menor e o nome."""
    pontuacao = leitura.pontuacao
    compra = leitura.compra
    return (
        leitura.nao_quer,
        -(pontuacao.valor if pontuacao is not None else Decimal(-1)),
        compra.valor if compra is not None else Decimal("Infinity"),
        chave_do_nome(leitura.nome),
    )


def ranking(leituras: Iterable[LeituraDaReceita]) -> list[LeituraDaReceita]:
    """As receitas avaliadas que dá para fazer, na ordem do ranking."""
    return sorted((le for le in leituras if le.no_ranking), key=_chave_do_ranking)


def posicao_no_ranking(leituras: Iterable[LeituraDaReceita], slug: str) -> int | None:
    for posicao, leitura in enumerate(ranking(leituras), start=1):
        if leitura.slug == slug:
            return posicao
    return None


# --------------------------------------------------------------------------- #
# O veredito da cozinha, a pergunta da vez e o selo
# --------------------------------------------------------------------------- #


def _pergunta_da_cozinha(avaliacao: Avaliacao) -> Pergunta | None:
    """A pergunta que ela responde primeiro: equipamento, técnica, rotina, ingrediente."""
    perguntas = avaliacao.perguntas_da_cozinha
    if not perguntas:
        return None
    return min(
        enumerate(perguntas), key=lambda par: (_ORDEM_DAS_PERGUNTAS.get(par[1].tipo, 9), par[0])
    )[1]


def veredito_da_cozinha_json(leitura: LeituraDaReceita, restante: Dinheiro) -> dict[str, str]:
    """`{codigo, rotulo, motivo}`: só a cozinha e a despensa, sem o gosto."""
    avaliacao = leitura.avaliacao
    codigo = leitura.codigo
    if codigo == COM_O_QUE_TEM:
        rotulo = "Com o que a senhora tem"
        motivo = "A senhora tem o que a receita pede, e a cozinha dá conta."
    elif codigo == COMPRANDO:
        rotulo = "Dá, comprando o que falta"
        motivo = _maiuscula(falta_comprar_json(avaliacao, restante)["texto"]) + "."
    elif codigo == FALTA_RESPOSTA:
        rotulo = "Falta uma resposta da senhora"
        motivo = _motivo_da_pergunta(avaliacao)
    else:
        rotulo = "Não dá"
        motivos = "; ".join(str(i) for i in avaliacao.impedimentos_da_cozinha)
        motivo = _maiuscula(motivos) + "." if motivos else "A cozinha da senhora não dá conta."
    return {"codigo": codigo, "rotulo": rotulo, "motivo": motivo}


def _motivo_da_pergunta(avaliacao: Avaliacao) -> str:
    linhas = linhas_nao_entendidas_json(avaliacao)
    if linhas:
        quais = _lista([f"“{linha['texto']}”" for linha in linhas])
        palavra = "uma linha" if len(linhas) == 1 else "linhas"
        return f"Não consegui ler quanto vai em {palavra} dos ingredientes: {quais}."
    pergunta = _pergunta_da_cozinha(avaliacao)
    if pergunta is None:
        return "Falta uma resposta da senhora."
    return _maiuscula(pergunta.motivo) + "." if pergunta.motivo else pergunta.texto


def selo_json(leitura: LeituraDaReceita, restante: Dinheiro) -> dict[str, str]:
    codigo = leitura.codigo
    if codigo == COM_O_QUE_TEM:
        return {"codigo": codigo, "texto": "Com o que a senhora tem"}
    if codigo == COMPRANDO:
        compra = leitura.compra
        if compra is None:
            return {"codigo": codigo, "texto": "Comprando o que falta"}
        return {"codigo": codigo, "texto": f"Comprando {compra}, cabe nos {restante}"}
    return {"codigo": FALTA_RESPOSTA, "texto": "Falta uma resposta da senhora"}


def pontuacao_json(pontuacao: Pontuacao | None, *, com_conta: bool) -> dict[str, Any] | None:
    if pontuacao is None:
        return None
    saida: dict[str, Any] = {"valor": float(pontuacao.valor), "texto": pontuacao.texto}
    if com_conta:
        saida["derivacao"] = pontuacao.derivacao
    return saida


# --------------------------------------------------------------------------- #
# A grade
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Filtros:
    """Os filtros da grade, já conferidos."""

    aba: str = "pode_fazer"
    q: str | None = None
    usa: str | None = None
    tempo_max: int | None = None
    so_com_o_que_tenho: bool = False
    nota_min: Decimal | None = None
    ordem: str | None = None

    def __post_init__(self) -> None:
        if self.aba not in ABAS:
            raise ErroDeUso("essa aba não existe", aba=self.aba, validas=", ".join(ABAS))
        if self.ordem is not None and self.ordem not in ORDENS:
            raise ErroDeUso("essa ordem não existe", ordem=self.ordem, validas=", ".join(ORDENS))

    def aceita(self, leitura: LeituraDaReceita) -> bool:
        if self.q and self.q.strip() and not _casa_a_busca(leitura, self.q):
            return False
        if self.usa and not any(
            a.item is not None and a.item.id == self.usa for a in leitura.avaliacao.ajustes
        ):
            return False
        if self.tempo_max is not None and (
            leitura.minutos is None or leitura.minutos > self.tempo_max
        ):
            return False
        if self.so_com_o_que_tenho and leitura.avaliacao.faltantes:
            return False
        if self.nota_min is not None:
            pontuacao = leitura.pontuacao
            if pontuacao is None or pontuacao.valor < self.nota_min:
                return False
        return True


def _casa_a_busca(leitura: LeituraDaReceita, q: str) -> bool:
    """A busca olha o nome, o site e os ingredientes, sem ligar para caixa e acento."""
    alvo = chave_do_nome(q)
    textos = [leitura.nome, leitura.guardada.site or ""]
    textos += [i.nome for i in leitura.guardada.receita.ingredientes]
    return any(alvo in chave_do_nome(t) for t in textos)


def _na_aba(leitura: LeituraDaReceita, aba: str) -> bool:
    return leitura.no_ranking if aba == "ranking" else leitura.aba == aba


def _ordenar(leituras: list[LeituraDaReceita], ordem: str) -> list[LeituraDaReceita]:
    if ordem == "pontuacao":
        return sorted(leituras, key=_chave_do_ranking)
    if ordem == "compra":
        return sorted(
            leituras,
            key=lambda le: (
                le.compra is None,
                le.compra.valor if le.compra is not None else Decimal(0),
                chave_do_nome(le.nome),
            ),
        )
    if ordem == "tempo":
        return sorted(
            leituras,
            key=lambda le: (le.minutos is None, le.minutos or 0, chave_do_nome(le.nome)),
        )
    if ordem == "recentes":
        return sorted(
            leituras,
            key=lambda le: le.guardada.criada_em.timestamp() if le.guardada.criada_em else 0.0,
            reverse=True,
        )
    return sorted(leituras, key=_chave_do_aproveitamento)


def _chave_do_aproveitamento(leitura: LeituraDaReceita) -> tuple[int, Decimal, str]:
    """As que usam mais do que ela tem primeiro; depois a que pede menos compra, e o nome."""
    usadas = sum(
        1
        for a in leitura.avaliacao.ajustes
        if a.situacao in (SituacaoDoIngrediente.TEM, SituacaoDoIngrediente.TEM_PARTE)
    )
    compra = leitura.compra
    return (
        -usadas,
        compra.valor if compra is not None else Decimal("Infinity"),
        chave_do_nome(leitura.nome),
    )


def item_da_grade(
    sessao: Sessao,
    leitura: LeituraDaReceita,
    restante: Dinheiro,
    *,
    com_pergunta: bool,
    perfil: PerfilCozinha | None = None,
) -> dict[str, Any]:
    """Um card da grade (`receitas.json#itens[]`).

    `perfil` é a cozinha lida uma vez para a grade inteira; sem ele, lê a de agora.
    """
    from mise.certeza import nota_da_grade  # noqa: PLC0415

    guardada = leitura.guardada
    pergunta = None
    if com_pergunta and leitura.codigo == FALTA_RESPOSTA:
        pergunta = pergunta_json(sessao, leitura)
    nota = nota_da_grade(
        guardada.receita, perfil if perfil is not None else sessao.perfil, leitura.avaliacao
    )
    return {
        "slug": guardada.slug,
        "nome": guardada.nome,
        "imagem": imagem_json(guardada),
        "site": guardada.site if guardada.da_internet else None,
        "tempo_texto": tempo_texto(leitura.minutos),
        "selo": selo_json(leitura, restante),
        "usa_texto": _usa_texto(leitura.avaliacao),
        "falta_texto": _falta_texto(leitura.avaliacao),
        "nota_da_cozinha": nota,
        "pontuacao": pontuacao_json(leitura.pontuacao, com_conta=False),
        "gosta": leitura.gosta,
        "pergunta": pergunta,
        "referencias": [
            ref
            for faltante in leitura.avaliacao.faltantes
            if (ref := referencia_json(faltante)) is not None
        ],
        "rota": rota_da_receita(guardada.slug),
    }


def pergunta_json(sessao: Sessao, leitura: LeituraDaReceita) -> dict[str, Any] | None:
    """A pergunta que ela responde ali mesmo, na forma de `receita.json#perguntas[]`."""
    from mise.passos import avaliar_passos, perguntas_com_opcoes  # noqa: PLC0415

    pergunta = _pergunta_da_cozinha(leitura.avaliacao)
    if pergunta is None:
        return None
    passos = avaliar_passos(leitura.guardada.receita, sessao.perfil)
    return perguntas_com_opcoes([pergunta], passos)[0]


def estado_da_descoberta(sessao: Sessao) -> dict[str, Any]:
    """Como anda a busca de receitas por conta própria; parada, até a descoberta existir."""
    encontradas = sessao.catalogo.contar(OrigemNoCatalogo.DESCOBERTA)
    if encontradas:
        texto = (
            f"Trouxe {contagem(encontradas, 'receita', 'receitas')} da internet "
            "que usam a despensa da senhora."
        )
    else:
        texto = (
            "Ainda não procurei receitas na internet por conta própria. A senhora pode "
            "trazer uma pelo endereço, ou me pedir na conversa."
        )
    return {"estado": "parada", "lidas": encontradas, "encontradas": encontradas, "texto": texto}


def lista(sessao: Sessao, filtros: Filtros) -> dict[str, Any]:
    """`GET /api/receitas`: a aba pedida, as contagens de cada aba e a descoberta.

    `perguntas_que_liberam` junta as perguntas das receitas que esperam uma
    resposta dela pelo que perguntam, e diz quantas receitas cada resposta
    mexe: a tela mostra quando nada dá para fazer ainda. `esperando_resposta`
    diz quantas dessas usam só o que ela tem e esperam só o que ela responder,
    para a tela nunca dizer "nada dá" quando a verdade é "ainda não confirmei".
    """
    leituras = [le for le in ler(sessao, guardadas(sessao)) if filtros.aceita(le)]
    restante = sessao.dossie.orcamento().restante
    contagens = {aba: sum(1 for le in leituras if _na_aba(le, aba)) for aba in ABAS}
    da_aba = [le for le in leituras if _na_aba(le, filtros.aba)]
    ordenadas = _ordenar(da_aba, filtros.ordem or ORDEM_DA_ABA[filtros.aba])
    esperando = [le for le in leituras if _na_aba(le, "falta_resposta")]
    perfil = sessao.perfil
    return {
        "aba": filtros.aba,
        "contagens": contagens,
        "itens": [
            item_da_grade(
                sessao, le, restante, com_pergunta=filtros.aba == "falta_resposta", perfil=perfil
            )
            for le in ordenadas
        ],
        "descoberta": estado_da_descoberta(sessao),
        "perguntas_que_liberam": perguntas_que_liberam(esperando),
        "esperando_resposta": esperando_resposta(esperando),
        "sem_preco_na_internet": sem_preco_na_internet(leituras),
    }


def so_falta_o_preco(leitura: LeituraDaReceita) -> bool:
    """A cozinha dela dá conta, e a receita ficou de fora só porque um preço não se achou."""
    from mise.viabilidade import SEM_PRECO  # noqa: PLC0415

    impedimentos = leitura.avaliacao.impedimentos_da_cozinha
    return (
        leitura.codigo == NAO_DA
        and bool(impedimentos)
        and all(i.id == SEM_PRECO for i in impedimentos)
    )


def sem_preco_na_internet(leituras: Sequence[LeituraDaReceita]) -> dict[str, Any] | None:
    """Quantas receitas ficaram de fora só porque um preço não se achou em página de supermercado.

    O preço não se pergunta: sem ele, não dá para confirmar que a compra cabe
    nos R$ 80,00, e a receita não aparece em "Dá para fazer". A tela diz quantas
    ficaram de fora por isso, e quais; `None` quando nenhuma.
    """
    fora = [le for le in leituras if so_falta_o_preco(le)]
    if not fora:
        return None
    quantas = contagem(len(fora), "receita ficou", "receitas ficaram")
    return {
        "receitas": len(fora),
        "nomes": [le.nome for le in fora],
        "slugs": [le.slug for le in fora],
        "texto": (
            f"{quantas} de fora porque não achei em página de supermercado o preço de algum "
            "ingrediente; se a senhora souber o preço, eu confiro de novo."
        ),
    }


# --------------------------------------------------------------------------- #
# As perguntas que liberam receitas                                             #
# --------------------------------------------------------------------------- #

#: Quantas perguntas o painel "Responda e eu libero mais receitas" traz, no máximo.
MAXIMO_DE_PERGUNTAS_QUE_LIBERAM: Final = 5

#: As que valem para a cozinha inteira: a mesma resposta serve a toda receita.
_DA_COZINHA_INTEIRA: Final = frozenset(
    {AssuntoDaPergunta.EQUIPAMENTO, AssuntoDaPergunta.TECNICA, AssuntoDaPergunta.ROTINA}
)
#: As que ela responde ali mesmo, mas que são de uma receita só.
_DE_UMA_RECEITA: Final = frozenset(
    {
        AssuntoDaPergunta.LINHA_NAO_LIDA,
        AssuntoDaPergunta.MESMO_INGREDIENTE,
        AssuntoDaPergunta.RENDIMENTO,
        AssuntoDaPergunta.TEMPO_COZIMENTO,
    }
)
_MOTIVO_DO_PRECO: Final = "sem o preço não dá para saber se cabe no orçamento"


@dataclass(slots=True)
class _GrupoDePerguntas:
    """Uma pergunta e as receitas que esperam por ela."""

    pergunta: dict[str, Any]
    ordem: int
    receitas: list[LeituraDaReceita]


def _chaves_da_pergunta(
    pergunta: Pergunta, leitura: LeituraDaReceita
) -> list[tuple[tuple[str, ...], dict[str, Any] | None]]:
    """O que a pergunta pergunta, como chave, e a forma dela no painel (`None`: fica fora).

    Equipamento, técnica e rotina são da cozinha: a mesma chave em toda receita.
    O preço do que falta vira uma pergunta por ingrediente, pelo produto (o
    núcleo do nome: "cenouras médias" e "cenoura" são a mesma compra). O resto
    é da receita, e a chave leva a receita junto.
    """
    from mise.casamento import nucleo_do_nome  # noqa: PLC0415
    from mise.passos import perguntas_com_opcoes  # noqa: PLC0415

    assunto = assunto_da(pergunta)
    if assunto is AssuntoDaPergunta.PRECO_DE_COMPRA and pergunta.compras:
        chaves: list[tuple[tuple[str, ...], dict[str, Any] | None]] = []
        for falta in pergunta.compras:
            quanto = (
                medida_texto(falta.falta) if falta.falta is not None else falta.quantidade_texto
            )
            produto = nucleo_do_nome(falta.nome) or chave_do_nome(falta.nome)
            chaves.append(
                (
                    (assunto.value, produto),
                    {
                        "tipo": "ingrediente",
                        "assunto": assunto.value,
                        "campo": falta.nome,
                        "texto": (
                            f"Quanto custa {_minuscula(falta.nome)} aí na sua região, e por qual "
                            "quantidade (o quilo, a lata, o pacote)?"
                        ),
                        "motivo": _MOTIVO_DO_PRECO,
                        "compras": [{"ingrediente": falta.nome, "quantidade_texto": quanto}],
                        "opcoes": [],
                        "entrada": {"tipo": "texto"},
                        "passos": [],
                    },
                )
            )
        return chaves
    forma = perguntas_com_opcoes([pergunta])[0]
    if assunto in _DA_COZINHA_INTEIRA:
        return [((assunto.value, pergunta.campo), forma)]
    chave = (assunto.value, leitura.slug, pergunta.campo)
    # O peso de uma linha que ela diz ali mesmo; a medida que um peso não resolve fica de fora.
    responde_ali = assunto in _DE_UMA_RECEITA or pergunta.peso is not None
    return [(chave, forma if responde_ali else None)]


def _contagem_texto(receitas: int, liberadas: int) -> str:
    """ "libera 3 receitas", "ajuda a liberar 2 receitas", "libera 1 receita e ajuda outras 2"."""
    if liberadas == receitas:
        return f"libera {contagem(receitas, 'receita', 'receitas')}"
    if liberadas == 0:
        return f"ajuda a liberar {contagem(receitas, 'receita', 'receitas')}"
    outras = receitas - liberadas
    return (
        f"libera {contagem(liberadas, 'receita', 'receitas')} e ajuda "
        f"{'outra' if outras == 1 else f'outras {outras}'}"
    )


def perguntas_que_liberam(leituras: Sequence[LeituraDaReceita]) -> list[dict[str, Any]]:
    """As perguntas das receitas que esperam uma resposta, juntas pelo que perguntam.

    Cada uma diz quantas receitas esperam por ela (`receitas`) e quantas ela
    libera sozinha (`liberadas`: as que não esperam por mais nada), com os
    nomes e o texto da contagem. Vêm primeiro as que mexem em mais receitas.
    Só entra o que ela responde ali mesmo (inclusive quanto pesa a linha que
    não se converte, "Não sei quanto pesa um peito de frango"); a pergunta que
    só a conversa resolve (o modo de preparo, a medida que um peso não
    resolve) conta como pendência da receita, mas não vem no painel.
    """
    grupos: dict[tuple[str, ...], _GrupoDePerguntas] = {}
    pendencias: dict[str, set[tuple[str, ...]]] = {}
    for leitura in leituras:
        chaves_da_receita: set[tuple[str, ...]] = set()
        for pergunta in leitura.avaliacao.perguntas_da_cozinha:
            for chave, forma in _chaves_da_pergunta(pergunta, leitura):
                chaves_da_receita.add(chave)
                if forma is None:
                    continue
                grupo = grupos.setdefault(
                    chave, _GrupoDePerguntas(forma, _ORDEM_DAS_PERGUNTAS.get(pergunta.tipo, 9), [])
                )
                if leitura not in grupo.receitas:
                    grupo.receitas.append(leitura)
                # O mesmo produto escrito de vários jeitos: pergunta pelo nome mais curto.
                if (len(forma["campo"]), forma["campo"]) < (
                    len(grupo.pergunta["campo"]),
                    grupo.pergunta["campo"],
                ):
                    grupo.pergunta = forma
        pendencias[leitura.slug] = chaves_da_receita

    saida: list[tuple[tuple[int, int, int, str], dict[str, Any]]] = []
    for chave, grupo in grupos.items():
        receitas = len(grupo.receitas)
        liberadas = sum(1 for le in grupo.receitas if pendencias[le.slug] == {chave})
        forma = dict(grupo.pergunta)
        if receitas > 1 and chave[0] != AssuntoDaPergunta.PRECO_DE_COMPRA.value:
            # O porquê de uma receita só não explica as outras: os nomes explicam.
            forma["motivo"] = ""
        sem_compra = sum(1 for le in grupo.receitas if espera_da_receita(le) == SO_COM_O_QUE_TEM)
        item = {
            "pergunta": forma,
            "receitas": receitas,
            "liberadas": liberadas,
            "sem_compra": sem_compra,
            "sem_compra_texto": _sem_compra_texto(receitas, sem_compra),
            "nomes": [le.nome for le in grupo.receitas],
            "slugs": [le.slug for le in grupo.receitas],
            "rota": (
                rota_da_receita(grupo.receitas[0].slug)
                if receitas == 1
                else "/receitas?aba=falta_resposta"
            ),
            "texto": _contagem_texto(receitas, liberadas),
        }
        ordem = (-receitas, -liberadas, grupo.ordem, chave_do_nome(grupo.receitas[0].nome))
        saida.append((ordem, item))
    saida.sort(key=lambda par: par[0])
    return [item for _, item in saida[:MAXIMO_DE_PERGUNTAS_QUE_LIBERAM]]


# --------------------------------------------------------------------------- #
# Em que pé estão as receitas que esperam uma resposta                          #
# --------------------------------------------------------------------------- #

#: Nenhuma linha pede compra: a receita usa só o que ela tem e espera só a resposta dela.
SO_COM_O_QUE_TEM: Final = "so_com_o_que_tem"
#: Alguma linha falta, inteira ou em parte: a receita pede compra.
PRECISA_COMPRAR: Final = "precisa_comprar"
#: Nada a comprar até aqui, mas uma linha que a leitura não entendeu não casou com a
#: despensa: pode ser compra, e não dá para dizer que ela usa só o que tem.
LINHA_SEM_LEITURA: Final = "linha_sem_leitura"

#: A pergunta da rotina dita no meio da frase ("falta só a senhora me dizer ...").
_ROTINA_NA_FRASE: Final[dict[str, str]] = {
    "tempo_max_por_fornada_min": "quanto tempo consegue ficar cozinhando de uma vez",
    "bocas_fogao": "quantas bocas tem o seu fogão",
    "porcoes_por_fornada": "quantas marmitas monta numa leva",
    "espaco_geladeira_litros": "quanto cabe na sua geladeira",
    "energia_aparelhos_simultaneos": "quantos aparelhos fortes liga ao mesmo tempo",
    "tem_gas_sobrando": "como está o seu botijão de gás",
}

#: Quantas perguntas da cozinha a frase diz pelo nome; as outras viram "mais N".
_PERGUNTAS_NA_FRASE: Final = 3


def espera_da_receita(leitura: LeituraDaReceita) -> str:
    """Pela despensa, em que pé está a receita que espera uma resposta dela.

    `so_com_o_que_tem`: nenhuma linha pede compra (ela tem, vai a gosto, é o
    opcional que fica de fora, ou é um item dela que falta ela confirmar); a
    receita espera só o que ela responder. `precisa_comprar`: alguma linha
    falta, inteira ou em parte. `linha_sem_leitura`: nada a comprar até aqui,
    mas uma linha que a leitura não entendeu não casou com nada da despensa.
    """
    avaliacao = leitura.avaliacao
    faltam = (SituacaoDoIngrediente.FALTA, SituacaoDoIngrediente.TEM_PARTE)
    if avaliacao.faltantes or any(a.situacao in faltam for a in avaliacao.ajustes):
        return PRECISA_COMPRAR
    if any(
        a.situacao is SituacaoDoIngrediente.NAO_ENTENDI and a.item is None
        for a in avaliacao.ajustes
    ):
        return LINHA_SEM_LEITURA
    return SO_COM_O_QUE_TEM


def pergunta_na_frase(pergunta: Pergunta) -> str | None:
    """A pergunta da cozinha no meio de uma frase: "se tem panela de pressão".

    Só a da cozinha inteira (equipamento, técnica, rotina) tem frase; a de uma
    receita só (a linha, o rendimento, o item parecido) devolve `None`.
    """
    assunto = assunto_da(pergunta)
    try:
        if assunto is AssuntoDaPergunta.EQUIPAMENTO:
            return f"se tem {_minuscula(equipamento(pergunta.campo).nome)}"
        if assunto is AssuntoDaPergunta.TECNICA:
            nome = _minuscula(tecnica(pergunta.campo).nome).replace(" / ", " ou ")
            return f"se tem prática com {nome}"
    except VocabularioDesconhecido:
        return None
    if assunto is AssuntoDaPergunta.ROTINA:
        return _ROTINA_NA_FRASE.get(pergunta.campo)
    return None


def _o_que_falta_dizer(leituras: Sequence[LeituraDaReceita]) -> tuple[list[str], int]:
    """As perguntas da cozinha que seguram estas receitas, das que seguram mais para as
    que seguram menos, e quantas perguntas de uma receita só ficam além delas."""
    frases: dict[str, tuple[int, int, set[str]]] = {}
    de_uma_receita = 0
    for leitura in leituras:
        for pergunta in leitura.avaliacao.perguntas_da_cozinha:
            frase = pergunta_na_frase(pergunta)
            if frase is None:
                de_uma_receita += 1
                continue
            ordem = _ORDEM_DAS_PERGUNTAS.get(pergunta.tipo, 9)
            _, _, slugs = frases.setdefault(frase, (ordem, len(frases), set()))
            slugs.add(leitura.slug)
    ordenadas = sorted(frases, key=lambda f: (-len(frases[f][2]), frases[f][0], frases[f][1]))
    return ordenadas, de_uma_receita


def _falta_so(frases: list[str], de_uma_receita: int, receitas: int) -> str:
    """ "falta só a senhora me dizer quanto tempo consegue ... e se tem panela de pressão"."""
    elas = "ela" if receitas == 1 else "elas"
    ditas = frases[:_PERGUNTAS_NA_FRASE]
    mais = len(frases) - len(ditas) + de_uma_receita
    if not ditas:
        perguntas = contagem(mais, "pergunta", "perguntas")
        return f"falta só a senhora responder {perguntas} sobre {elas}"
    if mais:
        ditas = [*ditas, f"mais {contagem(mais, 'coisa', 'coisas')} sobre {elas}"]
    return f"falta só a senhora me dizer {_lista(ditas)}"


def _texto_da_espera(so: list[LeituraDaReceita], comprando: int, sem_leitura: int) -> str:
    """O que a tela e o agente dizem das receitas que esperam resposta, sem exagero."""
    total = len(so) + comprando + sem_leitura
    resto = []
    if comprando:
        resto.append(f"{contagem(comprando, 'receita pede', 'receitas pedem')} alguma compra")
    if sem_leitura:
        resto.append(
            f"{contagem(sem_leitura, 'receita tem', 'receitas têm')} uma linha que eu "
            "não consegui ler"
        )
    if so:
        usam = contagem(len(so), "receita usa", "receitas usam")
        frases, de_uma_receita = _o_que_falta_dizer(so)
        texto = f"{usam} só o que a senhora tem; {_falta_so(frases, de_uma_receita, len(so))}."
        return f"{texto} {_maiuscula(_lista(resto))}." if resto else texto
    if comprando == total:
        if total == 1:
            return "A receita que espera resposta pede alguma compra."
        return (
            f"Nenhuma das {total} receitas que esperam resposta usa só o que a senhora "
            "tem: todas pedem alguma compra."
        )
    return f"Nenhuma receita que espera resposta usa só o que a senhora tem ainda: {_lista(resto)}."


def esperando_resposta(leituras: Sequence[LeituraDaReceita]) -> dict[str, Any] | None:
    """Quantas receitas de `falta_resposta` usam só o que ela tem, e o que falta ela dizer.

    Com a cozinha nova, toda receita espera uma resposta, e a aba "Dá para
    fazer" fica vazia. Dizer que nada dá seria mentira: a verdade é que ainda
    não está confirmado. Este bloco separa, pela despensa, as que usam só o que
    ela tem (e esperam só o que ela responder) das que pedem compra e das que
    têm uma linha sem leitura, com as perguntas da cozinha que seguram as
    primeiras e o texto pronto. `None` quando nenhuma receita espera resposta.
    """
    if not leituras:
        return None
    grupos: dict[str, list[LeituraDaReceita]] = {
        SO_COM_O_QUE_TEM: [],
        PRECISA_COMPRAR: [],
        LINHA_SEM_LEITURA: [],
    }
    for leitura in leituras:
        grupos[espera_da_receita(leitura)].append(leitura)
    so = grupos[SO_COM_O_QUE_TEM]
    frases, _ = _o_que_falta_dizer(so)
    return {
        "receitas": len(leituras),
        "so_com_o_que_tem": len(so),
        "precisa_comprar": len(grupos[PRECISA_COMPRAR]),
        "linha_sem_leitura": len(grupos[LINHA_SEM_LEITURA]),
        "nomes": [le.nome for le in so],
        "slugs": [le.slug for le in so],
        "falta_dizer": frases,
        "texto": _texto_da_espera(so, len(grupos[PRECISA_COMPRAR]), len(grupos[LINHA_SEM_LEITURA])),
    }


def _perguntas_texto(leitura: LeituraDaReceita) -> list[str]:
    return [p.texto for p in leitura.avaliacao.perguntas_da_cozinha]


def catalogo_para_a_consultora(sessao: Sessao) -> dict[str, Any]:
    """O catálogo separado como na tela, para o agente responder "o que eu consigo fazer?".

    As mesmas contas da grade, receita por receita: `da_para_fazer` (a
    conferência liberou, com o que ela tem ou comprando dentro do orçamento),
    `usa_so_o_que_tem` (nada a comprar, falta ela responder), `precisa_comprar`
    (com o que falta) e `linha_sem_leitura`. O que ela não quer e o que a
    cozinha dela não permite ficam de fora, como na grade.
    """
    leituras = ler(sessao, guardadas(sessao))
    restante = sessao.dossie.orcamento().restante
    da_para_fazer = [
        {"receita_id": le.slug, "prato": le.nome, "como": selo_json(le, restante)["texto"]}
        for le in _ordenar([le for le in leituras if le.aba == "pode_fazer"], "aproveitamento")
    ]
    esperando = _ordenar([le for le in leituras if le.aba == "falta_resposta"], "aproveitamento")
    grupos: dict[str, list[dict[str, Any]]] = {
        SO_COM_O_QUE_TEM: [],
        PRECISA_COMPRAR: [],
        LINHA_SEM_LEITURA: [],
    }
    for leitura in esperando:
        espera = espera_da_receita(leitura)
        item: dict[str, Any] = {"receita_id": leitura.slug, "prato": leitura.nome}
        if espera == PRECISA_COMPRAR:
            item["falta_comprar"] = [f.nome for f in leitura.avaliacao.faltantes]
        item["falta_responder"] = _perguntas_texto(leitura)
        grupos[espera].append(item)
    resumo = esperando_resposta(esperando)
    return {
        "da_para_fazer": da_para_fazer,
        "usa_so_o_que_tem": grupos[SO_COM_O_QUE_TEM],
        "precisa_comprar": grupos[PRECISA_COMPRAR],
        "linha_sem_leitura": grupos[LINHA_SEM_LEITURA],
        "texto": resumo["texto"] if resumo else None,
    }


def _sem_compra_texto(receitas: int, sem_compra: int) -> str | None:
    """ "7 delas usam só o que a senhora tem"; `None` quando nenhuma usa."""
    if not sem_compra:
        return None
    if receitas == 1:
        return "usa só o que a senhora tem"
    if sem_compra == receitas:
        return "todas usam só o que a senhora tem"
    usam = "usa" if sem_compra == 1 else "usam"
    return f"{sem_compra} delas {usam} só o que a senhora tem"


# --------------------------------------------------------------------------- #
# O detalhe
# --------------------------------------------------------------------------- #


def avaliacao_json(leitura: LeituraDaReceita) -> dict[str, Any]:
    """`{gosta, estrelas, notas, pontuacao}` da receita."""
    return {
        "gosta": leitura.gosta,
        "estrelas": {c: leitura.estrelas.estrelas.get(c) for c in CATEGORIAS},
        "notas": leitura.estrelas.notas,
        "pontuacao": pontuacao_json(leitura.pontuacao, com_conta=True),
    }


def _custo_porcao(leitura: LeituraDaReceita) -> dict[str, Any] | None:
    from mise.cmv import calcular  # noqa: PLC0415
    from mise.erros import ErroMise  # noqa: PLC0415

    if not leitura.avaliacao.permite_precificar:
        return None
    try:
        cmv = calcular(leitura.guardada.receita, leitura.avaliacao)
    except ErroMise:
        return None
    return dinheiro_json(cmv.para_precificar)


def _rascunho_chat(leitura: LeituraDaReceita) -> str:
    """O que ela mandaria ao agente sobre esta receita, em primeira pessoa."""
    nome = _minuscula(leitura.nome)
    if leitura.avaliacao.permite_precificar:
        return f"Quanto eu cobro por uma porção de {nome}?"
    if leitura.codigo == FALTA_RESPOSTA:
        return f"O que falta para eu poder fazer {nome}?"
    if leitura.codigo == NAO_DA:
        return f"Por que eu não consigo fazer {nome}?"
    return f"Vale a pena eu fazer {nome} para vender?"


def detalhe(sessao: Sessao, slug: str) -> dict[str, Any]:
    """`GET /api/receitas/{slug}`: a receita, a conferência, o que falta e a avaliação dela.

    `checklist` é o checklist de produção (`mise.checklist`): tudo o que precisa
    estar certo antes do aceite, grupo por grupo, com o estado e a origem.
    """
    from mise.checklist import lista_de_producao  # noqa: PLC0415
    from mise.passos import avaliar_passos, perguntas_com_opcoes  # noqa: PLC0415

    guardada = guardada_por_slug(sessao, slug)
    todas = ler(sessao, guardadas(sessao))
    leitura = next((le for le in todas if le.slug == guardada.slug), None)
    if leitura is None:
        leitura = ler(sessao, [guardada])[0]
    avaliacao = leitura.avaliacao
    receita = guardada.receita
    restante = sessao.dossie.orcamento().restante
    perfil = sessao.perfil
    passos = avaliar_passos(receita, perfil)
    por_passo = passos.para_json()
    checklist = lista_de_producao(
        receita,
        perfil,
        avaliacao,
        sessao.dossie.orcamento(),
        passos=passos,
        respondidos=[r.campo for r in guardada.respostas],
    )
    return {
        "slug": guardada.slug,
        "nome": guardada.nome,
        "imagem": imagem_json(guardada),
        "fonte": fonte_json(guardada),
        "origem": guardada.origem.value,
        "tempos": tempos_json(guardada),
        "tempo_texto": tempo_texto(leitura.minutos),
        "rendimento_texto": avaliacao.rendimento.texto if avaliacao.rendimento else None,
        "veredito": avaliacao.veredito.rotulo,
        "veredito_rotulo": avaliacao.veredito.rotulo_para_ela,
        "veredito_da_cozinha": veredito_da_cozinha_json(leitura, restante),
        "resumo": avaliacao.resumo(),
        "ingredientes": ingredientes_json(avaliacao, restante),
        "linhas_nao_entendidas": linhas_nao_entendidas_json(avaliacao),
        "opcionais": opcionais_json(avaliacao),
        "avisos": avisos_json(avaliacao),
        "falta_comprar": falta_comprar_json(avaliacao, restante),
        "custo_porcao": _custo_porcao(leitura),
        "pode_precificar": avaliacao.permite_precificar,
        "passos": por_passo["passos"],
        "requisitos_da_receita": por_passo["requisitos_da_receita"],
        "perguntas": perguntas_com_opcoes(avaliacao.perguntas, passos),
        "rendimento": rendimento_json(avaliacao),
        "avaliacao": avaliacao_json(leitura),
        "posicao_no_ranking": posicao_no_ranking(todas, guardada.slug),
        "respostas": respostas_json(guardada, sessao.dossie.agora()),
        "rascunho_chat": _rascunho_chat(leitura),
        "checklist": checklist,
        "rota": rota_da_receita(guardada.slug),
    }


# --------------------------------------------------------------------------- #
# O custo por porção
# --------------------------------------------------------------------------- #


def _por_que_nao_custeia(leitura: LeituraDaReceita) -> str:
    """Por que o custo ainda não sai, dito para ela."""
    avaliacao = leitura.avaliacao
    nome = _minuscula(leitura.nome)
    if avaliacao.veredito is Veredito.BLOQUEADO:
        motivos = "; ".join(str(i) for i in avaliacao.impedimentos)
        return f"Não calculo o custo de {nome}, porque esse prato não dá: {motivos}."
    perguntas = avaliacao.perguntas
    coisas = contagem(len(perguntas), "coisa", "coisas").replace("1 coisa", "uma coisa")
    primeira = perguntas[0].texto if perguntas else ""
    return f"Ainda não calculo o custo de {nome}: antes preciso saber {coisas}. {primeira}".strip()


def custo(sessao: Sessao, slug: str) -> dict[str, Any]:
    """`GET /api/receitas/{slug}/custo`: o custo de uma porção, linha a linha.

    Passa pela conferência inteira, com o gosto: receita que ela não pode
    precificar levanta `CustoRecusado`, com o porquê na língua dela.
    """
    from mise.cmv import calcular  # noqa: PLC0415
    from mise.erros import CustoIndeterminado  # noqa: PLC0415

    guardada = guardada_por_slug(sessao, slug)
    leitura = ler(sessao, [guardada])[0]
    if not leitura.avaliacao.permite_precificar:
        raise CustoRecusado(_por_que_nao_custeia(leitura))
    try:
        cmv = calcular(guardada.receita, leitura.avaliacao)
    except CustoIndeterminado as erro:
        quais = _lista([_minuscula(i) for i in erro.ingredientes])
        raise CustoRecusado(
            f"Ainda não calculo o custo de {_minuscula(leitura.nome)}: falta o preço de {quais}."
        ) from erro
    total = cmv.total.valor
    return {
        "prato": cmv.receita,
        "rendimento_original": cmv.rendimento_original,
        "e_faixa": cmv.e_faixa,
        "total": dinheiro_json(cmv.para_precificar),
        "minimo": dinheiro_json(cmv.minimo),
        "maximo": dinheiro_json(cmv.maximo),
        "linhas": [
            {
                "ingrediente": linha.ingrediente,
                "quantidade": linha.quantidade,
                "custo": dinheiro_json(exibido),
                "derivacao": linha.derivacao,
                "fracao": round(float(linha.custo.valor / total), 2) if total else 0.0,
            }
            for linha, exibido in zip(cmv.linhas, cmv.custos_exibidos(), strict=True)
        ],
        "itens_a_gosto": list(cmv.itens_a_gosto),
        "explicacao": cmv.explicacao(),
    }


class CustoRecusado(ErroDeRegra):
    """A conferência não libera o custo desta receita; a mensagem diz por quê, para ela."""


# --------------------------------------------------------------------------- #
# A avaliação e as notas
# --------------------------------------------------------------------------- #


def _posicao_texto(posicao: int) -> str:
    if posicao <= len(_POSICOES):
        return f"em {_POSICOES[posicao - 1]} lugar"
    return f"na posição {posicao}"


def _situacao_no_ranking(leitura: LeituraDaReceita, posicao: int | None) -> str:
    nome = _maiuscula(leitura.nome)
    if posicao is not None:
        return f"{nome} está {_posicao_texto(posicao)} no ranking da senhora."
    if not leitura.estrelas.avaliada:
        return f"Quando a senhora der as estrelas, {_minuscula(leitura.nome)} entra no ranking."
    return f"{nome} entra no ranking quando der para fazer com o que a senhora tem ou pode comprar."


def resposta_da_avaliacao(
    sessao: Sessao, slug: str, *, anotou: bool, impedimento_retirado: str = ""
) -> dict[str, Any]:
    """`GET|PUT /api/receitas/{slug}/avaliacao`: a avaliação, a posição e o texto.

    `impedimento_retirado` é o impedimento que ela tinha apontado e que deixou
    de valer quando ela disse que gosta de fazer de novo: o texto diz isso.
    """
    guardada = guardada_por_slug(sessao, slug)
    todas = ler(sessao, guardadas(sessao))
    leitura = (
        next((le for le in todas if le.slug == guardada.slug), None) or ler(sessao, [guardada])[0]
    )
    posicao = posicao_no_ranking(todas, guardada.slug)
    quando = leitura.atualizada_em
    situacao = _situacao_no_ranking(leitura, posicao)
    return {
        "slug": guardada.slug,
        "nome": guardada.nome,
        "avaliacao": avaliacao_json(leitura),
        "posicao_no_ranking": posicao,
        "atualizado_texto": (
            quando_texto(quando, sessao.dossie.agora())
            if quando is not None
            else "a senhora ainda não avaliou"
        ),
        "texto": _texto_da_avaliacao(leitura, situacao, anotou, impedimento_retirado),
    }


def _texto_da_avaliacao(
    leitura: LeituraDaReceita, situacao: str, anotou: bool, impedimento_retirado: str
) -> str:
    if not anotou:
        return situacao
    if impedimento_retirado.strip():
        motivo = impedimento_retirado.strip().rstrip(".")
        return (
            f"Anotei que a senhora gosta de fazer {_minuscula(leitura.nome)}. O impedimento que "
            f"a senhora tinha apontado ({motivo}) não segura mais a receita. {situacao}"
        )
    return f"Anotei. {situacao}"


def resposta_das_notas(sessao: Sessao, slug: str, notas: EstrelasENotas) -> dict[str, Any]:
    guardada = guardada_por_slug(sessao, slug)
    quando = notas.atualizada_em
    return {
        "slug": guardada.slug,
        "notas": notas.notas,
        "atualizado_texto": (
            quando_texto(quando, sessao.dossie.agora()) if quando is not None else "agora"
        ),
        "texto": "Guardei a anotação." if notas.notas else "Apaguei a anotação.",
    }


# --------------------------------------------------------------------------- #
# Para a conversa
# --------------------------------------------------------------------------- #


def ajuste_para_a_consultora(avaliacao: Avaliacao, restante: Dinheiro) -> dict[str, Any]:
    """O ajuste à despensa que `avaliar_receita` devolve junto do parecer."""
    return {
        "ingredientes": ingredientes_json(avaliacao, restante),
        "linhas_nao_entendidas": linhas_nao_entendidas_json(avaliacao),
        "opcionais": opcionais_json(avaliacao),
        "falta_comprar_texto": falta_comprar_json(avaliacao, restante)["texto"],
    }


__all__ = [
    "ABAS",
    "CODIGO_DA_COZINHA",
    "ORDENS",
    "CustoRecusado",
    "Filtros",
    "LeituraDaReceita",
    "ajuste_para_a_consultora",
    "avaliacao_json",
    "custo",
    "detalhe",
    "estado_da_descoberta",
    "falta_comprar_json",
    "guardada_por_slug",
    "guardadas",
    "ingredientes_json",
    "item_da_grade",
    "ler",
    "lista",
    "medida_de_referencia_json",
    "medida_texto",
    "na_receita",
    "posicao_no_ranking",
    "ranking",
    "referencia_json",
    "rendimento_json",
    "resposta_da_avaliacao",
    "resposta_das_notas",
    "sem_preco_na_internet",
    "so_falta_o_preco",
    "tempo_texto",
]
