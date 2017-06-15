from django import template

register = template.Library()

@register.simple_tag
def query_transform(request, **kwargs):
    updated = request.GET.copy()
    if kwargs.get('state'):
        updated['state'] = kwargs.get('state')
    if kwargs.get('match'):
        updated['match'] = kwargs.get('match')
    if kwargs.get('sort'):
        updated['sort'] = kwargs.get('sort')
    return updated.urlencode()
