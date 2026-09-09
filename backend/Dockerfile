FROM node:22-bookworm-slim AS sidecar-deps

WORKDIR /sidecar
COPY openmaic-sidecar/package.json openmaic-sidecar/package-lock.json ./
RUN npm ci --omit=dev

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system mira \
    && useradd --system --gid mira --home-dir /app mira

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY --chown=mira:mira . .
COPY --from=sidecar-deps /usr/local/bin/node /usr/local/bin/node
COPY --from=sidecar-deps --chown=mira:mira /sidecar/node_modules ./openmaic-sidecar/node_modules
RUN chmod 0755 scripts/start-prod.sh \
    && mkdir -p data/learning-media \
    && chown -R mira:mira data

USER mira

EXPOSE 8000

CMD ["./scripts/start-prod.sh"]
