# Nieuws Piet frontend — Next.js image (taak 2.2).
#
# Stages:
#   deps    — dependencies exact uit package-lock.json (`npm ci`)
#   builder — frontend-bron + `next build`
#   runner  — productie: prod-dependencies + build-output, `npm start` op 3000
#
# `deps` is ook de stage van de ontwikkelingsopstelling (compose.dev.yaml).
# De feitelijke applicatiebron (app/ of pages/, plus public/) volgt in
# sectie 3; deze scaffolding beperkt zich tot de Docker build/run-opzet.

FROM node:20-slim AS base
WORKDIR /app
# Browser-download hoort bij de host-setup (`npx playwright install chromium`),
# niet bij deze image-build.
ENV NEXT_TELEMETRY_DISABLED=1 \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

FROM base AS deps
COPY package.json package-lock.json ./
RUN npm ci

FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# `public` standaard aanmaken zodat de runner-stage altijd uit deze stage kan kopiëren.
RUN mkdir -p public && npm run build

FROM base AS runner
ENV NODE_ENV=production
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["npm", "start"]
