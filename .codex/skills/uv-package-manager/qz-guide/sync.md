# Sync

`qz sync` is a thin wrapper around rsync for transferring files between your local machine and the cluster.

## Usage

```
qz sync [rsync-flags...] SRC... DEST
```

## How it works

- `qz sync` requires rsync to be installed locally and SSH access to the cluster (e.g. via a long-running CPU notebook tunnel). It typically syncs code/logs between your machine and the GPFS storage on the cluster (shared by all containers).
- A bare `:path` in SRC or DEST expands to `remote_host:path` using the `[sync]` config section.
- Prepends default rsync flags: `-rlpt --delete`.
- Output goes directly to stdout/stderr (not JSON). This is the one exception to the JSON output contract.
- Exit code is the rsync exit code.

## Examples

Push local source to cluster:
```bash
qz sync -av src/ :proj/src/
```

Pull results from cluster:
```bash
qz sync -av --exclude='.git/' :proj/results/ ./results/
```

Dry run to see what would change:
```bash
qz sync -av --dry-run local_dir/ :remote_dir/
```

Arbitrary rsync (no colon expansion needed if you specify full paths):
```bash
qz sync -av --dry-run local_dir/ user@host:remote_dir/
```

## Config

```toml
[sync]
remote_host = "qz-cpu"
remote_prefix = "~/project"
```

- `remote_host` is the SSH host alias (must be configured in `~/.ssh/config`).
- `remote_prefix` is prepended to bare `:path` targets if the path is relative.

## Gotchas

- `--delete` is on by default. Files on the destination that do not exist on the source will be removed. Use `--dry-run` first if unsure.
- Trailing slashes on directories matter (standard rsync behavior). `src/` syncs the contents; `src` syncs the directory itself.
