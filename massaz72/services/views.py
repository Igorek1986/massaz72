from django.shortcuts import render
from django.views.generic import DetailView

from .models import Massage


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
    }
    return render(request, "services/index.html", context=context)


class MassageDetailView(DetailView):
    model = Massage
    context_object_name = "massage"
