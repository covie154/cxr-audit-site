# Plan

Require exact typed delete this report confirmation in UI and admin POST endpoint, preserving CSRF/revision protections. Move catalog Create report below available reports. Per user follow-ups, remove obsolete template-reset box and report-selection toolbar, establish canonical /layout/ catalog and /layout/editor/<report_name>/ routes, and show active report in the editor header. Retain old report-v2 editor endpoints as compatibility aliases. Verify backend rejection, canonical navigation, route-bound saves, and browser confirmation/create/preview/delete flow.
