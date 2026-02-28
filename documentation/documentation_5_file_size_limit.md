# Security Fix #5: Enforce 10MB File Size Limit in Django

## Summary
The Django application had no explicit upload size limits, which could allow denial-of-service via excessively large file uploads. Additionally, the ground truth upload endpoint stored parsed rows in the session without a row count cap, which could exhaust server memory.

## Changes Made

### Files Modified

1. **django-app/lunit_audit/settings.py**
   - Added `DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024` (10 MB) -- limits the maximum request body size
   - Added `FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024` (10 MB) -- limits the size of files held in memory before spilling to disk

2. **django-app/gt/views.py** (`validate_upload` function)
   - Added `MAX_GT_ROWS = 10000` row count limit
   - Returns HTTP 400 with a descriptive error message when the uploaded file exceeds 10,000 rows

## Rationale
- **DATA_UPLOAD_MAX_MEMORY_SIZE**: Django's default is 2.5 MB, but the existing application works with Excel/CSV files that can be several megabytes. 10 MB is a reasonable upper bound for report files.
- **FILE_UPLOAD_MAX_MEMORY_SIZE**: Ensures large uploads spill to temporary disk storage rather than consuming RAM.
- **MAX_GT_ROWS**: The ground truth upload parses the file and stores all rows in the Django session. Without a cap, a malicious file with millions of rows could exhaust memory. 10,000 rows is well above any realistic audit batch size.

## Reflections
- The FastAPI backend is not directly exposed to the internet (it sits behind Django), so Django-level limits effectively protect both services.
- Nginx could also enforce a `client_max_body_size` directive as a defense-in-depth measure, but that is outside the scope of this fix.
- The 10 MB limit is generous for CSV/Excel report files but prevents egregious abuse. It can be tuned via settings if needed.
