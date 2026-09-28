# Imagem do motor e do gateway.
#
# Multi-stage por dois motivos, nessa ordem de importância: a imagem final não
# carrega compilador nem cabeçalho de desenvolvimento, que é superfície de ataque
# a mais; e ela fica pequena o bastante para o `docker pull` não ser o passo
# lento do deploy.
#
# A interface web não entra aqui. Next.js tem o próprio caminho de build e
# empacotar os dois na mesma imagem faria um deploy de CSS reiniciar o motor.

# --------------------------------------------------------------------------- #
# Estágio 1: dependências                                                      #
# --------------------------------------------------------------------------- #
FROM python:3.12-slim-bookworm AS dependencias

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /construcao

# Os seis pacotes, instalados pelo mesmo script do bootstrap e do CI. A imagem
# antiga copiava só os `__init__.py` antes do install, para aproveitar cache de
# camada, e instalava três pacotes de seis: o resultado era um venv com pacotes
# vazios que o `gateway.http` não conseguia importar. Cache de camada não vale
# uma imagem que não sobe; o script termina importando cada ponto de entrada,
# então um pacote faltando reprova o `docker build`, não o deploy.
COPY scripts/preparar_ambiente.sh scripts/
COPY mise mise
COPY gateway gateway
COPY retrieval retrieval
COPY telemetria telemetria
COPY auditor auditor
COPY evals evals

RUN bash scripts/preparar_ambiente.sh /opt/venv --sem-dev

# --------------------------------------------------------------------------- #
# Estágio 2: imagem final                                                      #
# --------------------------------------------------------------------------- #
FROM python:3.12-slim-bookworm AS producao

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    MISE_PLANILHA=/app/dados/despensa_dona_maria.xlsx \
    MISE_DOSSIE=/dados/dossie.db \
    MISE_AUDITORIA=/dados/auditoria.jsonl \
    MISE_HTTP_HOST=0.0.0.0 \
    MISE_HTTP_PORT=8777

# Usuário sem privilégio. Container que roda como root e é comprometido entrega
# root, e não há uma única razão para este processo precisar disso.
RUN useradd --create-home --uid 10001 cozinha

COPY --from=dependencias /opt/venv /opt/venv

WORKDIR /app
COPY --chown=cozinha:cozinha dados ./dados

# O dossiê é estado e mora em volume: reiniciar o container não pode apagar o
# que a Dona Maria respondeu.
RUN mkdir -p /dados && chown cozinha:cozinha /dados
VOLUME ["/dados"]

USER cozinha
EXPOSE 8777

# O **mesmo** ponto de entrada do `make api`. Um segundo caminho só para o
# container seria um caminho a menos testado, e seria justamente o que roda em
# produção. `main()` já lê host e porta do ambiente, que é o que as variáveis
# acima ajustam.
CMD ["python", "-m", "gateway.http"]
