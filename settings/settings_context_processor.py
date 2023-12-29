from .models import Settings
from django.views.decorators.cache import cache_page

from context_cache.decorators import cache_for_context

@cache_page(60 * 10 )
def get_settings(request):
    data=Settings.objects.last()
    return{'settings_data':data}