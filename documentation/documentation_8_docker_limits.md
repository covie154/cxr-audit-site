# Security Fix #8: Add Docker Resource Limits

## Summary
The Docker containers had no CPU, memory, or PID limits, making the system vulnerable to resource exhaustion attacks. A single runaway process or deliberate abuse could consume all host resources and affect other services.

## Changes Made

### Files Modified

1. **docker-compose.yml** -- added resource limits to all three services:

| Service | CPUs | Memory | PIDs |
|---------|------|--------|------|
| nginx   | 1.0  | 512 MB | 100  |
| django  | 2.0  | 2 GB   | 200  |
| api     | 2.0  | 4 GB   | 200  |

### Syntax Used
- `deploy.resources.limits.cpus` and `deploy.resources.limits.memory` for CPU and memory caps
- `pids_limit` at the service level for process count limits

## Rationale
- **nginx**: Lightweight reverse proxy; 512 MB and 1 CPU is generous for its workload.
- **django**: Runs Gunicorn workers (default 3). 2 GB memory accommodates multiple workers plus file processing overhead.
- **api (FastAPI)**: Handles compute-intensive CXR analysis with pandas/numpy. 4 GB memory allows processing large datasets. 2 CPUs match the expected workload.
- **pids_limit**: Prevents fork bomb attacks. 200 is ample for Python application containers; 100 suffices for nginx.

## Reflections
- These limits work with `docker compose up` directly (Compose v2 applies deploy.resources.limits without Swarm mode).
- If the API processes very large batches in the future, the 4 GB memory limit may need adjustment.
- Consider adding `mem_reservation` (soft limits) as a future enhancement to improve scheduling.
