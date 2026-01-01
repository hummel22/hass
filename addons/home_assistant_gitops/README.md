# Home Assistant GitOps

The Home Assistant GitOps Bridge add-on tracks configuration changes in `/config`, exposes an
ingress UI to stage/commit changes, and syncs with GitHub via SSH.

## Feature checklist

- [x] Initialize a Git repository in `/config` and maintain a safe default `.gitignore`.
- [x] Watch YAML configuration files for changes with debounce protection.
- [x] Provide an ingress UI for status, commits, and sync actions.
- [x] Support Git staging, commits, pushes, and fast-forward pulls.
- [x] Generate SSH keys and show the public key for GitHub.
- [x] Provide webhook-triggered pulls and periodic remote checks.
- [x] Merge automation files with BEGIN/END markers for UI compatibility.
- [x] Send Home Assistant persistent notifications for conflicts or deferred pulls.

## Add-on options

| Option | Description | Default |
| --- | --- | --- |
| `remote_url` | SSH URL for the GitHub repository (e.g. `git@github.com:user/ha-config.git`). | `""` |
| `remote_branch` | Remote branch to sync. | `main` |
| `notification_enabled` | Enable persistent notifications. | `true` |
| `webhook_enabled` | Enable the webhook pull endpoint. | `false` |
| `webhook_path` | Path segment for the webhook. | `pull` |
| `poll_interval_minutes` | Periodic remote check interval in minutes. | `15` |
| `merge_automations` | Generate a merged `automations.yaml` file from `automations/`. | `true` |

## Usage

1. Install the add-on and start it.
2. Open the ingress UI from the sidebar.
3. Configure `remote_url` and add the generated SSH public key to GitHub.
4. Use the UI to commit and push changes.
5. Enable the webhook and/or periodic checks if desired.

## Webhook

When `webhook_enabled` is true, POST to `/api/webhook/<webhook_path>` to trigger a pull.

## Automation merge workflow

The add-on can merge `automations/*.yaml` into `automations.yaml` with comment markers. Use
`Sync from markers` in the UI to write changes back into individual files.
