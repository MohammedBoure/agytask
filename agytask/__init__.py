"""
agytask - Antigravity Task Runner CLI, Desktop GUI, and Python API.
"""

from .parser import (
    Task,
    parse_tasks_file,
    mark_task_as_completed,
    clean_to_absolute_path,
)
from .models import (
    DEFAULT_MODEL,
    ModelInfo,
    fetch_available_models,
    resolve_agy_model_and_effort,
)
from .runner import (
    run_tasks,
    execute_task,
    run_stream_command,
)
from .ui import (
    launch_ui,
    AntigravityTaskRunnerUI,
)

__version__ = "0.3.0"


def __getattr__(name: str):
    """Lazily load interactive worker functions to avoid circular imports."""
    if name in ("run_interactive_pipeline", "run_interactive_task"):
        from . import interactive_worker
        return getattr(interactive_worker, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Task",
    "ModelInfo",
    "run_tasks",
    "execute_task",
    "run_stream_command",
    "run_interactive_pipeline",
    "run_interactive_task",
    "launch_ui",
    "AntigravityTaskRunnerUI",
    "parse_tasks_file",
    "mark_task_as_completed",
    "clean_to_absolute_path",
    "fetch_available_models",
    "resolve_agy_model_and_effort",
    "DEFAULT_MODEL",
    "__version__",
]
