#!/usr/bin/env python3

import sass

# download BS5 scss from https://getbootstrap.com/docs/5.2/getting-started/download/

css = sass.compile(filename="base.scss")
with open("web/static/main.css", "w") as fp:
    fp.write(css)
