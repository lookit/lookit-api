"""Graph facilities for the Analytics study view."""
import altair
import pandas
from django_pandas.io import read_frame


pandas.set_option("display.max_columns", None)
pandas.set_option("display.max_rows", None)


def get_participation_graph(responses_queryset):
    responses_dataframe = _get_responses_dataframe(responses_queryset)
    return _get_responses_graph(responses_dataframe)


def _get_responses_dataframe(responses_queryset):
    response_dataframe = read_frame(
        responses_queryset,
        fieldnames=("date_created", "completed_consent_frame", "current_ruling"),
        index_col="uuid",
    )

    # TODO: is there a way to do this in Altair rather than in pandas? That would allow
    #       us to parameterize the creation of the graph a bit more cleanly, I think.
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


def get_registration_graph(participant_queryset):
    """Graphing the children and users?

    Args:
        participant_queryset: the queryset for a bunch of children.

    Returns:
        An Altair Graph.
    """
    registration_dataframe = _get_children_dataframe(participant_queryset)
    return _get_family_registration_graph(registration_dataframe)


def _get_children_dataframe(families_queryset):
    """

    Args:
        families_queryset: the queryset for families.

    Returns:
        An Altair Graph.
    """
    read_frame(
        families_queryset,
        fieldnames=("date_created", "completed_consent_frame", "current_ruling"),
        index_col="uuid",
    )


def _get_family_registration_graph(families_dataframe):
    pass
