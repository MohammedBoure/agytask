"""
parser.py - Markdown task parsing, completion status updates, and path normalization.
"""

import os
import re
from pathlib import Path
from typing import List, Tuple, TypedDict, Union


class Task(TypedDict):
    """Data structure representing a parsed task from a Markdown tasks file."""
    id: str
    effort: str
    content: str


def clean_to_absolute_path(raw_input: Union[str, Path]) -> Path:
    """
    Normalize a user-provided path string into a resolved absolute Path.

    Args:
        raw_input: Raw path string or Path object.

    Returns:
        Path: Resolved absolute Path object.
    """
    cleaned = str(raw_input).strip()
    cleaned = re.sub(r"^[:\s]+", "", cleaned)
    cleaned = cleaned.strip("\"'")
    expanded = os.path.expanduser(cleaned)
    return Path(expanded).resolve()


def parse_tasks_file(file_path: Union[str, Path]) -> Tuple[List[Task], List[str]]:
    """
    Parse a Markdown tasks file and separate pending tasks from completed ones.

    Supports header formats such as:
      # 1 [PENDING]: medium
      # 1 [COMPLETED]: medium
      # 1: high
      # 1: medium [COMPLETED]
      # 1

    Args:
        file_path: Path to the Markdown tasks file.

    Returns:
        Tuple[List[Task], List[str]]: (pending tasks, completed task IDs).

    Raises:
        FileNotFoundError: If the tasks file does not exist.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Tasks file not found: {file_path}")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = (
        r"^#\s*(\d+)(?:[ \t]+\[(PENDING|COMPLETED|DONE|مكتملة|منجزة)\])?"
        r"(?:\s*:\s*([a-zA-Z]+))?"
        r"(?:[ \t]+\[(PENDING|COMPLETED|DONE|مكتملة|منجزة)\])?"
    )
    sections = re.split(pattern, content, flags=re.MULTILINE | re.IGNORECASE)

    tasks: List[Task] = []
    skipped_tasks: List[str] = []

    for i in range(1, len(sections), 5):
        task_id = sections[i].strip()
        st1 = sections[i + 1]
        effort_raw = sections[i + 2]
        st2 = sections[i + 3]
        body = sections[i + 4].strip() if (i + 4) < len(sections) else ""

        status = (st1 or st2 or "").upper()
        effort = (effort_raw if effort_raw else "medium").strip().lower()

        if status in ("COMPLETED", "DONE", "مكتملة", "منجزة"):
            skipped_tasks.append(task_id)
            continue

        if body and len(body) > 3:
            tasks.append({
                "id": task_id,
                "effort": effort,
                "content": body,
            })

    return tasks, skipped_tasks


def mark_task_as_completed(file_path: Union[str, Path], task_id: str) -> bool:
    """
    Safely update the task header in the Markdown file to [COMPLETED].

    Args:
        file_path: Path to the tasks file.
        task_id: Numeric ID of the completed task.

    Returns:
        bool: True if the file was updated, False if already marked or not found.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Tasks file not found: {file_path}")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    p_pending = rf"^(#\s*{re.escape(str(task_id))}[^\n]*?)\[(?:PENDING|DONE|منجزة)\]"
    updated_content, count = re.subn(
        p_pending, r"\1[COMPLETED]", content, count=1, flags=re.MULTILINE | re.IGNORECASE
    )

    if count == 0:
        p_append = (
            rf"^(#\s*{re.escape(str(task_id))}(?:\s*:[^\n]*)?)"
            rf"(?!.*\[(?:COMPLETED|DONE|مكتملة|منجزة)\])$"
        )
        updated_content, count = re.subn(
            p_append, r"\1 [COMPLETED]", content, count=1, flags=re.MULTILINE | re.IGNORECASE
        )

    if count > 0:
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(updated_content)
        temp_path.replace(path)
        print(f"[OK] File updated: Task #{task_id} marked as [COMPLETED].")
        return True

    return False
