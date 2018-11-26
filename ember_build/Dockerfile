FROM node:8-slim

# The checkout dir must be in the format f'{player_sha}_{addons_sha}'
# Before adding any new args, please read the docs to understand the caching impact!
# https://docs.docker.com/engine/reference/builder/#impact-on-build-caching
ARG player_addons_concat_sha
ARG ember_prepend_replacement_string
ARG study_uuid

# Dependencies.
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

# Create root for checkout.
WORKDIR checkouts
COPY checkouts/$player_addons_concat_sha frameplayer_exp_bundle
COPY environment frameplayer_exp_bundle/.env

# Build exp-player
WORKDIR /checkouts/frameplayer_exp_bundle/lib/exp-player
RUN yarn install
RUN node_modules/.bin/bower install --allow-root

# Build frameplayer
WORKDIR /checkouts/frameplayer_exp_bundle
RUN yarn install
RUN node_modules/.bin/bower install --allow-root
# TODO: get rid of ember prepend replacement string.
# The ember prepend clause value is actually mostly static - it looks like so:
# /studies/${STUDY_UUID} so it *could* be constructed at runtime instead of being
# passed in whole like this. The problem is that string interpolation in docker
# is finicky. Whoever figures out how to do this gets a gold star.
RUN sed -i "s/prepend: ''/$ember_prepend_replacement_string/g" ember-cli-build.js
RUN node_modules/.bin/ember build --environment=production

# Mount deployable volume, which will be written to with `docker run ...`
RUN mkdir /deployments
VOLUME /deployments

# Copy over script that will be invoked with `docker run ...`
WORKDIR /
COPY build.sh .

# This is the entry point for `docker run`.
CMD ["bash", "build.sh"]
