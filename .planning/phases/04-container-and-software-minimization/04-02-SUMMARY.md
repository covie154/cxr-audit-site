# 04-02 Summary: Compose Execution Hardening

## Objective

Add practical Compose execution hardening for Django and FastAPI.

## Completed

- Added `security_opt: ["no-new-privileges:true"]` to Django.
- Added `security_opt: ["no-new-privileges:true"]` to FastAPI.
- Added `cap_drop: ["ALL"]` to FastAPI.
- Deferred Django capability dropping because the container still starts as root to repair named-volume ownership before dropping to `appuser`.
- Updated Phase 4 planning documents to record that Django capability drops remain a follow-up after startup ownership is redesigned.

## Verification

- Compose YAML structural check passed:
  - Django has no-new-privileges.
  - Django does not drop all capabilities in this phase.
  - FastAPI has no-new-privileges.
  - FastAPI drops all capabilities.

## Notes

- This is a pragmatic hardening step, not a complete least-privilege proof. Django can be tightened further once volume ownership is handled outside the main container startup path.
