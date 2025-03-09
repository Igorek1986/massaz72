from django.shortcuts import render

from .models import Massage


def home(request):
    massages = Massage.objects.all().prefetch_related()
    return render(request, "services/index.html", {"massages": massages})
