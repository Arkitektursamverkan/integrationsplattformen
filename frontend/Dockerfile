# ── Builder ────────────────────────────────────────────────────────────────────
FROM node:26-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

# ── Runtime (nginx) ────────────────────────────────────────────────────────────
FROM nginx:1.31-alpine AS runtime

# The release workflow passes the tag (e.g. 0.1.0).
ARG APP_VERSION=dev
LABEL org.opencontainers.image.title="Integration Platform web" \
      org.opencontainers.image.licenses="EUPL-1.2" \
      org.opencontainers.image.version="${APP_VERSION}"

COPY --from=builder /app/dist /usr/share/nginx/html
# The nginx image renders templates/*.template into conf.d at start, filling
# in only the environment variables that are set (nginx's own $host etc. stay).
# API_UPSTREAM is a host:port – on Render the API's internal hostport.
ENV API_UPSTREAM=api:8000 \
    PORT=80 \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
COPY templates/default.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
