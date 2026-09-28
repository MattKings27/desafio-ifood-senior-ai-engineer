# Sabor da Maria: atalhos do projeto. `make` sozinho lista todos.
#
#   make bootstrap   prepara ambiente, perfil do Hermes, skills, plugin e MCP (idempotente)
#   make test        lint, tipos e os testes com cobertura
#   make evals       casos dourados e adversariais do motor, sem gastar token
#   make dev         API, interface e agente, juntos
#   make chat        conversa com o agente no terminal
#
.DEFAULT_GOAL := ajuda
SHELL := /usr/bin/env bash

RAIZ    := $(shell pwd)
VENV    := $(RAIZ)/mise/.venv
PY      := $(VENV)/bin/python
PERFIL  := sabor-da-maria
HERMES  := $(shell command -v hermes 2>/dev/null || echo $$HOME/.local/bin/hermes)

export MISE_PLANILHA := $(RAIZ)/dados/despensa_dona_maria.xlsx
export MISE_DOSSIE   := $(RAIZ)/.estado/dossie.db
export MISE_AUDITORIA := $(RAIZ)/.estado/auditoria.jsonl

.PHONY: ajuda comecar bootstrap perfil-avaliacao evals-agente clone-limpo test testes cobertura cobertura-diff portoes higiene tipos lint formato plugin design medir evals evals-recuperacao conferir-conhecimento conferir-referencias conferir-fotos conferir-fotos-cozinha observabilidade auditor api web dev demo agente-status reiniciar-agente chat tui mcp auditoria limpar conferir-passos conciliar

ajuda:  ## Mostra estes comandos
	@echo "Sabor da Maria: agente de cardápio e precificação"
	@echo
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-17s\033[0m %s\n",$$1,$$2}'

# Numa máquina nova: o Hermes antes do bootstrap, e a conferência de tudo depois.
.PHONY: instalar-hermes verificar

comecar:  ## Um comando do clone ao site: instala o Hermes, guarda a chave, monta o agente e sobe tudo
	@scripts/comecar.sh

instalar-hermes:  ## Instala o Hermes Agent no commit testado, pelo instalador oficial (FORCAR=1 troca outra versão)
	@FORCAR=$(FORCAR) SIMULAR=$(SIMULAR) scripts/instalar_hermes.sh

# Só a biblioteca padrão do Python do sistema: roda antes de existir o
# ambiente do projeto, para dizer o que falta.
verificar:  ## Confere sistema, ferramentas, agente, chaves e portas, com o comando que conserta cada item
	@python3 scripts/verificar_ambiente.py

bootstrap:  ## Prepara ambiente, perfil do Hermes, skills, plugin e MCP
	@./hermes/bootstrap.sh
	@git config core.hooksPath .githooks
	@echo "pre-commit ativo (.githooks/pre-commit)"

perfil-avaliacao:  ## Perfil descartável do Hermes para os cenários do agente
	@PERFIL_HERMES=$(PERFIL)-avaliacao ./hermes/bootstrap.sh

evals-agente:  ## Cenários no agente real (gasta tokens). K=3 MODELO=... ESFORCO=high
	@$(PY) -m evals.agente $(or $(CENARIOS),evals/casos/agente/*.yaml) --k $(or $(K),1) \
		--perfil $(PERFIL)-avaliacao $(if $(MODELO),--modelo $(MODELO)) \
		$(if $(ESFORCO),--esforco $(ESFORCO)) $(if $(SAIDA),--saida $(SAIDA))

clone-limpo:  ## Clona o commit atual e sobe tudo do zero (--com-hermes com H=1)
	@scripts/clone_limpo.sh $(if $(H),--com-hermes)

portoes:  ## Roda os testes dos próprios portões de CI
	@$(PY) -m pytest scripts/tests -q -p no:cacheprovider

higiene:  ## Travessão separando ideias, caminho local e plural com (s) na tela
	@$(PY) scripts/higiene.py

cobertura-diff:  ## Cobertura das linhas que este branch mudou (piso 80%)
	@cd mise && $(PY) -m pytest -q --cov --cov-report=xml > /dev/null
	@cd gateway && $(PY) -m pytest -q --cov --cov-report=xml > /dev/null
	@$(PY) scripts/cobertura_do_diff.py --base origin/main \
		mise/coverage.xml gateway/coverage.xml

test: lint tipos testes  ## Roda tudo: lint, tipos e testes com cobertura

testes:  ## pytest com cobertura nos seis pacotes, no plugin e nas instruções do agente
	@echo "── motor (mise) ──────────────────────────────────────────"
	@cd mise && $(PY) -m pytest -q --cov
	@echo "── gateway ───────────────────────────────────────────────"
	@cd gateway && $(PY) -m pytest -q --cov
	@echo "── pesquisa de receita (retrieval) ───────────────────────"
	@cd retrieval && $(PY) -m pytest -q --cov
	@echo "── auditor A2A ───────────────────────────────────────────"
	@cd auditor && $(PY) -m pytest -q --cov
	@echo "── telemetria ────────────────────────────────────────────"
	@cd telemetria && $(PY) -m pytest -q --cov
	@echo "── avaliador (evals) ─────────────────────────────────────"
	@cd evals && $(PY) -m pytest -q --cov
	@echo "── plugin guardrail ──────────────────────────────────────"
	@$(PY) -m pytest hermes/plugins/guardrail-numerico -q -p no:cacheprovider
	@echo "── instruções e configuração do agente ───────────────────"
	@$(PY) -m pytest hermes/tests -q -p no:cacheprovider

tipos:  ## mypy --strict
	@cd mise && $(PY) -m mypy src/mise
	@cd gateway && $(PY) -m mypy src
	@cd retrieval && $(PY) -m mypy src/retrieval
	@cd evals && $(PY) -m mypy src/evals
	@cd telemetria && $(PY) -m mypy src/telemetria
	@cd auditor && $(PY) -m mypy src/auditor

lint:  ## ruff
	@cd mise && $(PY) -m ruff check . && $(PY) -m ruff format --check .
	@cd gateway && $(PY) -m ruff check . && $(PY) -m ruff format --check .
	@cd retrieval && $(PY) -m ruff check . && $(PY) -m ruff format --check .
	@cd evals && $(PY) -m ruff check . && $(PY) -m ruff format --check .
	@cd telemetria && $(PY) -m ruff check . && $(PY) -m ruff format --check .
	@cd auditor && $(PY) -m ruff check . && $(PY) -m ruff format --check .

formato:  ## Aplica formatação
	@cd mise && $(PY) -m ruff format . && $(PY) -m ruff check --fix .
	@cd gateway && $(PY) -m ruff format . && $(PY) -m ruff check --fix .

evals:  ## Casos dourados + adversarial (portão: reprova se algo decidir diferente)
	@$(PY) -m evals

conciliar:  ## Confere a plataforma contra a planilha crua, item por item (API=http://127.0.0.1:8777 confere a que está no ar)
	@$(PY) scripts/conciliar_planilha.py $(if $(API),--api $(API))

evals-recuperacao:  ## Conjunto dourado da busca: revocação, MRR, nDCG, abstenção e ablação
	@$(PY) -m evals.recuperacao $(if $(SAIDA),--saida $(SAIDA))

conferir-conhecimento:  ## Busca cada página citada e prova que o trecho continua lá (rede)
	@$(PY) scripts/conferir_conhecimento.py

conferir-referencias:  ## Busca cada preço de referência e cada linha do IBGE e prova que continuam lá (rede)
	@$(PY) scripts/conferir_referencias.py

conferir-fotos:  ## Pergunta ao Commons por cada foto dos ingredientes: licença livre, autor e endereço (rede)
	@$(PY) scripts/conferir_fotos.py

conferir-fotos-cozinha:  ## O mesmo para as fotos dos equipamentos e técnicas da cozinha (rede)
	@$(PY) scripts/conferir_fotos.py --cozinha

conferir-passos:  ## Confere os passos de cada receita do catálogo com o JSON-LD da página (rede; só lê a API, API=...)
	@$(PY) scripts/conferir_passos.py $(if $(API),--api $(API))

design:  ## Valida DESIGN.md (estrutura + contraste WCAG) e exporta tokens
	@npx -y @google/design.md@0.4.0 lint DESIGN.md
	@npx -y @google/design.md@0.4.0 export DESIGN.md --format tailwind > webapp/tokens.tailwind.json
	@echo "tokens exportados para webapp/tokens.tailwind.json"

medir:  ## Mede de novo os tokens visuais no site do iFood (Playwright)
	@PLAYWRIGHT_BROWSERS_PATH=$$HOME/.cache/ms-playwright $(PY) webapp/scripts/medir-ifood.py

plugin:  ## Valida o plugin no CI gate do próprio Hermes
	@$(HERMES) plugins validate hermes/plugins/guardrail-numerico

auditor:  ## Sobe o par A2A que confere a conta, em :8899
	@$(PY) -m auditor.servidor

api:  ## Sobe a API HTTP do motor em :8777
	@$(PY) -m gateway.http

web:  ## Sobe a interface em :3000 (precisa do `make api` rodando)
	@cd webapp && npm run dev

dev:  ## API, interface e o agente juntos, logs prefixados (Ctrl-C derruba tudo)
	@scripts/dev.sh

# Igual ao `make dev`, mas com a interface compilada para produção: sem o
# indicador de desenvolvimento do Next, com o desempenho que a banca vai ver.
demo:  ## Como o make dev, com a interface em modo de produção (para gravar a demonstração)
	@cd webapp && npm run build
	@DEV_CMD_WEB='cd $(CURDIR)/webapp && MISE_API=http://127.0.0.1:8777 exec node_modules/.bin/next start -p 3000' scripts/dev.sh

agente-status:  ## Gateway, servidor de API, chaves e modelo do agente (sem segredo)
	@$(PY) -m gateway.hermes_operacao status --perfil $(PERFIL)

# O servidor de API do agente mora no gateway: reiniciar deixa o chat da web
# sem o agente por alguns segundos, em todos os perfis. Por isso o aviso e os
# 5 s para desistir, e por isso o bootstrap aceita SEM_REINICIAR=1.
reiniciar-agente:  ## Reinicia o gateway do Hermes (o chat da web fica sem o agente por alguns segundos)
	@printf '\033[33m!\033[0m %s\n' \
	  "Reiniciar o gateway deixa o chat da web de todos os perfis sem o agente por alguns segundos." \
	  "Ctrl-C nos próximos 5 s para desistir."
	@sleep 5
	@$(HERMES) gateway restart
	@$(PY) -m gateway.hermes_operacao status --perfil $(PERFIL) --esperar 90

chat:  ## Conversa com o agente
	@$(HERMES) -p $(PERFIL)

tui:  ## Conversa na interface completa
	@$(HERMES) -p $(PERFIL) --tui

mcp:  ## Confere a integração MCP
	@$(HERMES) -p $(PERFIL) mcp test mise

observabilidade:  ## Latência p50/p95/p99 por rota, do motor no ar
	@curl -s http://127.0.0.1:8777/observabilidade | $(PY) -c "\
import json,sys; d=json.load(sys.stdin)['dados']; \
[print(f\"  {s['ferramenta']:30} {s['chamadas']:>4}x  p50 {s['p50_ms']:>8.1f}ms  p95 {s['p95_ms']:>8.1f}ms  erro {s['taxa_de_erro']:.1%}\") for s in d['series']] or print('  nenhuma chamada ainda')"

auditoria:  ## Últimas chamadas ao motor
	@test -f .estado/auditoria.jsonl && tail -20 .estado/auditoria.jsonl | \
	  $(PY) -c "import sys,json,datetime; [print(f\"{datetime.datetime.fromtimestamp(e['momento']):%H:%M:%S}  {e['ferramenta']:<26} {e['resultado']:<8} {e['duracao_ms']:>7.1f}ms\") for e in map(json.loads, sys.stdin)]" \
	  || echo "sem trilha ainda: converse com o agente primeiro"

limpar:  ## Remove caches (preserva o dossiê)
	@find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache \) -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "caches removidos (o dossiê em .estado/ foi preservado)"
