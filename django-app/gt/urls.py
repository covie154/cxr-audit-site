# PRIMER — LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""
URL configuration for the gt (Manual GT) app.
"""

from django.urls import path
from . import views

app_name = 'gt'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/report-count', views.report_count, name='report_count'),
    path('api/download-reports', views.download_reports, name='download_reports'),
    path('api/validate-upload', views.validate_upload, name='validate_upload'),
    path('api/apply-gt', views.apply_gt, name='apply_gt'),
]
