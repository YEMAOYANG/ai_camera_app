# syntax=docker/dockerfile:1.7

FROM node:22-bookworm-slim AS dependencies
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM dependencies AS builder
ARG MIRA_STUDENT_WEB_PUBLIC_URL
ARG OPENMAIC_FULL_RUNTIME_PUBLIC_URL
ENV NODE_ENV=production \
    MIRA_BACKEND_URL=http://backend:8000 \
    MIRA_STUDENT_WEB_PUBLIC_URL=${MIRA_STUDENT_WEB_PUBLIC_URL} \
    OPENMAIC_FULL_RUNTIME_PUBLIC_URL=${OPENMAIC_FULL_RUNTIME_PUBLIC_URL}
COPY . .
# next.config.ts bakes the trusted classroom origin into Permissions-Policy.
# Record both public addresses so startup cannot silently use different ones.
RUN node <<'NODE'
const fs = require('node:fs');
const names = ['MIRA_STUDENT_WEB_PUBLIC_URL', 'OPENMAIC_FULL_RUNTIME_PUBLIC_URL'];
const urls = {};
for (const name of names) {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is a required build argument`);
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new Error(`${name} must be an HTTPS origin without credentials, path, query or fragment`);
  }
  urls[name] = url.origin;
}
fs.writeFileSync('.build-public-urls.json', JSON.stringify(urls));
NODE
RUN npm run build

FROM dependencies AS production-dependencies
RUN npm prune --omit=dev --ignore-scripts --no-audit --no-fund

FROM node:22-bookworm-slim AS runner
WORKDIR /app
ARG MIRA_STUDENT_WEB_PUBLIC_URL
ARG OPENMAIC_FULL_RUNTIME_PUBLIC_URL
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    MIRA_BACKEND_URL=http://backend:8000 \
    MIRA_STUDENT_WEB_PUBLIC_URL=${MIRA_STUDENT_WEB_PUBLIC_URL} \
    OPENMAIC_FULL_RUNTIME_PUBLIC_URL=${OPENMAIC_FULL_RUNTIME_PUBLIC_URL}

COPY --from=production-dependencies --chown=node:node /app/node_modules ./node_modules
COPY --from=builder --chown=node:node /app/package.json /app/package-lock.json ./
COPY --from=builder --chown=node:node /app/.next ./.next
COPY --from=builder --chown=node:node /app/public ./public
COPY --from=builder --chown=node:node /app/next.config.ts /app/tsconfig.json ./
# next start loads the existing TypeScript config and its security helpers.
COPY --from=builder --chown=node:node /app/src/lib/security ./src/lib/security
COPY --from=builder --chown=node:node /app/.build-public-urls.json ./
RUN <<'SHELL'
cat > /app/docker-start.cjs <<'NODE'
const fs = require('node:fs');
const expected = JSON.parse(fs.readFileSync('/app/.build-public-urls.json', 'utf8'));
for (const [name, origin] of Object.entries(expected)) {
  const url = new URL(process.env[name]);
  if (url.origin !== origin || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new Error(`${name} differs from the image build; rebuild the image for the new public origin`);
  }
}
NODE
SHELL
USER node
EXPOSE 3000
# The root redirect needs no backend, authentication or paid provider calls.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:' + (process.env.PORT || '3000') + '/', {redirect:'manual', signal:AbortSignal.timeout(4000)}).then(r => process.exit(r.status >= 200 && r.status < 400 ? 0 : 1)).catch(() => process.exit(1))"
CMD ["sh", "-c", "node /app/docker-start.cjs && exec node node_modules/next/dist/bin/next start --hostname 0.0.0.0 --port \"$PORT\""]
