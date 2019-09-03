"""Graph facilities for the Analytics study view."""
import altair
import pandas
from django_pandas.io import read_frame


def graph_responses(responses_queryset):
    responses_dataframe = _get_responses_dataframe(responses_queryset)
    return _get_responses_graph(responses_dataframe)


def _get_responses_dataframe(responses_queryset):
    response_dataframe = read_frame(
        responses_queryset,
        fieldnames=("date_created", "completed_consent_frame", "current_ruling"),
        index_col="uuid",
    )
    cumulative_responses_dataframe = (
        pandas.crosstab(
            response_dataframe.date_created, columns=response_dataframe.current_ruling
        )
        .cumsum()
        .stack()
        .reset_index()
        .rename(columns={0: "cumulative_responses"})
    )

    return cumulative_responses_dataframe


def _get_responses_graph(responses_dataframe):
    return (
        altair.Chart(responses_dataframe)
        .mark_area(interpolate="step-after", line=True)
        .encode(
            x=altair.X(
                "date_created:T",
                title="Date of Response",
                axis=altair.Axis(format="%b. %d, %Y", labelAngle=-45),
            ),
            y=altair.Y("cumulative_responses:Q", title="Response Count"),
            color=altair.Color("current_ruling:N", title="Current Ruling"),
            tooltip="cumulative_responses",
        )
        .properties(width=400, height=400)
    )
