---
name: qz-setup
description: "Interactive setup wizard for the qz CLI. Use this skill when the user wants to install, configure, or set up qz for the first time, or when they need help with credentials, config.toml, SSH host aliases, or sync configuration. Trigger on phrases like 'set up qz', 'install qz', 'configure qz', 'qz setup', or when a user is clearly starting fresh with the QZ platform."
---

# qz-setup: Interactive Config Wizard

Follow these steps interactively. **Ask the user before proceeding at each step.** Do not assume they have any specific accounts or access. If something fails, help troubleshoot before moving on.

---

## Step 1: Install qz

1. Check if qz is already installed:
   ```bash
   which qz
   ```
2. If **not installed**, install from local source: `uv tool install -e /path/to/qz` (ask for the path)
3. Verify the installation:
   ```bash
   qz --help
   ```
4. If already installed, confirm the version and move on.

---

## Step 2: Set up credentials

1. Explain that qz needs four environment variables for authentication. API and Cookie credentials **may be different accounts**.
2. Ask the user to set up the credentials themselves in their shell profile (`~/.bashrc` or `~/.zshrc`):
   - `QZ_API_USERNAME` — OpenAPI username
   - `QZ_API_PASSWORD` — OpenAPI password
   - `QZ_COOKIE_USERNAME` — CAS/WebUI username
   - `QZ_COOKIE_PASSWORD` — CAS/WebUI password
3. **Do not ask the user to tell you the passwords.** Tell them to set the env vars and source their shell profile.
4. Ask the user to test `qz login` in a separate terminal to verify credentials work.
5. Suggest they also run `qz login -d` in a background terminal or tmux session so the agent can use qz commands without needing to know passwords.

---

## Step 3: Create config.toml

1. Ask the user if they already have a pre-configured pool list (e.g. from another QZ CLI tool's config file).
2. If **yes**, read their existing config and convert it to qz format.
3. If **no**, use the `/qz-browser` skill via a subagent to navigate the QZ platform WebUI and gather the list of available pools/workspaces. Extract workspace_id, logic_compute_group_id, and spec_id for each pool.
4. Present the discovered pools to the user and let them:
   - Remove pools they never use
   - Suggest aliases (short names like `h200`, `cpu`, `4090`)
   - Set preference order (first = highest priority for auto-selection)
5. Help them find the required IDs for each pool:
   - `workspace_id` — the workspace/project UUID
   - `logic_compute_group_id` (aliased as `lcg_id`) — the compute group UUID
   - `spec_id` — the resource spec UUID (determines GPU type/count)

   **How to find these IDs:**
   - From the QZ web UI: go to the job creation form and inspect network requests (look for the POST payload).
   - Or from an existing job: `qz job list --raw` and examine the fields in the output.
   - Or use the `/qz-browser` skill to navigate the platform and extract them.

3. Create `~/.config/qz/config.toml` with their pool definitions. Minimum viable config is **one pool**:
   ```toml
   [[pools]]
   name = "my-pool"
   workspace_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
   lcg_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
   spec_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
   ```

4. If the user has multiple pools, list them in preference order (first = highest priority for auto-selection):
   ```toml
   [[pools]]
   name = "preferred-pool"
   workspace_id = "..."
   lcg_id = "..."
   spec_id = "..."

   [[pools]]
   name = "fallback-pool"
   workspace_id = "..."
   lcg_id = "..."
   spec_id = "..."
   ```

5. Create the config directory if it does not exist:
   ```bash
   mkdir -p ~/.config/qz
   ```

---

## Step 4: Verify

1. Source the shell profile to pick up the new environment variables:
   ```bash
   source ~/.bashrc   # or source ~/.zshrc
   ```
2. Test login (both auth mechanisms):
   ```bash
   qz login
   ```
   Expected output: both token and cookie show as `"ok"`. If either fails, use `qz login -v` to see debug output on stderr and troubleshoot.
3. Test pool config:
   ```bash
   qz pools
   ```
   Should list the pools defined in config.toml.
4. Test availability:
   ```bash
   qz avail
   ```
   Should show current GPU/resource availability for configured pools.

If any step fails, stop and help the user debug before continuing.

---

## Step 5: (Optional) Set up CPU notebook as SSH gateway

Ask the user if they want SSH access to the cluster via a long-running CPU notebook.

If yes:

1. Create a CPU notebook to serve as the gateway:
   ```bash
   qz notebook create --name gateway --image <base-image> --pool cpu
   ```
2. Wait for it to be ready:
   ```bash
   qz notebook wait gateway
   ```
3. Set up an SSH tunnel:
   ```bash
   qz notebook tunnel gateway
   ```
4. This notebook can then serve as the rsync target and SSH gateway for other operations.

---

## Step 6: (Optional) Set up SSH host for sync

Ask the user if they want to use `qz sync` for rsync-based file transfer to the cluster.

If yes:

1. Help them configure an SSH host alias in `~/.ssh/config`:
   ```
   Host qz-cpu
       HostName <cluster-gateway-ip-or-hostname>
       User <username>
       Port <port>
       IdentityFile ~/.ssh/id_rsa
   ```
2. Add a `[sync]` section to `~/.config/qz/config.toml`:
   ```toml
   [sync]
   remote_host = "qz-cpu"
   remote_prefix = "/gpfs/home/<username>/projects"
   ```
3. Test with a dry run:
   ```bash
   qz sync push -av --dry-run
   ```

---

## Step 7: (Optional) Start the auth daemon

Ask the user if they want automatic credential refresh for long-running sessions.

If yes:

1. Start the daemon in the background:
   ```bash
   qz login -d >> ~/.cache/qz/daemon.log 2>&1 &
   ```
2. This keeps both the Bearer token and CAS cookie fresh automatically (refreshes every hour and on demand via socket).
3. Suggest adding it to their shell startup or a systemd user service for persistence.

---

## Notes for the agent

- **Always ask before proceeding** to the next step. The user may want to skip optional steps or may not have all information ready.
- **Never store credentials in git-tracked files.** Only write them to the user's shell profile.
- If the user does not know their pool IDs, offer to use the `/qz-browser` skill to extract them from the web UI.
- If `qz login` fails, common issues are: wrong credentials, network/VPN not connected, or the platform being down. Use `qz login -v` for verbose debug output.
