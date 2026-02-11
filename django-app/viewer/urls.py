"""
URL configuration for the viewer app.
"""

from django.urls import path
from . import views

app_name = 'viewer'

urlpatterns = [
    path('', views.index, name='index'),
    path('study/<int:accession_no>/', views.study_detail, name='study_detail'),
    path('study/<int:accession_no>/update/', views.study_update, name='study_update'),
    path('study/<int:accession_no>/delete/', views.study_delete, name='study_delete'),
    path('bulk-delete/', views.bulk_delete, name='bulk_delete'),
    path('export/', views.export_csv, name='export_csv'),
]
