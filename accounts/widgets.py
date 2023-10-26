import datetime

from django import forms

this_year = datetime.date.today().year


class BirthdayWidget(forms.SelectDateWidget):
    template_name = "widgets/birthday.html"

    def __init__(self, attrs=None, years=None, months=None, empty_label=None):
        if not years:
            years = range(this_year, this_year - 25, -1)

        if attrs is None:
            attrs = {}

        if "class" not in attrs:
            attrs["class"] = "form-select"

        super().__init__(attrs, years, months, empty_label)
