from datetime import datetime
from os import getenv

from django.shortcuts import render
from django.views.generic import DetailView

from .models import Massage

TELEGRAM_USERNAME = getenv("TELEGRAM_USERNAME")
WHATSAPP_NUMBER = getenv("WHATSAPP_NUMBER")


def home(request):
    # massages = Massage.objects.all().prefetch_related()
    child_massages = Massage.objects.filter(massage_type=Massage.CHILD).order_by(
        "order"
    )
    adult_massages = Massage.objects.filter(massage_type=Massage.ADULT).order_by(
        "order"
    )
    context = {
        "child_massages": child_massages,
        "adult_massages": adult_massages,
        "telegram_username": TELEGRAM_USERNAME,
        "whatsapp_number": WHATSAPP_NUMBER,
        "year": datetime.now().year,
    }
    return render(request, "services/index.html", context=context)


class MassageDetailView(DetailView):
    model = Massage
    context_object_name = "massage"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["telegram_username"] = TELEGRAM_USERNAME
        context["whatsapp_number"] = WHATSAPP_NUMBER
        context["year"] = datetime.now().year
        
        return context
