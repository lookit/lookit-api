FROM python:3.9-buster

ARG GIT_TAG
ARG GIT_COMMIT
ARG POETRY_INSTALL_ARG

ENV VERSION=${GIT_TAG} \
    GIT_COMMIT=${GIT_COMMIT} \
    PATH="/root/.local/bin:/code/.venv/bin:${PATH}"

WORKDIR /code
COPY ./ ./
ADD https://astral.sh/uv/install.sh /uv-installer.sh

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu=1.10-1+b23 gettext=0.19.8.1-9  \
    && rm -rf /var/lib/apt/lists/*  \
    && gosu nobody true  \
    && update-ca-certificates  \
    && sh /uv-installer.sh  \
    && rm /uv-installer.sh \
    && uv sync --frozen --no-dev  \
    && python manage.py compilemessages
