FROM python:3.6-slim-jessie

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
        # psycopg2
        python-dev \
        libpq-dev \
        graphviz \
        libgraphviz-dev \
        pkg-config \
        curl \
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
    # gosu
    && export GOSU_VERSION=1.10 \
    && gpg --keyserver pool.sks-keyservers.net --recv-keys B42F6819007F00F88E364FD4036A9C25BF357DD4 \
    && curl -o /usr/local/bin/gosu -SL "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-$(dpkg --print-architecture)" \
    && curl -o /usr/local/bin/gosu.asc -SL "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-$(dpkg --print-architecture).asc" \
    && gpg --verify /usr/local/bin/gosu.asc \
    && rm /usr/local/bin/gosu.asc \
    && chmod +x /usr/local/bin/gosu \
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

ARG GIT_TAG=
ARG GIT_COMMIT=
ENV VERSION=${GIT_TAG} \
    GIT_COMMIT=${GIT_COMMIT}

CMD ["python", "manage.py", "--help"]
