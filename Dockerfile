FROM python:3.8.3-buster

ARG GIT_TAG
ARG GIT_COMMIT
ENV VERSION=${GIT_TAG} \
    GIT_COMMIT=${GIT_COMMIT}

WORKDIR /code
COPY ./ ./

SHELL ["/bin/bash", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && gosu nobody true \
    && update-ca-certificates 

RUN wget https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py -O /tmp/get-poetry.py \
    && cat /tmp/get-poetry.py | python - \
    && source $HOME/.poetry/env \
    && poetry config virtualenvs.create false \
    && poetry install \
    && python /tmp/get-poetry.py --uninstall -y \
    && rm /tmp/get-poetry.py 

CMD ["python", "manage.py", "--help"]
