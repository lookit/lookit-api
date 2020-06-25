FROM python:3.8.3-buster

RUN apt-get update \
    && apt-get install -y \
        ca-certificates \
        gcc \
        git \
        libev4 \
        libev-dev \
        libevent-dev \
        libxml2-dev \
        libxslt1-dev \
        libffi-dev \
        python-dev \
        libpq-dev \
        graphviz \
        libgraphviz-dev \
        pkg-config \
        curl \
        gosu \
    && gosu nobody true \
    && apt-get clean \
    && apt-get autoremove -y \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install -U pip \
    && update-ca-certificates \
    && mkdir -p /code

WORKDIR /code

COPY ./requirements/ ./requirements/
RUN pip install --no-cache-dir -r ./requirements/release.txt \
    && apt-get autoremove -y \
        gcc \
    && rm -rf /var/lib/apt/lists/*

COPY ./ ./

ARG GIT_TAG
ARG GIT_COMMIT
ENV VERSION=${GIT_TAG} \
    GIT_COMMIT=${GIT_COMMIT}

CMD ["python", "manage.py", "--help"]
