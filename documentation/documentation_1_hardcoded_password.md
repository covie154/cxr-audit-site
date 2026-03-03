# Security Fix #1: Move Hardcoded Excel Password to Environment Variable

## Summary
The Excel decryption password `GE_2024_P@55` was hardcoded in four locations across the codebase. This is a credential-in-source-code vulnerability (CWE-798) that exposes the password to anyone with repository access, including in git history.

## Changes Made

### Files Modified

1. **cxr-audit-api/class_process_carpl.py** (line 153)
   - Changed `passwd` default from `"GE_2024_P@55"` to `None`
   - Added logic to read `XLSX_DECRYPT_PASSWORD` from environment when no password is explicitly provided

2. **cxr-audit-api/combined_server.py** (line 121)
   - Replaced hardcoded `password="GE_2024_P@55"` with `os.environ.get("XLSX_DECRYPT_PASSWORD", "")`

3. **django-app/upload/views.py** (line 560)
   - Replaced hardcoded `XLSX_PASSWORD = 'GE_2024_P@55'` with `os.environ.get("XLSX_DECRYPT_PASSWORD", "")`
   - Added `import os` to the file

4. **django-app/upload/utils/open_protected_xlsx.py** (line 12)
   - Changed `password` default from `"GE_2024_P@55"` to `None`
   - Added logic to read `XLSX_DECRYPT_PASSWORD` from environment when no password is explicitly provided

5. **.env.example**
   - Added `XLSX_DECRYPT_PASSWORD=change-me` entry under a new "Excel Decryption" section

## Environment Variable
- **Name**: `XLSX_DECRYPT_PASSWORD`
- **Required**: Yes, for processing password-protected GE Excel reports
- **Delivery**: Via `.env` file, which is loaded by both `django` and `api` containers through `env_file` in `docker-compose.yml`

## Deployment Note
After deploying this change, the actual password must be set in the `.env` file:
```
XLSX_DECRYPT_PASSWORD=GE_2024_P@55
```

## Reflections
- The password was present in source code as a string literal, meaning it would persist in git history even after removal. Consider rotating the password if the repository has been shared broadly.
- Both Docker services already use `env_file: .env` in docker-compose.yml, so no orchestration changes were needed.
- The fallback default is an empty string rather than the old password, ensuring the system fails safely if the variable is not configured.
