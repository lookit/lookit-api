FROM node:8-slim

# The checkout dir must be in the format f'{player_sha}_{addons_sha}'
# Before adding any new args, please read the docs to understand the caching impact!
# https://docs.docker.com/engine/reference/builder/#impact-on-build-caching
ARG player_addons_concat_sha
ARG ember_prepend_replacement_string

# Copy over script that will be invoked with `docker run ...`
RUN mkdir -p checkouts deployments
COPY build.sh .
COPY environment checkouts/frameplayer_exp_bundle/.env

# Mount deployable volume, which will be written to with `docker run ...`
# RUN mkdir /deployments
VOLUME /deployments

# Why is this step here and not  with the rest of the copies? Again, DLIC -
# to quote from the documentation referenced above, "If a Dockerfile defines an ARG
# variable whose value is different from a previous build, then a “cache miss” occurs
# upon its first USAGE, not its DEFINITION" (emphasis/capitalization mine). So by
# saving arg consumption until the very last two steps, we ensure that we will only
# create new image layers when *absolutely* necessary.
COPY checkouts/$player_addons_concat_sha checkouts/frameplayer_exp_bundle

# For GOSU details see https://github.com/tianon/gosu/blob/master/INSTALL.md
RUN set -eux; \
    apt-get update; \
    apt-get install -y gosu \
        ca-certificates \
        gcc \
        git \
        build-essential \
        libssl-dev \
        libffi-dev \
        python \
        python-dev \
        python3-pip; \
    rm -rf /var/lib/apt/lists/*; \
    gosu nobody true; \
    apt-get clean; \
    update-ca-certificates; \
    cd /checkouts/frameplayer_exp_bundle/lib/exp-player; \
    yarn install --pure-lockfile; \
    node_modules/.bin/bower install --allow-root; \
    cd /checkouts/frameplayer_exp_bundle; \
    yarn install --pure-lockfile; \
    node_modules/.bin/bower install --allow-root; \
    sed -i "s/prepend: ''/$ember_prepend_replacement_string/g" ember-cli-build.js; \
    node_modules/.bin/ember build --environment=production; \
# "Cheat" the layering system - kill all node_modules dirs after build finishes
    rm -rf /checkouts/frameplayer_exp_bundle/node_modules; \
    rm -rf /checkouts/frameplayer_exp_bundle/lib/exp-player/node_modules; \
    rm -rf /checkouts/frameplayer_exp_bundle/bower_components; \
# Below looks extreme, but we know what we are doing - since our container process
# will only ever use programs from /bin, we are nuking the entire /usr/ directory
# (!!!) as well as some cache stuff to mitigate disk consumption.
    rm -rf /usr /root/.cache

# Below would be the entry point for `docker run`, however we are trying to be as
# sparse as possible with the image caching layers in order to keep our disk
# consumption in check.
# CMD ["bash", "build.sh"]
