#!/usr/bin/env python
"""Mede os tokens visuais do site do iFood, em vez de copiá-los de guias de terceiros.

Todo guia de marca disponível publicamente diz que o vermelho do iFood é
`#EA1D2C`. O site ao vivo usa `#EB0033`. A diferença é imperceptível no olho e
decisiva na acessibilidade: `#EA1D2C` reprova no WCAG AA para texto pequeno por
0,04 de contraste, e `#EB0033` passa.

Esse é o argumento do script: fidelidade visual vira medição, não opinião.

Uso:

    PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright \\
      mise/.venv/bin/python webapp/scripts/medir-ifood.py

Requer `playwright` no venv e o Chromium que o instalador do Hermes já baixa.
A saída vai para `.estado/design/medicao.json` e `.estado/design/*.png`.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ALVOS = (
    "https://www.ifood.com.br/",
    "https://institucional.ifood.com.br/",
    # O portal do lojista é a superfície que importa aqui: a Dona Maria **é**
    # lojista, e a interface dela deve se parecer com a que o iFood dá a quem
    # vende, não com a que dá a quem compra. As duas divergem: a do lojista tem
    # cabeçalho branco, radius maior e a família tipográfica declarada.
    "https://parceiros.ifood.com.br/",
)

SAIDA = Path(__file__).resolve().parents[2] / ".estado" / "design"

AGENTE = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)

#: Roda no browser. Conta estilos computados de todo elemento visível, para que
#: a frequência indique o que é token de sistema e o que é exceção de uma tela.
COLETA = """() => {
  const visivel = el => {
    const r = el.getBoundingClientRect();
    return r.width > 20 && r.height > 12 && getComputedStyle(el).visibility !== 'hidden';
  };
  const mapas = {
    radius: {}, sombra: {}, fonte: {}, peso: {}, tamanho: {},
    cor: {}, fundo: {}, transicao: {}, borda: {},
  };
  const add = (m, k) => { if (k) m[k] = (m[k] || 0) + 1; };

  for (const el of document.querySelectorAll('*')) {
    if (!visivel(el)) continue;
    const s = getComputedStyle(el);
    add(mapas.radius,   s.borderRadius !== '0px' ? s.borderRadius : null);
    add(mapas.sombra,   s.boxShadow !== 'none' ? s.boxShadow : null);
    add(mapas.fonte,    s.fontFamily);
    add(mapas.peso,     s.fontWeight);
    add(mapas.tamanho,  s.fontSize);
    add(mapas.cor,      s.color);
    add(mapas.fundo,    s.backgroundColor !== 'rgba(0, 0, 0, 0)' ? s.backgroundColor : null);
    add(mapas.borda,    s.borderTopWidth !== '0px' ? s.borderTopColor : null);
    if (s.transitionDuration !== '0s') {
      add(mapas.transicao, `${s.transitionDuration} ${s.transitionTimingFunction}`);
    }
  }
  const ordenar = m => Object.entries(m).sort((a, b) => b[1] - a[1]);
  const saida = {};
  for (const [nome, mapa] of Object.entries(mapas)) saida[nome] = ordenar(mapa);
  saida._titulo = document.title;
  saida._nos = document.querySelectorAll('*').length;
  return saida;
}"""


def rgb_para_hex(valor: str) -> str | None:
    """`rgb(235, 0, 51)` -> `#EB0033`. Devolve `None` se não for rgb sólido."""
    if not valor.startswith("rgb(") or not valor.endswith(")"):
        return None
    try:
        partes = [int(p.strip()) for p in valor[4:-1].split(",")]
    except ValueError:
        return None
    if len(partes) != 3:
        return None
    return "#{:02X}{:02X}{:02X}".format(*partes)


def _luminancia(hexa: str) -> float:
    componentes = [int(hexa[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in componentes
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contraste(a: str, b: str) -> float:
    """Razão de contraste do WCAG 2.2 entre duas cores hex."""
    maior, menor = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (maior + 0.05) / (menor + 0.05)


def medir() -> dict[str, Any]:
    # Import aqui dentro: o Playwright é dependência opcional, só desta medição.
    from playwright.sync_api import sync_playwright

    SAIDA.mkdir(parents=True, exist_ok=True)
    resultados: dict[str, Any] = {}

    with sync_playwright() as pw:
        navegador = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        contexto = navegador.new_context(
            viewport={"width": 1440, "height": 900}, locale="pt-BR", user_agent=AGENTE
        )
        pagina = contexto.new_page()

        for url in ALVOS:
            nome = url.split("//")[1].split(".")[0]
            try:
                resposta = pagina.goto(
                    url, wait_until="domcontentloaded", timeout=45_000
                )
                pagina.wait_for_timeout(3_500)
                dados = pagina.evaluate(COLETA)
                dados["_http"] = resposta.status if resposta else None
                dados["_url"] = url
                resultados[nome] = dados
                pagina.screenshot(path=str(SAIDA / f"{nome}.png"))
                print(f"✓ {url} · HTTP {dados['_http']} · {dados['_nos']} nós")
            except Exception as erro:  # noqa: BLE001 - coleta de site externo é best-effort
                print(f"✗ {url} -> {type(erro).__name__}: {erro}", file=sys.stderr)
                resultados[nome] = {"_erro": f"{type(erro).__name__}: {erro}"}

        navegador.close()

    (SAIDA / "medicao.json").write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return resultados


def relatar(resultados: dict[str, Any]) -> None:
    """Imprime os tokens candidatos e o contraste de cada cor sobre branco."""
    cores: Counter[str] = Counter()
    for dados in resultados.values():
        if "_erro" in dados:
            continue
        for grupo in ("cor", "fundo"):
            for valor, n in dados.get(grupo, []):
                if (hexa := rgb_para_hex(valor)) is not None:
                    cores[hexa] += n

    print(f"\n{'cor':<12}{'amostras':>10}{'contraste/branco':>19}  {'AA texto':<10}")
    print("-" * 54)
    for hexa, n in cores.most_common(12):
        razao = contraste(hexa, "#FFFFFF")
        veredito = "passa" if razao >= 4.5 else "falha"
        print(f"{hexa:<12}{n:>10}{razao:>18.2f}:1  {veredito:<10}")

    for nome, dados in resultados.items():
        if "_erro" in dados:
            continue
        print(f"\n=== {nome} ===")
        for grupo in ("radius", "sombra", "transicao", "tamanho"):
            topo = dados.get(grupo, [])[:5]
            if topo:
                print(f"  {grupo}: " + " · ".join(f"{v[:44]} ({n}×)" for v, n in topo))


if __name__ == "__main__":
    relatar(medir())
