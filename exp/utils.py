import csv
import io

RESPONSE_PAGE_SIZE = 500  # for pagination of responses when processing for download


def flatten_dict(d):
    """Flatten a dictionary where values may be other dictionaries

	The dictionary returned will have keys created by joining higher- to lower-level keys with dots. e.g. if the original dict d is
	{'a': {'x':3, 'y':4}, 'b':{'z':5}, 'c':{} }
	then the dict returned will be
	{'a.x':3, 'a.y': 4, 'b.z':5}

	Note that if a key is mapped to an empty dict or list, NO key in the returned dict is created for this key.

	Also note that values may be overwritten if there is conflicting dot notation in the input dictionary, e.g. {'a': {'x': 3}, 'a.x': 4}.
	"""
    # http://codereview.stackexchange.com/a/21035

    def expand(key, value):
        if isinstance(value, list):
            value = {i: v for (i, v) in enumerate(value)}
        if isinstance(value, dict):
            return [
                (str(key) + "." + str(k), v) for k, v in flatten_dict(value).items()
            ]
        else:
            return [(key, value)]

    items = [item for k, v in d.items() for item in expand(k, v)]

    return dict(items)


def csv_dict_output_and_writer(header_list):
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        quoting=csv.QUOTE_NONNUMERIC,
        fieldnames=header_list,
        restval="",
        extrasaction="ignore",
    )
    writer.writeheader()
    return output, writer


def study_name_for_files(study_name):
    return "".join([c if c.isalnum() else "-" for c in study_name])


def round_age(age_in_days):
    if age_in_days <= 360:
        return round(age_in_days / 10) * 10
    else:
        return round(age_in_days / 30) * 30


def round_ages_from_birthdays(child_birthdays, date_created):
    return [
        round_age((date_created.date() - birthdate).days)
        if birthdate and type(birthdate) == type(date_created.date())
        else None
        for birthdate in child_birthdays
    ]
