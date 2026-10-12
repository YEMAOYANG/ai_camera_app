FROM node:22-alpine

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund
COPY src ./src

ENV NODE_ENV=production
ENV PORT=3101
USER node
EXPOSE 3101
CMD ["node", "src/server.mjs"]
