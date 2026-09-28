"""A planilha dela em texto: a base de conhecimento que o agente e a tela leem.

Dois arquivos, os dois em UTF-8:

- **`dados/despensa_dona_maria.txt`**, versionado: a transcrição fiel da
  planilha original, célula a célula. Um teste confere cada célula contra o que
  o openpyxl lê do `.xlsx`, e confere que o arquivo é o que
  `transcrever_planilha` gera hoje (`python -m mise.planilha_txt` o refaz).
- **`.estado/despensa.txt`**, gerado no arranque e a cada mudança na despensa
  ou nos R$ 80,00: a mesma transcrição, as mudanças dela, os itens de agora com
  o custo unitário e a conta, o que ainda falta saber e o extrato dos
  complementos. A gravação é atômica (arquivo temporário e troca): quem lê no
  meio de uma escrita vê a versão anterior inteira, nunca metade.

Todo dinheiro sai como "R$ x,yy": é o formato que o guard-rail da conversa
reconhece, então o agente pode repetir um valor daqui (a ferramenta
`consultar_planilha` devolve este texto) sem ele ser apagado.
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Final

from mise import categorias
from mise.dinheiro import Dinheiro
from mise.erros import PlanilhaInvalida

if TYPE_CHECKING:
    from datetime import datetime

    from mise.despensa_editavel import EstadoDaDespensa
    from mise.dossie import EstadoOrcamento, LinhaDoExtrato

#: O nome de cada aba, dito para quem lê o texto.
DESCRICAO_DAS_ABAS: Final[dict[str, str]] = {
    "Despensa": "o estoque que ela informou",
    "Precos": "quanto ela pagou",
}

SEPARADOR: Final = " | "


@dataclass(frozen=True, slots=True)
class Celula:
    """O valor de uma célula e o formato de número dela (para saber o que é dinheiro)."""

    valor: object
    formato: str = "General"

    @property
    def e_dinheiro(self) -> bool:
        return "R$" in self.formato


def ler_celulas(caminho: str | Path) -> dict[str, list[list[Celula]]]:
    """Todas as células de todas as abas, linha a linha, como o openpyxl lê.

    Linhas inteiramente vazias no fim da aba ficam de fora; as do meio ficam.
    """
    import openpyxl  # noqa: PLC0415 (import tardio: openpyxl custa ~200ms)

    caminho = Path(caminho)
    try:
        livro = openpyxl.load_workbook(caminho, data_only=True)
    except Exception as exc:
        raise PlanilhaInvalida(f"não foi possível abrir ({exc})", str(caminho)) from exc
    try:
        abas: dict[str, list[list[Celula]]] = {}
        for aba in livro.worksheets:
            linhas = [
                [Celula(c.value, c.number_format or "General") for c in linha]
                for linha in aba.iter_rows()
            ]
            while linhas and all(c.valor is None for c in linhas[-1]):
                linhas.pop()
            abas[aba.title] = linhas
    finally:
        livro.close()
    return abas


def texto_da_celula(celula: Celula) -> str:
    """A célula como se lê no Brasil: "1,5", "R$ 24,90", texto numa linha só."""
    valor = celula.valor
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, int | float | Decimal):
        numero = Decimal(str(valor))
        if celula.e_dinheiro:
            return str(Dinheiro(numero))
        normalizado = numero.normalize()
        if normalizado == normalizado.to_integral_value():
            return str(int(normalizado))
        return f"{normalizado:f}".replace(".", ",")
    # Uma célula com quebra de linha ou com a barra do separador desmancharia a tabela.
    return " ".join(str(valor).replace("|", "/").split())


def _aba_em_texto(nome: str, linhas: list[list[Celula]], *, prefixo: str = "") -> list[str]:
    descricao = DESCRICAO_DAS_ABAS.get(nome)
    titulo = f'== Aba "{nome}"{prefixo}' + (f" ({descricao})" if descricao else "") + " =="
    return [titulo, *(SEPARADOR.join(texto_da_celula(c) for c in linha) for linha in linhas)]


def transcrever_planilha(caminho: str | Path) -> str:
    """A transcrição fiel da planilha: cada linha de cada aba, as colunas separadas por " | "."""
    caminho = Path(caminho)
    abas = ler_celulas(caminho)
    partes = [
        f"DESPENSA DA DONA MARIA: transcrição fiel da planilha {caminho.name}",
        'Cada linha é uma linha da planilha, com as colunas separadas por " | ".',
        'Números com vírgula decimal; dinheiro como "R$ x,yy".',
    ]
    for nome, linhas in abas.items():
        partes += ["", *_aba_em_texto(nome, linhas)]
    return "\n".join(partes) + "\n"


def _abas_da_transcricao(transcricao: str | None) -> list[str]:
    """As seções das abas de uma transcrição, sem o cabeçalho dela."""
    if transcricao is None:
        return ["== Planilha original ==", "(não consegui ler a planilha original agora)"]
    linhas = transcricao.splitlines()
    inicio = next((n for n, linha in enumerate(linhas) if linha.startswith("== Aba")), len(linhas))
    return [
        linha.replace('" (', '" da planilha (', 1) if linha.startswith("== Aba") else linha
        for linha in linhas[inicio:]
    ]


def montar_texto(
    *,
    transcricao: str | None,
    nome_da_planilha: str,
    estado: EstadoDaDespensa,
    orcamento: EstadoOrcamento,
    extrato: tuple[LinhaDoExtrato, ...],
    agora: datetime,
    versao: int,
) -> str:
    """O `.estado/despensa.txt`: a planilha, as mudanças dela, a despensa de agora e o extrato."""
    from mise import despensa_json as dj  # noqa: PLC0415

    despensa = estado.despensa
    por_id = {linha.id: linha for linha in extrato}
    mudancas = "mudanças da senhora incluídas" if estado.eventos else "sem mudanças da senhora"
    partes = [
        f"DESPENSA DA DONA MARIA: transcrição da planilha {nome_da_planilha}",
        f"Gerado em: {dj.data_hora_texto(agora)}. Versão {versao} ({mudancas}).",
        'Dinheiro como "R$ x,yy"; números com vírgula decimal. A planilha original não muda:',
        'o que a senhora mudou está em "Mudanças da senhora" e vale nos "Itens de hoje".',
        "",
        *_abas_da_transcricao(transcricao),
        "",
        "== Mudanças da senhora ==",
    ]
    if estado.eventos:
        for evento in estado.eventos:
            na_despensa = estado.item(evento.item_id)
            nome = na_despensa.linha.nome if na_despensa is not None else evento.item_id
            canal = "pela tela" if evento.canal == "tela" else "pela conversa"
            unidade = na_despensa.linha.unidade if na_despensa is not None else ""
            texto = dj.texto_do_evento(evento, nome, por_id, unidade)
            partes.append(f"{dj.data_hora_texto(evento.registrado)} · {nome}: {texto} ({canal})")
    else:
        partes.append("(nenhuma)")

    partes += [
        "",
        "== Itens de hoje, com o custo unitário ==",
        SEPARADOR.join(("Ingrediente", "Categoria", "Tem", "Pagou", "Custo unitário", "Conta")),
    ]
    for item in despensa:
        pagou = str(item.preco_pago) if item.preco_informado else "não informado"
        partes.append(
            SEPARADOR.join(
                (
                    item.nome,
                    categorias.categoria(item.categoria).rotulo,
                    dj.estoque_texto(item),
                    pagou,
                    dj.custo_texto(item),
                    dj.derivacao_texto(item),
                )
            )
        )
    total_itens = len(despensa)
    partes.append(
        f"Total: {total_itens} {'item' if total_itens == 1 else 'itens'}, "
        f"{despensa.total_investido} pagos."
    )

    partes += ["", "== O que ainda falta saber =="]
    if despensa.pendencias:
        for pendencia in despensa.pendencias:
            partes.append(
                f"{pendencia.ingrediente}: {pendencia.pergunta} "
                f"({dj.pendencia_json(pendencia, despensa)['impacto_texto']})"
            )
    else:
        partes.append("(nada)")

    partes += [
        "",
        f"== Complementos ({orcamento.inicial}) ==",
        f"Gasto: {orcamento.gasto} · Restam: {orcamento.restante}",
    ]
    if extrato:
        for linha in extrato:
            partes.append(
                f"{dj.data_hora_texto(linha.registrado)} · {linha.descricao} · {linha.valor}"
                + (" (devolvida)" if linha.estornada else "")
            )
    else:
        partes.append("(nenhuma compra)")
    return "\n".join(partes) + "\n"


def escrever_atomico(caminho: Path, texto: str) -> None:
    """Grava o texto inteiro ou nada: escreve ao lado e troca pelo nome certo."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    descritor, temporario = tempfile.mkstemp(
        prefix=f".{caminho.name}.", suffix=".tmp", dir=caminho.parent
    )
    try:
        with os.fdopen(descritor, "w", encoding="utf-8", newline="\n") as arquivo:
            arquivo.write(texto)
        # O temporário nasce 0600; a planilha em texto é para ler, como qualquer arquivo.
        Path(temporario).chmod(0o644)
        Path(temporario).replace(caminho)
    except BaseException:
        Path(temporario).unlink(missing_ok=True)
        raise


def main(argumentos: list[str] | None = None) -> int:
    """`python -m mise.planilha_txt PLANILHA.xlsx [SAIDA.txt]`: refaz a transcrição fiel."""
    args = sys.argv[1:] if argumentos is None else argumentos
    if not args or len(args) > 2:  # noqa: PLR2004
        print("uso: python -m mise.planilha_txt PLANILHA.xlsx [SAIDA.txt]", file=sys.stderr)
        return 2
    texto = transcrever_planilha(args[0])
    if len(args) == 2:  # noqa: PLR2004
        escrever_atomico(Path(args[1]), texto)
    else:
        sys.stdout.write(texto)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "DESCRICAO_DAS_ABAS",
    "SEPARADOR",
    "Celula",
    "escrever_atomico",
    "ler_celulas",
    "main",
    "montar_texto",
    "texto_da_celula",
    "transcrever_planilha",
]
