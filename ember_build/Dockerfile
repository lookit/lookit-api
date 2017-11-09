FROM node:8-slim

RUN apt-get update \
    && apt-get install -y \
        ca-certificates \
        gcc \
        git \
        build-essential \
        libssl-dev \
        libffi-dev \
        python \
        python-dev \
        python3-pip \
    # gosu
    && export GOSU_VERSION='1.10' \
    && gpg --keyserver pool.sks-keyservers.net --recv-keys B42F6819007F00F88E364FD4036A9C25BF357DD4 \
    && curl -o /usr/local/bin/gosu -SL "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-$(dpkg --print-architecture)" \
    && curl -o /usr/local/bin/gosu.asc -SL "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-$(dpkg --print-architecture).asc" \
    && gpg --verify /usr/local/bin/gosu.asc \
    && rm /usr/local/bin/gosu.asc \
    && chmod +x /usr/local/bin/gosu \
    # /gosu
    && apt-get clean \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

VOLUME /checkouts
VOLUME /deployments

COPY ./build.sh ./environment ./VideoRecorder.swf /

CMD ["/bin/bash", "/build.sh"]
