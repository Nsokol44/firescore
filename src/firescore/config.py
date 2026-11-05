"""FireScore configuration loading.

All scoring constants live in a versioned YAML file (``config/default.yaml``
ships with the package). A county copies that file, edits it, and passes it
with ``--config``; no constant is hard-coded in the scoring code.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "default.yaml"


def _deep_update(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def load_config(path: str | Path | None = None) -> dict:
    """Load the default config, optionally deep-merged with a user file."""
    with open(DEFAULT_CONFIG_PATH) as fh:
        cfg = yaml.safe_load(fh)
    if path is not None:
        with open(path) as fh:
            user_cfg = yaml.safe_load(fh) or {}
        cfg = _deep_update(copy.deepcopy(cfg), user_cfg)
    _validate(cfg)
    return cfg


def _validate(cfg: dict) -> None:
    weights = cfg["weights"]
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"composite weights must sum to 1, got {total}")
    for name, sens in cfg["sensitivity"].items():
        total = sum(sens.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"sensitivity config {name!r} weights sum to {total}")
    sub = cfg["egress"]["subweights"]
    if abs(sum(sub.values()) - 1.0) > 1e-6:
        raise ValueError("egress subweights must sum to 1")
    mix = cfg["fuels"]["vegetation_mix"]
    if abs(sum(mix.values()) - 1.0) > 1e-6:
        raise ValueError("vegetation_mix weights must sum to 1")
