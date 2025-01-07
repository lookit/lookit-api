FROM python:3.9-buster

ARG GIT_TAG
ARG GIT_COMMIT
ARG POETRY_INSTALL_ARG

ENV VERSION=${GIT_TAG} \
    GIT_COMMIT=${GIT_COMMIT} \
    PATH="/root/.local/bin:${PATH}"

WORKDIR /code
COPY ./ ./

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu=1.10-1+b23 gettext=0.19.8.1-9 \
    && rm -rf /var/lib/apt/lists/* \
    && gosu nobody true \
    && update-ca-certificates \
    && pip install -U pip wheel setuptools \
    && curl -sSL --proto "=https" https://install.python-poetry.org | python3 - --version 1.8.4 \
    && poetry config virtualenvs.create false \
    && poetry install --no-dev \
    && python manage.py compilemessages 
