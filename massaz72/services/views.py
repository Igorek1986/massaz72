from django.shortcuts import render
from django.views.generic import DetailView

from .models import Massage


class MassageDetailView(DetailView):
    model = Massage
    context_object_name = "massage"
