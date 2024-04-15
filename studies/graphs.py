"""Graph facilities for the Analytics study view."""

import pandas
from django_pandas.io import read_frame

pandas.set_option("display.max_columns", None)
pandas.set_option("display.max_rows", None)


def _get_base_responses_dataframe(responses_queryset):
    response_dataframe = read_frame(
        responses_queryset,
        fieldnames=("date_created", "current_ruling", "study__name", "study__id"),
        index_col="uuid",
    )

    return response_dataframe


def get_response_timeseries_data(responses_queryset):
    """This method has one job, and that's to package data for MetricsGraphics.JS.

    Format:
        [
            {
                "timestamp": [UTC timestamp],
                "count_per_study": [The count for each study]
                "count_per_ruling": [the count per ruling]
                "count_per_study_by_ruling: [the count per study and ruling]
            }
        ]

    The idea here is to have the grouped counts easily accessible to javascript, such that the
    series-generating functions only have to filter to get the appropriate dataset rather than computing counts.

    Args:
        responses_queryset: The time series we're going to digest.
        study_names: The names of the studies we want.

    Returns:
        A tuple of JSON-formatted strings.
    """
    # Base dataframe must include data as datetime for proper sorting.
    base_dataframe = _get_base_responses_dataframe(responses_queryset)
    base_dataframe["date_created"] = pandas.to_datetime(base_dataframe["date_created"])

    # Sort, date, and number, then add a date column for binning.
    base_dataframe.sort_values(["date_created"], inplace=True)
    base_dataframe["date_of_response"] = base_dataframe["date_created"].dt.date

    # TODO: Now create the daily binned DF
    responses_per_date = (
        pandas.crosstab(
            index=base_dataframe["date_of_response"],
            columns=[base_dataframe["current_ruling"], base_dataframe["study__id"]],
        )
        .stack()
        .stack()
        .reset_index()
        .rename(columns={0: "num_responses"})
    )

    # Cumulative stats all broken down with groupby
    base_dataframe["total_cumulative_responses"] = range(1, len(base_dataframe) + 1)
    base_dataframe["cumulative_count_per_study"] = base_dataframe.groupby(
        ["study__name"]
    ).cumcount()
    base_dataframe["cumulative_count_per_ruling"] = base_dataframe.groupby(
        ["current_ruling"]
    ).cumcount()
    base_dataframe["cumulative_count_per_study_by_ruling"] = base_dataframe.groupby(
        ["study__name", "current_ruling"]
    ).cumcount()

    return (
        base_dataframe.to_json(orient="records"),
        responses_per_date.to_json(orient="records"),
    )


def get_registration_data(users_queryset):
    """Graphing the children and users?

    Args:
        participant_queryset: the queryset for a bunch of parents.

    Returns:
        A JSON string.
    """
    registration_dataframe = get_users_dataframe(users_queryset)

    registration_dataframe["date_of_registration"] = registration_dataframe[
        "date_created"
    ].dt.date

    return registration_dataframe.to_json(orient="records")


def get_users_dataframe(users_queryset):
    """Get the dataframe for users, cross-tabulated

    Args:
        users_queryset: the queryset for families.

    Returns:
        A dataframe
    """
    users_dataframe = read_frame(
        users_queryset, fieldnames=("date_created",), index_col="uuid"
    )

    users_dataframe["cumulative_count"] = range(1, len(users_dataframe) + 1)

    return users_dataframe
