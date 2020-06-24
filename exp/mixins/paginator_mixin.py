from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator


class PaginatorMixin(object):
    """Mixin to add pagination to querysets"""

    paginator_class = Paginator

    def paginated_queryset(self, resource_list, page=1, count=10):
        """ Returns a page object with a subset of the queryset"""
        paginator = self.paginator_class(resource_list, count)
        try:
            results = paginator.page(page)
        except PageNotAnInteger:
            results = paginator.page(1)
        except EmptyPage:
            results = paginator.page(paginator.num_pages)
        return results
