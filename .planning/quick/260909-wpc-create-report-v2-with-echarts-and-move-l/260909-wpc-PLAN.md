# Report v2 foundation

1. Move the complete legacy report URL include to /report-old/, retaining its namespace.
2. Register report_v2 at /report/ with a login-protected template and locally served Apache ECharts. Provide an honest empty state; metrics and filters will be defined in subsequent work.
3. Update navigation and upload destination. Verify routes, authentication, templates, legacy endpoints, and static assets using synthetic tests.

Execute inline under gsd-quick. No clinical data access or database changes.
