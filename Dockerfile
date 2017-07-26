FROM python:3.6.1-slim

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
    && apt-get clean \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# grab gosu for easy step-down from root
ENV GOSU_VERSION 1.9
RUN apt-get update \
    && apt-get install -y \
        curl \
    && gpg --keyserver pool.sks-keyservers.net --recv-keys B42F6819007F00F88E364FD4036A9C25BF357DD4 \
    && curl -o /usr/local/bin/gosu -SL "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-$(dpkg --print-architecture)" \
    && curl -o /usr/local/bin/gosu.asc -SL "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-$(dpkg --print-architecture).asc" \
    && gpg --verify /usr/local/bin/gosu.asc \
    && rm /usr/local/bin/gosu.asc \
    && chmod +x /usr/local/bin/gosu \
    && apt-get clean \
    && apt-get autoremove -y \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN update-ca-certificates

RUN mkdir -p /code
WORKDIR /code

RUN pip install -U pip

COPY ./requirements/defaults.txt /code/requirements/defaults.txt
RUN pip install --no-cache-dir -r /code/requirements/defaults.txt

RUN pip install \
    uwsgi==2.0.13 \
    gevent==1.2.2 \
    psycogreen==1.0

RUN apt-get remove -y gcc

COPY ./ /code/

ARG GIT_TAG=
ARG GIT_COMMIT=
ENV VERSION ${GIT_TAG}
ENV GIT_COMMIT ${GIT_COMMIT}

CMD ["python", "manage.py", "--help"]
