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

# --- APPEND-ONLY (Task 13): the published report-detail + per-widget data routes ------------------
# Pure append below the Task-12 reserved block; every line above this comment is byte-for-byte the
# existing file. Both new routes carry the ``defid`` converter. The converter regex is deliberately
# narrower than ``validate_definition_id``'s full alphabet: it excludes hyphen, dot, tilde and upper
# case, so a reserved-style or stray slug such as ``some-random-slug`` fails the regex and matches no
# pattern at all -> Resolver404 (which is what ``test_editor_route_before_slug`` pins). ``to_python``
# still delegates to the repository validator: Django's RoutePattern.match catches ANY exception from
# a converter and reports no-match, so an id that passes the regex but fails validation degrades to a
# 404 rather than a 500. The reserved literal ``layout/...`` routes above win for their exact
# segments; there is deliberately no catch-all here (the legacy report stays on /report-old/).
from django.urls.converters import PathConverter, register_converter

from .definitions.repository import validate_definition_id


class _DefIdConverter(PathConverter):
    regex = r"[a-z][a-z0-9_]*"

    def to_python(self, value):
        validate_definition_id(value)
        return value


register_converter(_DefIdConverter, "defid")

urlpatterns += [
    path("<defid:slug>/", views.report_page, name="page"),
    path("<defid:slug>/widget/<defid:widget_id>/data/", views.widget_data, name="widget_data"),
]
