"""Admin report catalog and editor routes."""
from django.urls import path
from . import admin_views

app_name = "report_editor"
urlpatterns = [
    path("", admin_views.editor, name="editor"),
    path("actions/save/", admin_views.editor_save_draft, name="editor_save_draft"),
    path("actions/preview/", admin_views.editor_preview, name="editor_preview"),
    path("actions/publish/", admin_views.editor_publish, name="editor_publish"),
    path("actions/new/", admin_views.editor_new, name="editor_new"),
    path("actions/delete/", admin_views.editor_delete, name="editor_delete"),
    path("editor/<str:def_id>/", admin_views.editor, name="editor_detail"),
]
