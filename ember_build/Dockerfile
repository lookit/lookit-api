FROM node:10-slim

#####
# For GOSU details see https://github.com/tianon/gosu/blob/master/INSTALL.md
#####

RUN set -eux; 
RUN echo "deb http://archive.debian.org/debian/ stretch main contrib non-free \
deb http://archive.debian.org/debian/ stretch-proposed-updates main contrib non-free \
deb http://archive.debian.org/debian-security stretch/updates main contrib non-free" > /etc/apt/sources.list
RUN apt-get update \
&& apt-get install --no-install-recommends -y \
    gosu=1.10-1+b2 \
    phantomjs=2.1.1+dfsg-2 \
    ca-certificates=20200601~deb9u1 \
    python2.7=2.7.13-2+deb9u3 \
    build-essential=12.3 \
    git=1:2.11.0-3+deb9u7 \
&& apt-get clean \
&& rm -rf /var/lib/apt/lists/*
RUN gosu nobody true
RUN update-ca-certificates
RUN npm -g install bower@1.8.14
RUN ln -s /usr/bin/python2.7 /usr/bin/python2

VOLUME /checkouts
VOLUME /deployments

COPY ./build.sh ./environment /

CMD ["bash", "build.sh"]
