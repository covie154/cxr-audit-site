"""
URL configuration for the upload app.
"""

from django.urls import path
from . import views

app_name = 'upload'

urlpatterns = [
    # Main interface
    path('', views.index, name='index'),
    
    # Tasks list
    path('tasks/', views.tasks_list, name='tasks_list'),
    path('api/tasks/<str:task_id>/delete', views.delete_task, name='delete_task'),
    
    # Import historical data
    path('import/', views.import_data, name='import_data'),
    path('api/import/preview', views.import_preview, name='import_preview'),
    path('api/import/confirm', views.import_confirm, name='import_confirm'),
    
    # API server health check
    path('api/check-connection', views.check_api_connection, name='check_api_connection'),
    
    # Pre-check files against database
    path('api/precheck', views.precheck_files, name='precheck_files'),
    
    # Active task check (for resume-on-page-load)
    path('api/active-task', views.get_active_task, name='get_active_task'),
    
    # Proxy endpoints to backend API server
    path('api/analyze-multiple', views.analyze_multiple, name='analyze_multiple'),
    path('api/analyze-auto-sort', views.analyze_auto_sort, name='analyze_auto_sort'),
    path('api/status/<str:task_id>', views.get_status, name='get_status'),
    path('api/results/<str:task_id>', views.get_results, name='get_results'),
    
    # Saved task results from background worker
    path('api/task-results/<str:task_id>', views.get_task_results, name='get_task_results'),
]
