from functools import lru_cache
from django.views.decorators.cache import cache_page

@lru_cache(maxsize=None)
def settings_blob():
    return {}

@cache_page(60 * 15)
def account(request):
    ...
