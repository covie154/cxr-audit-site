from django.urls import path
from . import admin_views
from . import views

app_name = "report_v2"
urlpatterns = [path("", views.index, name="index")]

# --- APPEND-ONLY (Task 12): the reserved /report/layout/* editor routes -----------
# Pure append: the existing index pattern above is byte-for-byte untouched, and this project has no
# '/report/<slug>/' catch-all in this urlconf (the legacy report lives in ``report.urls`` mounted at
# '/report-old/' in ``lunit_audit/urls.py``, which is not edited here), so no existing route's
# matching changes. The reserved routes are listed ahead of the parameterised detail pattern so a
# report slug can never shadow an admin endpoint, and every editor route carries a distinct name
# (test_editor_route_before_slug proves the ordering).
urlpatterns += [
    path("layout/", admin_views.editor, name="editor"),
    path("layout/editor/save/", admin_views.editor_save_draft, name="editor_save_draft"),
    path("layout/editor/preview/", admin_views.editor_preview, name="editor_preview"),
    path("layout/editor/publish/", admin_views.editor_publish, name="editor_publish"),
    path("layout/editor/new/", admin_views.editor_new, name="editor_new"),
    # Parameterised report-detail view of the editor, declared LAST inside the reserved block so the
    # literal segments above win first.
    path("layout/editor/<str:def_id>/", admin_views.editor, name="editor_detail"),
]
