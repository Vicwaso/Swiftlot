from .models import SiteSettings
from django.conf import settings
def site_context(request):
    return {'site':SiteSettings.current(),'staff_area':request.path.startswith('/staff/'),'current_timezone':settings.TIME_ZONE}
