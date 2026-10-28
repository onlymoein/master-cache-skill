from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import render
from django.views.decorators.cache import cache_page

from .models import Invoice


@login_required
@cache_page(60 * 5)
def dashboard(request):
    org = request.user.organization
    stats = cache.get("dashboard_stats")
    if stats is None:
        stats = Invoice.objects.filter(organization=org).summary()  # ~2 s on large orgs
        cache.set("dashboard_stats", stats, 600)
    return render(request, "dashboard.html", {"stats": stats})
