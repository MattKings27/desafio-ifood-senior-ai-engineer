"""`mise`: o motor determinístico do Sabor da Maria.

*Mise en place*: tudo no lugar antes de cozinhar. É literalmente o que este
pacote faz: garante que a despensa, os equipamentos, as habilidades e as
contas estejam conferidos **antes** de a Dona Maria se comprometer com um prato.

Nenhuma linha aqui chama um LLM. O agente conversa; este módulo decide e
calcula. Todo número que sai daqui carrega a derivação que o produziu, e
qualquer coisa que a planilha não permita deduzir vira uma pergunta em vez de
uma estimativa.
"""

from __future__ import annotations

from mise.cmv import CMV, calcular
from mise.despensa import (
    Confianca,
    CustoUnitario,
    Despensa,
    Ingrediente,
    Pendencia,
    carregar_despensa,
)
from mise.dinheiro import Dinheiro
from mise.elicitacao import (
    PerguntaPriorizada,
    PlanoDeElicitacao,
    montar_plano,
    proxima_pergunta,
)
from mise.erros import (
    Ausente,
    CustoIndeterminado,
    DensidadeDesconhecida,
    ErroDeDados,
    ErroDeRegra,
    ErroDeUso,
    ErroMise,
    IngredienteDesconhecido,
    MassaDesconhecida,
    OrcamentoExcedido,
    PlanilhaInvalida,
    QuantidadeInvalida,
    UnidadeNaoNormalizavel,
    UnidadesIncompativeis,
    ViabilidadeNaoConfirmada,
)
from mise.perfil import PerfilCozinha, Posse, RestricoesOperacionais
from mise.preco import (
    RETENCAO,
    TAXA_PLATAFORMA,
    Cenario,
    TabelaDePrecos,
    lucro_em,
    montar_cenarios,
    preco_minimo,
    preco_por_food_cost,
    preco_por_margem,
    preco_por_markup,
    sensibilidade,
)
from mise.receita import IngredienteReceita, Receita, ingrediente, receita
from mise.taxonomia import Equipamento, Tecnica, detectar
from mise.unidades import (
    Dimensao,
    MedidaConvertida,
    Quantidade,
    UnidadeCompra,
    classificar_medida,
    converter_medida,
    converter_medida_para_volume,
    interpretar_unidade_compra,
)
from mise.viabilidade import Avaliacao, Impedimento, Pergunta, Veredito, avaliar

__version__ = "0.1.0"

__all__ = [
    "CMV",
    "RETENCAO",
    "TAXA_PLATAFORMA",
    "Ausente",
    "Avaliacao",
    "Cenario",
    "Confianca",
    "CustoIndeterminado",
    "CustoUnitario",
    "DensidadeDesconhecida",
    "Despensa",
    "Dimensao",
    "Dinheiro",
    "Equipamento",
    "ErroDeDados",
    "ErroDeRegra",
    "ErroDeUso",
    "ErroMise",
    "Impedimento",
    "Ingrediente",
    "IngredienteDesconhecido",
    "IngredienteReceita",
    "MassaDesconhecida",
    "MedidaConvertida",
    "OrcamentoExcedido",
    "Pendencia",
    "PerfilCozinha",
    "Pergunta",
    "PerguntaPriorizada",
    "PlanilhaInvalida",
    "PlanoDeElicitacao",
    "Posse",
    "Quantidade",
    "QuantidadeInvalida",
    "Receita",
    "RestricoesOperacionais",
    "TabelaDePrecos",
    "Tecnica",
    "UnidadeCompra",
    "UnidadeNaoNormalizavel",
    "UnidadesIncompativeis",
    "Veredito",
    "ViabilidadeNaoConfirmada",
    "__version__",
    "avaliar",
    "calcular",
    "carregar_despensa",
    "classificar_medida",
    "converter_medida",
    "converter_medida_para_volume",
    "detectar",
    "ingrediente",
    "interpretar_unidade_compra",
    "lucro_em",
    "montar_cenarios",
    "montar_plano",
    "preco_minimo",
    "preco_por_food_cost",
    "preco_por_margem",
    "preco_por_markup",
    "proxima_pergunta",
    "receita",
    "sensibilidade",
]
