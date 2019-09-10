"""Graph facilities for the Analytics study view."""
from functools import reduce

import altair
import pandas
from django_pandas.io import read_frame


pandas.set_option("display.max_columns", None)
pandas.set_option("display.max_rows", None)


def get_participation_graph(responses_queryset, study_names):
    responses_dataframe = _get_responses_dataframe(responses_queryset)

    studies_with_responses = []
    for name in study_names:
        response_counts_for_study = responses_dataframe[
            responses_dataframe.study__name == name
        ]
        if response_counts_for_study.cumulative_responses.sum() != 0:
            studies_with_responses.append(name)
        else:  # Trim the extraneous values that shouldn't be there.
            responses_dataframe = responses_dataframe[
                responses_dataframe.study__name != name
            ]

    return _get_responses_graph(responses_dataframe, studies_with_responses)


def _get_responses_dataframe(responses_queryset):
    response_dataframe = read_frame(
        responses_queryset,
        fieldnames=("date_created", "current_ruling", "study__name"),
        index_col="uuid",
    )

    # TODO: is there a way to do this in Altair rather than in pandas? That would allow
    #       us to parameterize the creation of the graph a bit more cleanly, I think.
    #       right now, we are resorting to this:
    #       https://stackoverflow.com/questions/40933985/cumulative-count-with-altair
    response_dataframe = (
        pandas.crosstab(
            response_dataframe.date_created,
            columns=[response_dataframe.current_ruling, response_dataframe.study__name],
        )
        .cumsum()
        .stack()  # stack study names
        .stack(dropna=False)  # stack current rulings
        .reset_index()
        .rename(columns={0: "cumulative_responses"})
        .fillna(0)
    )

    return response_dataframe


def _get_responses_graph(response_dataframe, study_names):
    studies_dropdown = altair.binding_select(options=study_names)
    studies_select = altair.selection_single(
        fields=["study__name"],
        bind=studies_dropdown,
        name="Study",
        init={"study__name": study_names[0]},
    )

    base_chart = (
        altair.Chart(response_dataframe)
        .mark_area(interpolate="step-after", line=True)
        .properties(width=200, height=200)
        .encode(
            x=altair.X(
                "date_created:T",
                title="Date of Response",
                axis=altair.Axis(format="%b. %d, %Y", labelAngle=-45),
            ),
            y=altair.Y(f"cumulative_responses:Q", title=f"Response Count"),
            color=altair.Color("current_ruling:N", title="Current Ruling"),
            tooltip="cumulative_responses",
        )
        .facet(column="current_ruling")
    )

    return base_chart.add_selection(studies_select).transform_filter(studies_select)


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
