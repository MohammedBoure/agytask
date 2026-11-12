"""
runner.py - Subprocess execution, live output streaming, and automatic task recovery.
"""

import os
import sys
import time
import uuid
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Union, List

from .models import DEFAULT_MODEL, resolve_agy_model_and_effort
from .parser import Task, parse_tasks_file, mark_task_as_completed, clean_to_absolute_path


def run_stream_command(
    cmd: List[str],
    project_dir: Union[str, Path],
    log_file: Union[str, Path],
    append: bool = False,
) -> int:
    """
    Execute a command, stream stdout/stderr live to the console and log file,
    and handle SIGINT / Ctrl+C gracefully.
    """
    mode = "a" if append else "w"
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    process: Optional[subprocess.Popen] = None

    try:
        with open(log_file, mode, encoding="utf-8", errors="replace") as out_file:
            process = subprocess.Popen(
                cmd,
                cwd=str(project_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )

            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    out_file.write(line)
                    out_file.flush()

            process.wait()
            return process.returncode if process.returncode is not None else 0

    except KeyboardInterrupt:
        print("\n\n[!] Interrupt signal received (Ctrl+C). Terminating subprocess safely...")
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        print("[!] Subprocess stopped cleanly.")
        raise


def execute_task(
    task: Task,
    project_dir: Union[str, Path],
    tasks_file_path: Union[str, Path],
    log_dir: Union[str, Path],
    conversation_id: str,
    model_name: str = DEFAULT_MODEL,
    max_retries: int = 2,
    interactive_on_failure: bool = True,
) -> bool:
    """
    Execute a single task via `agy -p` with automatic retry/recovery in the same session.
    """
    task_id = task["id"]
    effort = task["effort"]
    task_body = task["content"]
    log_file = Path(log_dir) / f"task_{task_id}.log"
    resolved_model, _ = resolve_agy_model_and_effort(model_name, effort)

    prompt = f"""
Project Root: {project_dir}
Tasks Source File: {tasks_file_path}

Executing Task #{task_id}:
--------------------------------------------------
{task_body}
--------------------------------------------------

Requirements:
1. Check docs/ and assets/ if referenced in the task description.
2. Apply code modifications directly to target files.
3. Ensure all requirements are satisfied cleanly.
4. Provide a concise summary of completed changes.
"""

    cmd = [
        "agy",
        "-p", prompt,
        "--conversation", conversation_id,
        "--add-dir", str(project_dir),
        "--model", resolved_model,
        "--mode", "accept-edits",
        "--dangerously-skip-permissions",
    ]

    print(f"\n{'-' * 70}")
    print(f"[*] Running Task #{task_id} | Model: [{resolved_model}] | Effort: [{effort.upper()}] | Session: [{conversation_id}]")
    print(f"[*] Streaming output live... (Log: {log_file})")
    print(f"{'-' * 70}\n")

    start_time = time.time()
    return_code = run_stream_command(cmd, project_dir, log_file, append=False)

    retries = 0
    while return_code != 0 and retries < max_retries:
        retries += 1
        print(f"\n[!] Task #{task_id} failed with exit code {return_code}.")
        print(f"[>] Sending recovery prompt to session [{conversation_id}] (Attempt {retries}/{max_retries})...\n")

        recovery_prompt = (
            f"An interruption or error (exit code: {return_code}) occurred while executing Task #{task_id}. "
            f"Review the current code state, fix any issues, and complete the remaining requirements "
            f"without reverting valid changes."
        )
        recovery_model, _ = resolve_agy_model_and_effort(model_name, "high")
        recovery_cmd = [
            "agy",
            "-p", recovery_prompt,
            "--conversation", conversation_id,
            "--add-dir", str(project_dir),
            "--model", recovery_model,
            "--mode", "accept-edits",
            "--dangerously-skip-permissions",
        ]

        return_code = run_stream_command(recovery_cmd, project_dir, log_file, append=True)

    duration = round(time.time() - start_time, 2)

    if return_code == 0:
        print(f"\n[OK] Task #{task_id} completed successfully in {duration}s.\n")
        mark_task_as_completed(tasks_file_path, task_id)
        return True

    print(f"\n[ERROR] Task #{task_id} failed after {max_retries} retries. See log: {log_file}\n")
    if interactive_on_failure:
        choice = input("Continue to the next task anyway? (y/n): ").strip().lower()
        if choice not in ("y", "yes"):
            print("Execution stopped to protect project integrity.")
            return False
    return False


def run_tasks(
    project_dir: Union[str, Path] = ".",
    tasks_file: Union[str, Path] = "TASKS.md",
    session_id: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    retries: int = 2,
    auto_confirm: bool = False,
    interactive: bool = True,
    sleep_between_tasks: float = 2.0,
) -> Dict[str, Any]:
    """
    Main Python API to execute Markdown tasks sequentially.
    """
    resolved_project_dir = clean_to_absolute_path(project_dir)
    if not resolved_project_dir.is_dir():
        raise NotADirectoryError(f"Project directory not found: {resolved_project_dir}")

    task_path_candidate = Path(tasks_file)
    if task_path_candidate.is_absolute() or task_path_candidate.is_file():
        resolved_tasks_file = clean_to_absolute_path(task_path_candidate)
    else:
        resolved_tasks_file = clean_to_absolute_path(resolved_project_dir / tasks_file)

    if not resolved_tasks_file.is_file():
        raise FileNotFoundError(f"Tasks file not found: {resolved_tasks_file}")

    conversation_id = session_id if session_id else f"agy-session-{uuid.uuid4().hex[:10]}"

    log_dir = resolved_project_dir / "tasks_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    tasks, skipped_tasks = parse_tasks_file(resolved_tasks_file)

    if skipped_tasks:
        print(f"\n[i] Skipped previously completed tasks: {', '.join(f'#{tid}' for tid in skipped_tasks)}")

    if not tasks:
        print("[!] No pending tasks to execute. All tasks are completed.")
        return {
            "status": "empty",
            "total": 0,
            "completed": 0,
            "failed": 0,
            "skipped": len(skipped_tasks),
            "session_id": conversation_id,
            "log_dir": str(log_dir),
        }

    print("\n" + "=" * 70)
    print(f"LOADED PENDING TASKS ({len(tasks)} tasks ready):")
    print("=" * 70)
    for t in tasks:
        print(f"  [>] Task #{t['id']:<4} | Effort: {t['effort'].upper():<8}")
    print("=" * 70)

    if not auto_confirm and interactive:
        confirm = input(f"\nStart execution using session [{conversation_id}]? (y/n): ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Execution cancelled by user.")
            return {
                "status": "cancelled",
                "total": len(tasks),
                "completed": 0,
                "failed": 0,
                "skipped": len(skipped_tasks),
                "session_id": conversation_id,
                "log_dir": str(log_dir),
            }

    completed_count = 0
    failed_count = 0

    try:
        for index, task in enumerate(tasks):
            success = execute_task(
                task=task,
                project_dir=resolved_project_dir,
                tasks_file_path=resolved_tasks_file,
                log_dir=log_dir,
                conversation_id=conversation_id,
                model_name=model,
                max_retries=retries,
                interactive_on_failure=interactive,
            )

            if success:
                completed_count += 1
            else:
                failed_count += 1
                if not interactive:
                    print("[!] Task failed in non-interactive mode. Stopping pipeline.")
                    break

            if index < len(tasks) - 1:
                time.sleep(sleep_between_tasks)

    except KeyboardInterrupt:
        print(f"\n[!] Execution interrupted by user after completing {completed_count} of {len(tasks)} tasks.")
        return {
            "status": "interrupted",
            "total": len(tasks),
            "completed": completed_count,
            "failed": failed_count,
            "skipped": len(skipped_tasks),
            "session_id": conversation_id,
            "log_dir": str(log_dir),
        }

    print(f"\nAll tasks finished. Completed: {completed_count}/{len(tasks)}. Logs saved in: {log_dir}")
    return {
        "status": "completed" if failed_count == 0 else "partial",
        "total": len(tasks),
        "completed": completed_count,
        "failed": failed_count,
        "skipped": len(skipped_tasks),
        "session_id": conversation_id,
        "log_dir": str(log_dir),
    }
