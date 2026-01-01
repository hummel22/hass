# Home Assistant GitOps

The Home Assistant GitOps Bridge add-on tracks configuration changes in `/config`, exposes an
ingress UI to stage/commit changes, and syncs with GitHub via SSH.


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

## GitOps config file

The add-on writes a GitOps config file into your repository at `/config/.gitops.yaml`.
It mirrors all add-on options so they can be tracked in Git and reviewed in pull requests.
If you edit `/config/.gitops.yaml`, restart the add-on to apply changes.
Commit this file along with the rest of your Home Assistant configuration.

## Manual Git setup

If you already manage `/config` with Git, the add-on will detect the existing repository and will not re-initialize or overwrite it. It will keep using your `.gitignore` and history.

To configure Git manually:

1. Create a GitHub repository (empty, no README or `.gitignore`).
2. From the Home Assistant host, initialize or clone into `/config`:
   - New repo: `cd /config && git init -b main`
   - Existing repo: `cd /config && git clone git@github.com:YOUR_USER/YOUR_REPO.git .`
3. Add a `.gitignore` (start with the add-on template entries): `addons/homeassistant_gitops/rootfs/app/gitignore_example`
4. Commit and push:
   - `git add -A`
   - `git commit -m "Initial Home Assistant configuration"`
   - `git remote add origin git@github.com:YOUR_USER/YOUR_REPO.git`
   - `git push -u origin main`
5. Set the add-on `remote_url` and start using the UI for ongoing commits.

## Webhook

When `webhook_enabled` is true, POST to `/api/webhook/<webhook_path>` to trigger a pull.

## Automation merge workflow

The add-on can merge `automations/*.yaml` into `automations.yaml` with comment markers. Use
`Sync from markers` in the UI to write changes back into individual files.

### Folder convention

Use the split-automation convention Home Assistant already supports:

- Put automation packages in `/config/automations/*.yaml`.
- Each file should contain a list of automations (the same format as `automations.yaml`).
- The add-on manages only the sections wrapped in `# BEGIN automations/...` and `# END ...`.

### Sync behavior

- When files under `automations/` change, the add-on rebuilds the matching marker blocks in
  `automations.yaml` and leaves any non-package content untouched.
- When you edit marker blocks inside `automations.yaml`, use `Sync from markers` to push
  updates back to the package files. Commit both files together.
