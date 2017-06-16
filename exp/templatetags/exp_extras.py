from django import template

register = template.Library()

@register.simple_tag
def query_transform(request, **kwargs):
    updated = request.GET.copy()

    state = kwargs.get('state')
    if state:
        updated['state'] = '' if state == 'all' else state
    if kwargs.get('match'):
        updated['match'] = kwargs.get('match')

    if kwargs.get('sort'):
        sort_value = kwargs.get('sort')
        previous_sort_value = request.GET.get('sort') or ''
        if sort_value in previous_sort_value and '-' not in previous_sort_value:
            sort_value = '-' + sort_value
        updated['sort'] = sort_value
    return updated.urlencode()
