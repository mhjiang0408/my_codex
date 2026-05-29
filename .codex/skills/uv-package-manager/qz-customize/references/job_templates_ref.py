"""Reference: Job templates for qzx — run named experiments with overrides.

Usage from qzx CLI:
    qzx job run train-8gpu --set lr=1e-4 --set epochs=3
    qzx job run eval-suite

Templates are Python dicts — code is configuration. Easy to version control,
easy to parameterize with f-strings.
"""

from qz import api, config, avail
from qz.output import json_out, error_exit

# === CUSTOMIZE THESE ===

# Default overrides applied to all templates
DEFAULTS = {
    "pool_type": "h200",
    "image": None,       # None = use config default
    "priority": 10,
}

# Template definitions
TEMPLATES = {
    "train-8gpu": {
        "description": "Single-node 8-GPU training run",
        "nodes": 1,
        "pool_type": "h200",
        "command": """
cd /path/to/project
source .venv/bin/activate
python train.py \\
    --num_gpus 8 \\
    --lr {lr} \\
    --epochs {epochs} \\
    --output_dir /path/to/checkpoints/{name}
""",
        "params": {
            "lr": "3e-4",
            "epochs": "10",
        },
    },
    "train-16gpu": {
        "description": "Two-node 16-GPU training run",
        "nodes": 2,
        "pool_type": "h200",
        "command": """
cd /path/to/project
source .venv/bin/activate
python train.py \\
    --num_gpus 16 \\
    --lr {lr} \\
    --epochs {epochs} \\
    --output_dir /path/to/checkpoints/{name}
""",
        "params": {
            "lr": "1e-4",
            "epochs": "5",
        },
    },
    "eval-suite": {
        "description": "Run evaluation benchmarks",
        "nodes": 1,
        "pool_type": "h200",
        "command": """
cd /path/to/project
source .venv/bin/activate
python eval.py --suite {suite} --model {model}
""",
        "params": {
            "suite": "all",
            "model": "latest",
        },
    },
}

# === IMPLEMENTATION ===


def run_template(template_name: str, *, name: str | None = None,
                 overrides: dict[str, str] | None = None,
                 pool: str | None = None, dry_run: bool = False) -> dict:
    """Run a job from a template with optional parameter overrides."""
    if template_name not in TEMPLATES:
        available = list(TEMPLATES.keys())
        error_exit(f"Unknown template: {template_name}. Available: {available}")

    tmpl = TEMPLATES[template_name]
    params = dict(tmpl.get("params", {}))
    if overrides:
        params.update(overrides)

    job_name = name or f"{template_name}"
    params["name"] = job_name

    command = tmpl["command"].format(**params).strip()
    nodes = tmpl.get("nodes", 1)

    if dry_run:
        return {
            "template": template_name,
            "name": job_name,
            "command": command,
            "nodes": nodes,
            "params": params,
            "dry_run": True,
        }

    pool_type = tmpl.get("pool_type", DEFAULTS["pool_type"])
    if pool:
        pool_cfg = config.get_pool(pool)
    else:
        pool_cfg = avail.select_pool(nodes, type=pool_type)
        if pool_cfg is None:
            error_exit(f"No viable pool (type={pool_type}) for {nodes} nodes")

    payload = api.build_job_payload(
        name=job_name,
        command=command,
        pool=pool_cfg,
        nodes=nodes,
        image=DEFAULTS.get("image"),
        priority=DEFAULTS.get("priority"),
    )
    result = api.create_job(payload)
    data = result.get("data", result)
    return data


def list_templates() -> list[dict]:
    """List available templates."""
    return [
        {
            "name": name,
            "description": tmpl.get("description", ""),
            "nodes": tmpl.get("nodes", 1),
            "params": list(tmpl.get("params", {}).keys()),
        }
        for name, tmpl in TEMPLATES.items()
    ]
