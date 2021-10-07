FROM python:3.8.3-buster

ARG GIT_TAG
ARG GIT_COMMIT
ARG POETRY_INSTALL_ARG
ENV VERSION=${GIT_TAG} \
    GIT_COMMIT=${GIT_COMMIT} 

WORKDIR /code
COPY ./ ./

SHELL ["/bin/bash", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu=1.10-1+b23 gettext=0.19.8.1-9 \
    && rm -rf /var/lib/apt/lists/* \
    && gosu nobody true \
    && update-ca-certificates \
    && wget https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py -q -O /tmp/get-poetry.py \
    && python /tmp/get-poetry.py  \
    && source "$HOME/.poetry/env" \
    && poetry config virtualenvs.create false \
    && poetry install --no-dev
