# Security Fix #4: Change Default Ollama URL to Localhost

## Issue

The default Ollama server URL in `cxr-audit-api/class_process_carpl.py` was hardcoded to `http://192.168.1.204:11434/v1`, an internal network IP address. Hardcoding internal infrastructure IPs in source code is a security concern because:

1. It leaks internal network topology to anyone with access to the repository.
2. If the code is deployed to a different environment, it may inadvertently route traffic to an unintended host.
3. It violates the principle of configuration-over-code for environment-specific values.

## Changes Made

### File: `cxr-audit-api/class_process_carpl.py` (line 23)

Changed the default fallback URL from `http://192.168.1.204:11434/v1` to `http://localhost:11434/v1`.

The `OLLAMA_BASE_URL` environment variable override mechanism is preserved, so deployments that need to point to a remote Ollama instance can still do so via configuration.

## Files Affected

- `cxr-audit-api/class_process_carpl.py`

## Reflections

- Using `localhost` as the default is the safest choice: it assumes Ollama runs on the same host (or in a sidecar container), which is the most common dev/test setup.
- Production deployments should set `OLLAMA_BASE_URL` explicitly via environment variables or Docker Compose configuration.
- The internal IP `192.168.1.204` should never have been committed to version control. This is a reminder to use `.env` files or secrets management for environment-specific values.
