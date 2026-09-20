# syntax=docker/dockerfile:1

ARG NODE_VERSION=24.18.0
ARG PYTHON_VERSION=3.14


# ---------------------------------------------------------------------
# Node runtime source
# ---------------------------------------------------------------------

FROM node:${NODE_VERSION}-bookworm-slim AS node-runtime


# ---------------------------------------------------------------------
# SvelteKit build
# ---------------------------------------------------------------------

FROM node:${NODE_VERSION}-bookworm-slim AS web-build

WORKDIR /workspace

RUN corepack enable \
    && corepack prepare pnpm@12.3.4 --activate

# Copy manifests first for dependency-layer caching.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY web/package.json ./web/package.json
COPY server/package.json ./server/package.json

RUN pnpm install \
    --frozen-lockfile \
    --filter @hcmusec-tnmt-registration/web...

COPY web ./web

# Your build script deliberately requires this value.
#
# The application itself reads $env/dynamic/public, so the real staging
# sitekey is still supplied at runtime. This value only satisfies the
# production-build validation.
ARG PUBLIC_TURNSTILE_SITE_KEY
ENV PUBLIC_TURNSTILE_SITE_KEY=${PUBLIC_TURNSTILE_SITE_KEY}

RUN pnpm --filter @hcmusec-tnmt-registration/web build

# Produce a portable production package with only runtime dependencies.
RUN pnpm \
      --filter @hcmusec-tnmt-registration/web \
      --prod \
      deploy /out/web \
    && cp -a web/build /out/web/build


# ---------------------------------------------------------------------
# Django dependencies
# ---------------------------------------------------------------------

FROM python:${PYTHON_VERSION}-slim-bookworm AS server-build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Important: keep this path identical to the final image because Python
# virtualenv launcher scripts contain absolute paths.
WORKDIR /app/server

COPY server/pyproject.toml server/uv.lock ./

RUN uv sync \
    --frozen \
    --no-dev \
    --no-install-project


# ---------------------------------------------------------------------
# Combined application runtime
# ---------------------------------------------------------------------

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libpq5 \
        libstdc++6 \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

# adapter-node only needs the Node runtime here; npm/pnpm aren't required.
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NODE_ENV=production \
    PATH="/app/server/.venv/bin:${PATH}"

WORKDIR /app

# Django
COPY --from=server-build /app/server/.venv /app/server/.venv
COPY server /app/server

# SvelteKit + production node_modules
COPY --from=web-build /out/web /app/web

# Collect Django admin/application static files into the image.
RUN cd /app/server \
    && SECRET_KEY=docker-build-only \
       TURNSTILE_SECRET_KEY=docker-build-only \
       python manage.py collectstatic --noinput

# Don't run application processes as root.
RUN useradd --system --uid 10001 --create-home app \
    && mkdir -p /app/server/media \
    && chown -R app:app /app

USER app

EXPOSE 3000 8000

# Useful default when running the image manually.
CMD ["node", "/app/web/build/index.js"]