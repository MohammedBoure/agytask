"""
agytask - أداة وحزمة بايثون لأتمتة وتشغيل مهام Antigravity.
"""

from .parser import (
    Task,
    parse_tasks_file,
    mark_task_as_completed,
    clean_to_absolute_path,
)
from .runner import (
    DEFAULT_MODEL,
    run_tasks,
    execute_task,
    run_stream_command,
)
from .ui import (
    launch_ui,
    AntigravityTaskRunnerUI,
)

__version__ = "0.2.1"


def __getattr__(name: str):
    """تحميل الدوال التفاعلية عند الطلب لتفادي تحذيرات الاستيراد الدائري."""
    if name in ("run_interactive_pipeline", "run_interactive_task"):
        from . import interactive_worker
        return getattr(interactive_worker, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Task",
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
    "DEFAULT_MODEL",
    "__version__",
]
