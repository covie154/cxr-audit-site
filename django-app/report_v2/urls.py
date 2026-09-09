from django.urls import path
from . import views

app_name = "report_v2"
urlpatterns = [path("", views.index, name="index")]
