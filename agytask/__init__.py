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

__version__ = "0.1.0"

__all__ = [
    "Task",
    "run_tasks",
    "execute_task",
    "run_stream_command",
    "parse_tasks_file",
    "mark_task_as_completed",
    "clean_to_absolute_path",
    "DEFAULT_MODEL",
    "__version__",
]
