"""
models.py - Live model discovery via `agy models` and model/effort resolution.
"""

import shutil
import subprocess
from typing import List, Optional, Tuple, TypedDict


class ModelInfo(TypedDict):
    """Represents an available Antigravity model returned by `agy models`."""
    id: str
    display_name: str


DEFAULT_MODEL = "gemini-3.8-flash-medium"

# Used only when `agy models` cannot be reached or times out.
FALLBACK_MODELS: List[ModelInfo] = [
    {"id": "gemini-4-hydrogen-medium", "display_name": "Gemini 4 Hydrogen (Medium)"},
    {"id": "gemini-4-hydrogen-high", "display_name": "Gemini 4 Hydrogen (High)"},
    {"id": "gemini-4-hydrogen-xhigh", "display_name": "Gemini 4 Hydrogen (XHigh)"},
    {"id": "gemini-4-hydrogen-low", "display_name": "Gemini 4 Hydrogen (Low)"},
    {"id": "gemini-4-argon-medium", "display_name": "Gemini 4 Argon (Medium)"},
    {"id": "gemini-4-argon-high", "display_name": "Gemini 4 Argon (High)"},
    {"id": "gemini-4-argon-low", "display_name": "Gemini 4 Argon (Low)"},
    {"id": "gemini-pro-orchestrator-g1-pro", "display_name": "Orchestrator (Argon)"},
    {"id": "gemini-3.8-flash-medium", "display_name": "Gemini 3.8 Flash (Medium)"},
    {"id": "gemini-3.8-flash-high", "display_name": "Gemini 3.8 Flash (High)"},
    {"id": "gemini-3.8-flash-low", "display_name": "Gemini 3.8 Flash (Low)"},
    {"id": "claude-opus-5-5-medium", "display_name": "Claude Opus 5.5 (Medium)"},
    {"id": "claude-opus-5-5-high", "display_name": "Claude Opus 5.5 (High)"},
    {"id": "claude-opus-5-5-low", "display_name": "Claude Opus 5.5 (Low)"},
    {"id": "claude-sonnet-5-5-medium", "display_name": "Claude Sonnet 5.5 (Medium)"},
    {"id": "claude-sonnet-5-5-high", "display_name": "Claude Sonnet 5.5 (High)"},
    {"id": "claude-sonnet-5-5-low", "display_name": "Claude Sonnet 5.5 (Low)"},
    {"id": "gpt-oss-120b-medium", "display_name": "GPT-OSS 120B (Medium)"},
]

# Base model families that encode reasoning effort as a suffix (-low / -medium / -high / -xhigh).
TIERED_MODEL_BASES = (
    "gemini-3.8-flash",
    "gemini-4-argon",
    "gemini-4-hydrogen",
    "claude-sonnet-5-5",
    "claude-opus-5-5",
)


def parse_agy_models_output(raw_output: str) -> List[ModelInfo]:
    """
    Parse the tab-separated output of `agy models` into a list of ModelInfo dicts.
    """
    models: List[ModelInfo] = []
    seen_ids = set()

    for line in raw_output.splitlines():
        stripped = line.strip()
        if not stripped or "\t" not in stripped:
            continue
        parts = stripped.split("\t", 1)
        model_id = parts[0].strip()
        display_name = parts[1].strip() if len(parts) > 1 else model_id
        if model_id and model_id not in seen_ids:
            seen_ids.add(model_id)
            models.append({"id": model_id, "display_name": display_name or model_id})

    return models


def fetch_available_models(timeout: float = 12.0) -> Tuple[List[ModelInfo], bool]:
    """
    Query `agy models` for the currently available models.

    Returns:
        Tuple[List[ModelInfo], bool]: (models list, True if fetched live from `agy`, False if fallback).
    """
    agy_executable = shutil.which("agy") or "agy"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        result = subprocess.run(
            [agy_executable, "models"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=creationflags,
        )
        if result.returncode == 0 and result.stdout:
            parsed = parse_agy_models_output(result.stdout)
            if parsed:
                return parsed, True
    except Exception:
        pass

    return list(FALLBACK_MODELS), False


def resolve_agy_model_and_effort(model: str, effort: Optional[str]) -> Tuple[str, Optional[str]]:
    """
    Align the model ID and effort level with `agy` CLI expectations.

    Models returned by `agy models` already encode the tier suffix (e.g.
    `gemini-4-hydrogen-medium`), so explicit suffixed IDs are preserved as-is.
    When a bare base name is provided (e.g. `gemini-3.8-flash`), the effort tier
    is appended automatically.
    """
    clean_model = (model or DEFAULT_MODEL).strip()
    eff = (effort or "medium").strip().lower()
    if eff in ("from-task", ""):
        eff = "medium"

    if eff in ("low", "medium", "high", "xhigh"):
        eff_tier = eff
    elif eff == "max":
        eff_tier = "xhigh" if clean_model.startswith("gemini-4-hydrogen") else "high"
    else:
        eff_tier = "medium"

    for base in TIERED_MODEL_BASES:
        if clean_model == base:
            # Only gemini-4-hydrogen supports -xhigh; clamp others to -high.
            tier = "high" if (eff_tier == "xhigh" and base != "gemini-4-hydrogen") else eff_tier
            return f"{base}-{tier}", None
        if clean_model.startswith(f"{base}-"):
            return clean_model, None

    if clean_model == "gpt-oss-120b":
        return "gpt-oss-120b-medium", None

    return clean_model, None
