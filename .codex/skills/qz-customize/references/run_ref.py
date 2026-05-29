"""Reference: all-in-one run command — sync + job create + wait + tail logs.

Usage from qzx CLI:
    qzx run --name experiment-1 --command "bash train.sh" [--pool h200] [--nodes 2]
    qzx run --name experiment-1 --command "bash train.sh" --sync  # sync first

This combines the typical agent workflow into a single command:
1. (Optional) qz sync push
2. qz job create
3. qz job wait --start
4. qz job logs (tail)
"""

import sys
import time

from qz import api, config, avail
from qz.output import json_out, error_exit

# === CUSTOMIZE THESE ===

# Import your sync module if you have one
# from qzx import sync as qzx_sync


def run(*, name: str, command: str, pool: str | None = None,
        pool_type: str = "h200", nodes: int = 1,
        image: str | None = None, do_sync: bool = False,
        tail_logs: bool = True, wait_timeout: int = 0) -> dict:
    """All-in-one: optionally sync, create job, wait for start, tail logs."""

    # 1. Optional sync
    if do_sync:
        print('{"step": "sync"}', flush=True)
        # qzx_sync.push()  # uncomment when you have sync set up
        print('{"step": "sync_done"}', flush=True)

    # 2. Resolve pool
    if pool:
        pool_cfg = config.get_pool(pool)
    else:
        pool_cfg = avail.select_pool(nodes, type=pool_type)
        if pool_cfg is None:
            error_exit(f"No viable pool (type={pool_type}) for {nodes} nodes")

    # 3. Create job
    payload = api.build_job_payload(
        name=name,
        command=command,
        pool=pool_cfg,
        nodes=nodes,
        image=image,
    )
    result = api.create_job(payload)
    data = result.get("data", result)
    job_id = data.get("job_id", "")
    print(f'{{"step": "created", "job_id": "{job_id}"}}', flush=True)

    if not job_id:
        error_exit("Job creation returned no job_id")

    # 4. Wait for RUNNING
    print('{"step": "waiting"}', flush=True)
    start = time.time()
    while True:
        detail = api.get_job_detail(job_id)
        status = detail.get("data", {}).get("status", "unknown")
        elapsed = int(time.time() - start)

        if status == "job_running":
            print(f'{{"step": "running", "elapsed_s": {elapsed}}}', flush=True)
            break
        if status in {"job_succeeded", "job_failed", "job_stopped"}:
            json_out({"step": "terminal", "status": status, "elapsed_s": elapsed})
            if status == "job_failed":
                sys.exit(2)
            return {"job_id": job_id, "status": status}
        if wait_timeout and elapsed > wait_timeout:
            error_exit(f"Timeout after {elapsed}s, job still {status}")
        time.sleep(30)

    # 5. Tail logs
    if tail_logs:
        time.sleep(10)  # let some output accumulate
        log_result = api.job_logs(job_id, page_size=50)
        logs = log_result.get("data", {}).get("logs", [])
        for entry in logs:
            ts = entry.get("timestamp_str", "")
            msg = entry.get("message", "")
            print(f"[{ts}] {msg}")

    return {"job_id": job_id, "status": "job_running"}
