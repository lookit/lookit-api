# TODO: StudyCreateView
# - check user has to be in a lab with perms to create study to get
# TODO: StudyUpdateView
# - check user has to be researcher and have edit perms on study details to get
# - check posting change works
# - check invalid metadata not saved
# - check can't change lab to one you're not in, or at all w/o perms to change lab
# TODO: StudyListView
# - check can get as researcher only
# - check you see exactly studies you have view details perms for
# TODO: StudyDetailView
# - check can get as researcher only
# - [postpone checks of POST which will be refactored]
# TODO: StudyBuildView
# - check cannot GET
# - check can POST only if researcher & user.has_study_perms(StudyPermission.WRITE_STUDY_DETAILS, study)
# - check sets is_building = True
# TODO: StudyPreviewDetailView
# - transfer from test_response_views
