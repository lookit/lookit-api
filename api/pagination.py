from collections import OrderedDict

from rest_framework.pagination import PageNumberPagination
from rest_framework.utils.urls import replace_query_param
from rest_framework.views import Response


class PageNumberPagination(PageNumberPagination):
    """
    A json-api compatible pagination format
    """

    page_size_query_param = 'page_size'
    max_page_size = 100

    def build_link(self, index):
        if not index:
            return None
        url = self.request and self.request.build_absolute_uri() or ''
        return replace_query_param(url, self.page_query_param, index)

    def get_paginated_response(self, data):
        next = None
        previous = None

        if self.page.has_next():
            next = self.page.next_page_number()
        if self.page.has_previous():
            previous = self.page.previous_page_number()

        return Response({
            'results': data,
            'links': OrderedDict([
                ('first', self.build_link(1)),
                ('last', self.build_link(self.page.paginator.num_pages)),
                ('next', self.build_link(next)),
                ('prev', self.build_link(previous)),
                ('meta', OrderedDict([
                        ('page', self.page.number),
                        ('pages', self.page.paginator.num_pages),
                        ('count', self.page.paginator.count),
                ])),
            ])
        })
