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
        # libmagic-dev \
    # Docker
    && export DOCKER_CHANNEL=stable \
    && export DOCKER_VERSION=17.06.1-ce \
    && export DOCKER_SHA256=e35fe12806eadbb7eb8aa63e3dfb531bda5f901cd2c14ac9cdcd54df6caed697 \
    && curl -o /tmp/docker.tgz -SL "https://download.docker.com/linux/static/${DOCKER_CHANNEL}/x86_64/docker-${DOCKER_VERSION}.tgz" \
    && echo "$DOCKER_SHA256  /tmp/docker.tgz" | sha256sum -c - \
    && tar --extract --file /tmp/docker.tgz --strip-components 1 --directory /usr/local/bin/ \
    && rm /tmp/docker.tgz \
    && dockerd -v \
    && docker -v \
    # /Docker
    # gosu, verify that it works
    && gosu nobody true \
    # /gosu
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
