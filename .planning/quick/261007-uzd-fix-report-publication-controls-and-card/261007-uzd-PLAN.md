# Report publication and card heights

1. Reuse locked definition storage for unpublish; retain editable YAML and immutable history, and advance version numbers after republishing.
2. Redirect successful publish to the report, show pending/errors, expose publication-aware View report and Publish/Unpublish in layout and catalog.
3. Honor configured row heights in shared card rendering and previews; verify with isolated Django and JavaScript regression tests.

4. Add toolbar card creation beside Undo, inserting after the selected row (last row by default) through the existing card form. Sections are existing YAML heading groups.
