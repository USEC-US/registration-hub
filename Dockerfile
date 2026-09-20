# syntax=docker/dockerfile:1.7

# -----------------------------------------------------------------------------
# Shared toolchain
#
# mise.toml is the source of truth for:
#   - Node
#   - pnpm
#   - Python
#   - uv
# -----------------------------------------------------------------------------

FROM debian:13-slim AS toolchain

ARG MISE_VERSION=2026.9.11

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        libpq5 \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV MISE_INSTALL_PATH=/usr/local/bin/mise \
    MISE_DATA_DIR=/mise \
    MISE_CACHE_DIR=/mise/cache \
    MISE_VERSION=${MISE_VERSION} \
    PATH=/mise/shims:${PATH}

RUN curl --proto '=https' --proto-redir '=https' \
        --fail --show-error --silent --location \
        https://mise.run \
        -o /tmp/install-mise.sh \
    && sh /tmp/install-mise.sh \
    && rm /tmp/install-mise.sh

WORKDIR /workspace

# Keep tool installation in its own cached layer.
COPY mise.toml ./

RUN mise trust \
    && mise install


# -----------------------------------------------------------------------------
# Frontend build
# -----------------------------------------------------------------------------

FROM toolchain AS web-build

WORKDIR /workspace

# Copy only package metadata first so dependency installation remains cached
# when application source changes.
COPY package.json \
     pnpm-lock.yaml \
     pnpm-workspace.yaml \
     ./

COPY web/package.json ./web/package.json
COPY server/package.json ./server/package.json

RUN mise exec -- \
    pnpm install \
        --frozen-lockfile \
        --filter @hcmusec-tnmt-registration/web...

# Now copy the frontend source.
COPY web ./web

# The project's build check requires a Turnstile site key.
# This is Cloudflare's public always-pass TEST site key, not a secret.
#
# The real staging site key can still be provided at runtime because the
# application uses $env/dynamic/public.
ARG PUBLIC_TURNSTILE_SITE_KEY=1x00000000000000000000AA

ENV PUBLIC_TURNSTILE_SITE_KEY=${PUBLIC_TURNSTILE_SITE_KEY}

RUN mise exec -- \
    pnpm \
        --filter @hcmusec-tnmt-registration/web \
        build

# Produce a standalone production dependency tree.
#
# /web/build is ignored by web/.gitignore, so pnpm deploy won't copy it.
# Copy the adapter-node build explicitly afterwards.
RUN mise exec -- \
    pnpm \
        --filter @hcmusec-tnmt-registration/web \
        --prod \
        deploy /out/web \
    && cp -a /workspace/web/build /out/web/build


# -----------------------------------------------------------------------------
# Backend build
# -----------------------------------------------------------------------------

FROM toolchain AS server-build

ENV UV_PROJECT_ENVIRONMENT=/app/server/.venv

WORKDIR /app

COPY mise.toml ./mise.toml
RUN mise trust /app/mise.toml

WORKDIR /app/server

COPY server/pyproject.toml server/uv.lock ./

RUN mise exec -- \
    uv sync \
        --frozen \
        --no-dev \
        --no-install-project

# Fail here instead of much later if the environment is wrong
RUN test -x /app/server/.venv/bin/python \
    && /app/server/.venv/bin/python -c \
       "import django; print('Django', django.get_version())"

# Application source
COPY server ./

# -----------------------------------------------------------------------------
# Combined runtime image
#
# Same image can run as:
#   registration-hub web
#   registration-hub api
#   registration-hub manage migrate --noinput
# -----------------------------------------------------------------------------

FROM toolchain AS runtime

ENV NODE_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VIRTUAL_ENV=/app/server/.venv \
    PATH=/app/server/.venv/bin:/mise/shims:${PATH}

WORKDIR /app

COPY mise.toml /app/mise.toml
RUN mise trust /app/mise.toml

COPY --from=web-build /out/web /app/web
COPY --from=server-build /app/server /app/server

# -----------------------------------------------------------------------------
# Django static files
#
# ServeStatic will serve these from STATIC_ROOT under ASGI/Uvicorn.
# No database connection is needed for collectstatic.
# -----------------------------------------------------------------------------

RUN cd /app/server \
    && DEBUG=False \
       SECRET_KEY=container-build-only \
       TURNSTILE_SECRET_KEY=container-build-only \
       /app/server/.venv/bin/python manage.py collectstatic --noinput


# -----------------------------------------------------------------------------
# Runtime dispatcher
# -----------------------------------------------------------------------------
COPY docker-scripts/registration-hub.sh /usr/local/bin/registration-hub
RUN chmod 0755 /usr/local/bin/registration-hub
# -----------------------------------------------------------------------------
# Non-root runtime
# -----------------------------------------------------------------------------

RUN groupadd --system --gid 10001 app \
    && useradd \
        --system \
        --no-log-init \
        --uid 10001 \
        --gid app \
        --home-dir /app \
        --no-create-home \
        app \
    && mkdir -p /app/server/media \
    && chown app:app /app/server/media

USER app

EXPOSE 3000 8000

ENTRYPOINT ["registration-hub"]
CMD ["web"]