Please refactor canonical/gatus-k8s-operator so the rock entrypoint no longer builds YAML config files inline in `gatus_rock/gatus_wrapper.sh`, and instead uses Jinja templates rendered at runtime.

Repository:
https://github.com/canonical/gatus-k8s-operator

Goal:
- Preserve the exact current behavior and keep existing tests passing.
- Replace the shell heredoc/config-file assembly in `gatus_rock/gatus_wrapper.sh` with a template-based approach.
- There should be one target template per generated config file:
  - `/config/ui.yaml`
  - `/config/storage.yaml`
  - `/config/alerting.yaml`
  - `/config/security.yaml`
  - `/config/announcements.yaml`
  - `/config/endpoints.yaml`

Requirements:
1. Add a templates directory under `gatus_rock/` containing one Jinja template per target config file.
2. Introduce a small runtime renderer (prefer Python) that:
   - reads the same environment variables the current wrapper relies on,
   - renders or removes config files under `/config`,
   - preserves current conditional behavior exactly.
3. Keep `gatus_wrapper.sh` as the rock entrypoint, but make it delegate config rendering instead of building YAML inline.
4. Update `gatus_rock/rockcraft.yaml` so the renderer, templates, and any required runtime dependencies are included in the rock.
5. Add or update unit tests to cover the rendered-output behavior.

Behavior that must remain unchanged:
- `ui.yaml` is always created.
- `storage.yaml` is created only when `POSTGRESQL_DB_CONNECT_STRING` is set; otherwise it is removed.
- `alerting.yaml` is created only when `MATTERMOST_WEBHOOK_URL` is set; otherwise it is removed.
- If `APP_MATTERMOST_INSECURE=true`, include the `client.insecure: true` block in `alerting.yaml`.
- `announcements.yaml` is created only when `APP_ANNOUNCEMENTS` is set; otherwise it is removed.
- `announcements.yaml` must be a raw pass-through of the charm-provided YAML payload.
- `endpoints.yaml` must be a raw pass-through of the charm-provided YAML payload when `APP_ENDPOINTS` is set.
- `endpoints.yaml` should contain the current default Ubuntu.com sample endpoint only when `APP_ENDPOINTS` is not set.
- `security.yaml` should be created only when the full required OIDC env set is present, matching the current script behavior.
- Final generated YAML should be equivalent to the current implementation so existing tests are unaffected.

Important constraints:
- Preserve filenames and file locations exactly.
- Do not alter the charm-side config contract.
- Do not parse and re-serialize `APP_ANNOUNCEMENTS` or `APP_ENDPOINTS`; write them through as raw YAML payloads.
- The only processing relevant to endpoint webhook placeholders should remain the existing charm-side substitution from Juju secrets before `APP_ENDPOINTS` reaches the rock. Do not move secret-resolution logic into the rock.
- Prefer minimal, behavior-preserving changes over cleanup.

Important caution:
- Before changing OIDC-related behavior, verify the env var naming used by `src/charm.py` versus `gatus_wrapper.sh`. There may be a pre-existing mismatch between `APP_OAUTH_*` and `APP_OIDC_*`. If you find one, call it out explicitly and decide whether to preserve it or fix it as a separate intentional change.

Suggested implementation:
- Add `gatus_rock/render_config.py`
- Add `gatus_rock/templates/ui.yaml.j2`
- Add `gatus_rock/templates/storage.yaml.j2`
- Add `gatus_rock/templates/alerting.yaml.j2`
- Add `gatus_rock/templates/security.yaml.j2`
- Add `gatus_rock/templates/announcements.yaml.j2`
- Add `gatus_rock/templates/endpoints.yaml.j2`
- Simplify `gatus_rock/gatus_wrapper.sh` to call the Python renderer and then exec Gatus
- Update `gatus_rock/rockcraft.yaml`
- Add unit tests for representative env combinations and expected file contents

Please:
1. Inspect the current implementation and tests first.
2. Make the changes.
3. Summarize exactly what changed.
4. Call out any assumptions or behavior mismatches you discover, especially around OIDC env vars.

Notifications:
Upon completion, or if any blocker is encountered, send a notification to the following webhook:
https://chat.canonical.com/hooks/xomkrdkhffgm5g6dd8jzktbbyr
