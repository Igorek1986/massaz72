from django.shortcuts import render
from main.models import About, Certificate
from services.models import Massage

from .models import SiteSettings


def index(request):
    # about = About.objects.first()
    child_massages = Massage.objects.filter(
        massage_type=Massage.CHILD, is_archived=False
    )
    adult_massages = Massage.objects.filter(
        massage_type=Massage.ADULT, is_archived=False
    )
    certificates = Certificate.objects.filter(is_archived=False).order_by("order")

    context = {
        # 'about': about,
        "site_settings": SiteSettings.objects.first(),
        "child_massages": child_massages,
        "adult_massages": adult_massages,
        "certificates": certificates,
        # 'banner': MainBanner.objects.first(),
    }
    return render(request, "main/index.html", context=context)


def cookies(request):
    return render(request, "main/cookies.html")
