---
status: complete
---
# Editor navigation fix

Use Django-reversed absolute editor base URL for selector navigation, preventing duplicated layout segments. JavaScript regression passed and 14 editor tests passed. Restarted synthetic preview; overview and showcase returned 200 with corrected base. Switched temporary helper to standard ThreadingHTTPServer to prevent idle browser connections blocking requests. Browser automation did not complete.
