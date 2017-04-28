from django.views import generic

from studies.models import Study


class StudyCreateView(generic.CreateView):
    model = Study


class StudyListView(generic.ListView):
    model = Study

    # TODO Pagination

class StudyDetailView(generic.DetailView):
    '''
    StudyDetailView shows information about a study.
    '''
    template_name = 'studies/study_detail.html'
    model = Study
