from django.shortcuts import render
from services.models import Massage
from main.models import About, Certificate


def index(request):
    # about = About.objects.first()
    child_massages = Massage.objects.filter(massage_type=Massage.CHILD, is_archived=False)
    adult_massages = Massage.objects.filter(massage_type=Massage.ADULT, is_archived=False)
    certificates = Certificate.objects.filter(is_archived=False).order_by('order')
    
    context = {
        # 'about': about,
        'child_massages': child_massages,
        'adult_massages': adult_massages,
        'certificates': certificates,
    }
    return render(request, "main/index.html", context=context)

def cookies(request):
    return render(request, 'main/cookies.html')
