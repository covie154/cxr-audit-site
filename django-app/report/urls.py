"""
URL configuration for the report app.
"""

from django.urls import path
from . import views

app_name = 'report'

urlpatterns = [
    path('', views.index, name='index'),
    path('sites/', views.get_sites, name='sites'),
    path('generate/', views.generate_report, name='generate'),
    path('export-csv/', views.export_report_csv, name='export_csv'),
    path('export-fn-csv/', views.export_false_negatives_csv, name='export_fn_csv'),
    path('export-fp-csv/', views.export_false_positives_csv, name='export_fp_csv'),
    path('email-report/', views.email_report, name='email_report'),
    path('download-pdf/', views.download_pdf, name='download_pdf'),
]
