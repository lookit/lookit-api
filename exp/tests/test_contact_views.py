# TODO: StudyParticipantContactView
# - check can only GET if return user.is_researcher and user.has_study_perms(
#             StudyPermission.CONTACT_STUDY_PARTICIPANTS, study
#         )
# - check context["participants"] has participants for this study but not another one
# - check can post a single message (postpone checks of appropriate recipients & message type)
