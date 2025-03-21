from django.shortcuts import render

from services.models import Massage


def home(request):
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
    return render(request, "main/index.html", context=context)
