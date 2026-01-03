# Automation ID Spike (PR-00)

This document guides the Home Assistant automation `id` behavior spike. It includes a helper
snapshot script and a results template.

## Goal

Determine how Home Assistant handles automation `id` values in `automations.yaml` when:

- `id` is missing
- `id` equals the `alias` (including spaces/punctuation)
- automations are edited in the UI
- `automation.reload` and/or a full HA restart occurs

## Helper: snapshot script

Location:

```
addons/homeassistant_gitops/rootfs/app/gitops_bridge/spikes/automation_id_spike.py
```

Usage (inside the add-on container):

```
python3 /app/gitops_bridge/spikes/automation_id_spike.py \
  --label before-reload \
  --path automations.yaml \
  --path packages/spike/automation.yaml \
  --path automations/automations.unassigned.yaml
```

The script writes JSON snapshots to:

```
/config/.gitops/spikes/automation-id/
```

Each snapshot includes file contents so we can diff behavior across reloads/restarts.

## Scenario A: Missing `id`

1. Create a module file:

```
/config/packages/spike/automation.yaml
```

Example content:

```yaml
- alias: Spike Missing ID
  trigger: []
  action: []
```

2. Run YAML Modules sync (UI or `POST /api/modules/sync`).
3. Snapshot:
   - `automations.yaml`
   - `packages/spike/automation.yaml`
   - `automations/automations.unassigned.yaml`
4. Call `automation.reload` (UI or service).
5. Snapshot again.
6. Restart Home Assistant.
7. Snapshot again.

## Scenario B: `id == alias`

1. Create a module file entry with punctuation and spaces in the alias:

```yaml
- alias: Spike ID = Alias (Kitchen / 7AM)
  id: Spike ID = Alias (Kitchen / 7AM)
  trigger: []
  action: []
```

2. Run sync, then repeat the same snapshot/reload/restart steps as Scenario A.

## Scenario C: UI edits

1. Take an automation that originated in YAML (from Scenario A or B).
2. Edit it via the UI.
3. Snapshot before and after the UI edit.
4. Note whether the YAML file changes or if edits land elsewhere.

## Results template

### Scenario A results

- Does HA write an `id` back into `automations.yaml`? (yes/no)
- If yes, what is the format? (uuid? slug? alias?)
- Does it happen on reload, restart, or UI edit?

### Scenario B results

- Did HA accept raw alias as `id`? (yes/no)
- Did it normalize/slugify it? (yes/no, describe)
- Did it reject or modify it?

### Scenario C results

- Does the UI edit write back to `automations.yaml`? (yes/no)
- If not, where does it land? (note if stored in `.storage`)

## Decision to feed into PR-01

Based on the results, record:

- Whether alias-based IDs are safe as-is.
- Whether a normalization step is required.
- Whether reconciliation after reload/restart is required, and how to match items safely.

