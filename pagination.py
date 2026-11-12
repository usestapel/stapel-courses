"""The anchor paginator every list of stapel-courses uses: newest first on ``-id``.

The anchor is declared and emitted as an opaque **string** (the id), so one
envelope shape serves every page component. A malformed anchor reads as no
anchor (the head of the list), never a 500.
"""
from __future__ import annotations

from stapel_core.django.api.pagination import AnchorPagination


class IdAnchorPagination(AnchorPagination):
    page_size = 20
    max_page_size = 100
    anchor_field = "id"
    anchor_type = "string"
    ordering = "-id"

    def paginate_queryset(self, queryset, request, view=None):
        anchor = request.query_params.get(self.anchor_param)
        if anchor is not None and not anchor.isdigit():
            request = _without_anchor(request, self.anchor_param)
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        for key in ("next_anchor", "prev_anchor"):
            if response.data[key] is not None:
                response.data[key] = str(response.data[key])
        return response


class CatalogAnchorPagination(IdAnchorPagination):
    page_size = 24


def _without_anchor(request, param):
    class _Request:
        def __init__(self, inner):
            self._inner = inner
            self.query_params = inner.query_params.copy()
            self.query_params.pop(param, None)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    return _Request(request)
