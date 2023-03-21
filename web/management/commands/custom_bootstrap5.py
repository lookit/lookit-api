import hashlib
import urllib.request
import zipfile
from pathlib import Path

import sass
from django.core.management.base import BaseCommand, CommandError
from django_bootstrap5.core import get_bootstrap_setting


class Command(BaseCommand):
    help = "Convert Bootstrap 5 Sass files to css with custom changes."
    output_css = "web/static/custom_bootstrap5.css"

    def get_css_hash(self):
        m = hashlib.sha256()

        with open(self.output_css) as fp:
            m.update(fp.read().encode("utf-8"))

        return m.hexdigest()

    def handle(self, *args, **kwargs):
        # get currently used version by django-boostrap package
        js_url = get_bootstrap_setting("javascript_url").get("url")
        bs5_version = js_url.split("/")[4].split("@")[1]

        # download BS5 scss from https://getbootstrap.com/docs/5.2/getting-started/download/
        bs5_url = f"https://github.com/twbs/bootstrap/archive/v{bs5_version}.zip"
        bs5_filename = bs5_url.split("/")[-1]

        # the known root directory of the BS5 archive zip file
        zip_root_dir = Path("bootstrap-5.2.0")

        # get the hash of the exisiting compiled css file
        css_hash = self.get_css_hash()

        # when the root directory doesn't exists, download and extract file
        if not zip_root_dir.exists():
            print(f"Downloading bootstrap v{bs5_version}....")
            urllib.request.urlretrieve(bs5_url, bs5_filename)

            print("Unzip bootstrap file...")
            with zipfile.ZipFile(bs5_filename) as zip_ref:
                zip_ref.extractall("./")

            print("Remove downloaded compressed file...")
            Path(bs5_filename).unlink()

            if not zip_root_dir.exists():
                raise CommandError(
                    f'Expected directory "{zip_root_dir}" was not found after unzip.'
                )

        print("Compile sass to css...")
        with open(self.output_css, "w") as fp:
            fp.write(sass.compile(filename="scss/base.scss"))

        if self.get_css_hash() != css_hash:
            raise CommandError("The custom bootstrap 5 css file has been updated.")
        else:
            print("No changes to the custom bootstrap 5 css file.")
