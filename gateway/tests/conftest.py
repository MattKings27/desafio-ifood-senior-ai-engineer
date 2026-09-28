"""O que vale para todos os testes do gateway.

O `TestClient` do Starlette chama a API com `Host: testserver`. Em produção só
`localhost` e `127.0.0.1` passam (`gateway.seguranca`); nos testes, o nome do
cliente de teste entra na lista pela mesma variável que abriria a API para outro
nome de verdade.
"""

from __future__ import annotations

import os

# A busca da plataforma usa o modelo semântico quando ele está baixado; os testes
# usam sempre os n-gramas, que dão o mesmo resultado em qualquer máquina.
os.environ.setdefault("SABOR_VETORIZADOR", "ngramas")

# Cada rodada da descoberta de receitas custa dinheiro: nos testes ela fica sempre
# desligada, e o teste que precisa dela liga pela configuração, com o Hermes falso.
os.environ["SABOR_DESCOBERTA"] = "desligada"

# A procura do preço nos mercados de São Paulo é rede de verdade: nos testes ela
# fica desligada, e o teste que precisa dela injeta um pesquisador com respostas gravadas.
os.environ["SABOR_PRECOS_NA_WEB"] = "desligada"

_HOSTS = [h for h in os.environ.get("MISE_HOSTS", "").split(",") if h.strip()]
os.environ["MISE_HOSTS"] = ",".join(dict.fromkeys([*_HOSTS, "testserver"]))
