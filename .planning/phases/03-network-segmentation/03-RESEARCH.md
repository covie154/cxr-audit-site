# Phase 3 Research: Network Segmentation

Current Compose has one bridge network, `primer-net`, with Nginx, Django, and FastAPI all attached. Django and FastAPI are not published to host ports, which is good. The next hardening step is named network boundaries that constrain reachability and prepare for PostgreSQL in Phase 5.

Implementation should avoid adding database services now. SQLite volumes remain local to Django; `primer-data` is a forward-compatible boundary and documentation signal until Phase 5.

Verification should use `docker compose config` and service healthcheck review. Full upload-to-analysis runtime smoke testing can be performed when Docker and the LLM endpoint are available.
