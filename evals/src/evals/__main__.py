"""Executor dos evals. `python -m evals`, ou `make evals`.

Sai com 1 quando qualquer caso dourado falha ou qualquer ataque passa. É portão
de CI, não relatório: um eval que não reprova nada não muda decisão nenhuma.

**O juiz é reportado e não bloqueia**, e a distinção é deliberada. O que bloqueia
merge é o que é determinístico: veredito do portão, aritmética, recusa,
procedência. Julgamento de qualidade de conversa varia entre rodadas, e um portão
que reprova de forma diferente a cada execução é um portão que alguém desliga.
"""

from __future__ import annotations

import sys
from pathlib import Path

from evals import adversarial, portao
from evals.juiz import JuizDeterministico, calibrar, carregar_respostas

RESERVADO = Path(__file__).resolve().parents[2] / "casos" / "respostas_reservadas.yaml"


def main() -> int:
    print("Casos dourados: o sistema decide o que combinamos?\n")
    dourados = portao.rodar()
    for r in dourados:
        print(r)
    falhas = [r for r in dourados if not r.passou]

    print("\nAdversarial: dá para fazer ele decidir errado?\n")
    ataques = adversarial.rodar()
    for a in ataques:
        print(a)
    furos = [a for a in ataques if not a.defendeu]

    # O juiz é reportado, **não é portão**. Ele mede qualidade de conversa, que
    # é subjetiva; o que bloqueia merge é o que é determinístico. Um portão que
    # reprova por julgamento de modelo reprova de forma diferente a cada rodada.
    print("\nJuiz: a qualidade da conversa, medida e calibrada\n")
    juiz = JuizDeterministico()
    ajuste = calibrar(juiz)
    reservado = calibrar(juiz, carregar_respostas(RESERVADO))
    print(f"  conjunto de ajuste:   {ajuste.concordancia:.0%} (sobreajustado por construção)")
    print(f"  conjunto reservado:   {reservado.concordancia:.0%}", end="")
    print(", utilizável" if reservado.utilizavel else ", **abaixo do limiar de 80%**")
    for linha in str(reservado).splitlines()[1:]:
        print(f"  {linha}")

    print()
    print(f"  dourados:    {len(dourados) - len(falhas)}/{len(dourados)}")
    print(f"  adversarial: {len(ataques) - len(furos)}/{len(ataques)}")

    if falhas or furos:
        print()
        if falhas:
            print("  O sistema está decidindo diferente do combinado:")
            for r in falhas:
                print(f"    {r.nome}: {r.motivo}")
        if furos:
            print("  Garantias que não existem:")
            for a in furos:
                print(f"    {a.nome}: {a.garantia} ({a.detalhe})")
        return 1

    print("\n  tudo defendido")
    return 0


if __name__ == "__main__":
    sys.exit(main())
