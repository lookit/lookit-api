FROM python:3.13-slim-bookworm

ARG GIT_TAG
ARG GIT_COMMIT
ARG POETRY_INSTALL_ARG

ENV VERSION=${GIT_TAG} \
    GIT_COMMIT=${GIT_COMMIT} \
    PATH="/root/.local/bin:/code/.venv/bin:${PATH}"

WORKDIR /code
COPY ./ ./
ADD https://astral.sh/uv/install.sh /uv-installer.sh

RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
        gosu=1.14-1+b10 \
        gettext=0.21-12 \
        git=1:2.39.5-0+deb12u2 \
        gcc=4:12.2.0-3 \
        wget=1.21.3-1+deb12u1 \
        libc6-dev=2.36-9+deb12u13 \
    && rm -rf /var/lib/apt/lists/*  

RUN gosu nobody true  
RUN update-ca-certificates  
RUN sh /uv-installer.sh  
RUN rm /uv-installer.sh 
RUN uv sync --frozen --no-dev  
RUN python manage.py compilemessages
