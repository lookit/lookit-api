from django.test import TestCase

# TODO: ParticipantSignupView
# - can create participant, new user is participant, is not researcher; maybe test password requirements
# TODO: DemographicDataUpdateView
# - can only GET authenticated, can only get/post own, can post update to own
# TODO: ParticipantUpdateView
# - check can update password, can update participant, can only get own data
# - check if invalid data sent (e.g. user with that email already exists), reloads page & no update
# TODO: ChildrenListView
# - check all own children are there, can only see own children
# - check can add child
# - check if invalid data sent, reloads page & does not create child
# TODO: ChildUpdateView
# - check can get but only for own child, check can change name, check cannot change DOB
# TODO: ParticipantEmailPreferencesView
# - check can get but only for own, check can un-check one preference & save
# TODO: StudiesListView
# - check can get unauthenticated, can see 2 studies which are public & active, but not one that is public & inactive
# and not one that is private & active
# TODO: StudiesHistoryView
# - check can see several sessions where consent frame was completed (but consent not marked), not for someone else's
# child, not for consent frame incomplete.
# TODO: StudyDetailView
# - check can see for public or private active study, unauthenticated or authenticated
# - check context[children] has own children only
# TODO: ExperimentAssetsProxyView
# - check have to be authenticated, maybe that's it for now??
# TODO: ExperimentProxyView
# - check have to be authenticated, has to be own child
