FROM lookit

SHELL ["/bin/bash", "-c"]

RUN source "$HOME/.poetry/env" \
    && poetry install 
