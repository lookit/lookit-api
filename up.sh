#! /bin/bash

echo "Is your virtual environment up and running? [(Y|y)|(N/n)]"

read answer

if [[ "$answer" =~ ^(Y|y|YES|yes|Yes|)$ ]]; then
  echo "Please activate your virtual environment so that pip installs dependencies in the correct location. (source {env name}/bin/activate, or activate.fish, .zsh, etc...)"
  exit 1
fi
  
# Ensure that GraphViz is installed correctly.
sudo pip install pygraphviz --install-option="--include-path=/usr/include/graphviz" --install-option="--library-path=/usr/lib/graphviz/"

pip install --user -r requirements/dev.txt

psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'lookit'" | grep -q 1 || psql -U postgres -c "CREATE DATABASE lookit"

python manage.py migrate
