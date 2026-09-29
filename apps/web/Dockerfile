FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
ARG API_URL=http://api:8000
ENV API_URL=$API_URL
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV API_URL=http://api:8000
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/.next/static ./app/.next/static
COPY --from=builder /app/.next/static ./apps/web/.next/static
EXPOSE 3000
USER node
CMD ["sh", "-c", "if [ -f server.js ]; then exec node server.js; elif [ -f app/server.js ]; then exec node app/server.js; else exec node apps/web/server.js; fi"]
