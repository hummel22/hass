# Contributor Guidelines

This repository keeps HASSEMS (service, UI, and Home Assistant integration) and
its Home Assistant custom component side-by-side. When modifying code inside
this repository:

* Treat `recorded_at` timestamps as diagnostics only. Do not use them for data
  processing, business logic, or metrics – prefer `measured_at` and associated
  cursor metadata.
* Historic processing uses a 10-day cutoff. Values measured more than 10 days
  in the past are considered historic, must be marked with `historic = true`,
  and must carry a `historic_cursor` identifier.
* When adjusting storage schemas, add an explicit migration in
  `services/hassems/storage.py` (the `_apply_migrations` pipeline) instead of
  relying on ad-hoc `ALTER TABLE` statements.
* Ensure Home Assistant entities surface the active `history_cursor` and the
  list of previous cursor events so the integration can reconcile state.
* Update unit tests or add coverage when changing behaviour that affects
  history processing, cursor lifecycles, or API contracts.

When editing frontend components under `services/hassems/frontend`, provide
clear operator-facing messaging that mirrors these expectations.
