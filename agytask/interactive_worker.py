"""
interactive_worker.py - Sequential task execution inside a live interactive `agy` TUI session.

Launches `agy` in the target conversation without `-i` (which would force a new session),
then runs a background orchestrator thread that injects tasks one by one into the live
console input via `WriteConsoleInputW` (`CONIN$`), monitors `transcript.jsonl` to detect
turn completion, marks each task `[COMPLETED]` in the Markdown file, and automatically
dispatches the next task in the same session.
"""

import os
import re
import sys
import json
import time
import uuid
import shutil
import ctypes
import tempfile
import argparse
import threading
import subprocess
from ctypes import wintypes
from pathlib import Path
from typing import Optional, List

# Ensure package root is on sys.path when executed directly from an external working directory.
_current_dir = Path(__file__).resolve().parent
_repo_root = _current_dir.parent
for _p in (str(_repo_root), str(_current_dir)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from agytask.parser import clean_to_absolute_path, parse_tasks_file, mark_task_as_completed, Task
    from agytask.models import DEFAULT_MODEL, resolve_agy_model_and_effort
except (ImportError, ModuleNotFoundError):
    try:
        from parser import clean_to_absolute_path, parse_tasks_file, mark_task_as_completed, Task
        from models import DEFAULT_MODEL, resolve_agy_model_and_effort
    except (ImportError, ModuleNotFoundError):
        from .parser import clean_to_absolute_path, parse_tasks_file, mark_task_as_completed, Task
        from .models import DEFAULT_MODEL, resolve_agy_model_and_effort


def set_console_title(title: str) -> None:
    """Safely set the Windows console window title."""
    try:
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetConsoleTitleW(title)
    except Exception:
        pass


def get_agy_brain_dir() -> Path:
    """Return the Antigravity CLI brain directory path."""
    return Path.home() / ".gemini" / "antigravity-cli" / "brain"


# ==============================================================================
# Windows Console Input Injection
# ==============================================================================

if sys.platform == "win32":
    KEY_EVENT = 0x0001
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    OPEN_EXISTING = 3

    class CHAR_UNION(ctypes.Union):
        _fields_ = [
            ("UnicodeChar", wintypes.WCHAR),
            ("AsciiChar", ctypes.c_char),
        ]

    class KEY_EVENT_RECORD(ctypes.Structure):
        _fields_ = [
            ("bKeyDown", wintypes.BOOL),
            ("wRepeatCount", wintypes.WORD),
            ("wVirtualKeyCode", wintypes.WORD),
            ("wVirtualScanCode", wintypes.WORD),
            ("uChar", CHAR_UNION),
            ("dwControlKeyState", wintypes.DWORD),
        ]

    class EVENT_UNION(ctypes.Union):
        _fields_ = [("KeyEvent", KEY_EVENT_RECORD)]

    class INPUT_RECORD(ctypes.Structure):
        _fields_ = [
            ("EventType", wintypes.WORD),
            ("Event", EVENT_UNION),
        ]


def is_agy_vim_mode_enabled() -> bool:
    """Check Antigravity CLI settings.json to determine whether Vim editor mode is enabled."""
    settings_path = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
    if not settings_path.is_file():
        return False
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8", errors="replace"))
        editor_mode = str(data.get("editorMode", "")).strip().lower()
        editor = str(data.get("editor", "")).strip().lower()
        return editor_mode.startswith("vim") or editor == "vim"
    except Exception:
        return False


def _make_key_record(ch: str, key_down: bool, vk: int = 0, scan: int = 0) -> "INPUT_RECORD":
    """Create a Windows console key event record."""
    rec = INPUT_RECORD()
    rec.EventType = KEY_EVENT
    rec.Event.KeyEvent.bKeyDown = 1 if key_down else 0
    rec.Event.KeyEvent.wRepeatCount = 1
    rec.Event.KeyEvent.wVirtualKeyCode = vk
    rec.Event.KeyEvent.wVirtualScanCode = scan
    rec.Event.KeyEvent.uChar.UnicodeChar = ch
    rec.Event.KeyEvent.dwControlKeyState = 0
    return rec


def _write_console_records(kernel32, h_conin, records: list) -> int:
    """Write an array of key event records to the CONIN$ handle."""
    arr = (INPUT_RECORD * len(records))(*records)
    written = wintypes.DWORD(0)
    kernel32.WriteConsoleInputW(h_conin, ctypes.byref(arr), len(records), ctypes.byref(written))
    return written.value


def send_console_key_enter() -> bool:
    """
    Send a submit key sequence to the interactive input field:
    - In Vim mode, send Esc to return to NORMAL mode, then press Enter.
    - In standard mode, press Enter directly.
    """
    if sys.platform != "win32":
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        h_conin = kernel32.CreateFileW(
            "CONIN$",
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if h_conin in (-1, 0, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
            return False
        try:
            if is_agy_vim_mode_enabled():
                esc_records = [
                    _make_key_record("\x1b", True, vk=0x1B, scan=0x01),
                    _make_key_record("\x1b", False, vk=0x1B, scan=0x01),
                ]
                _write_console_records(kernel32, h_conin, esc_records)
                time.sleep(0.25)

            enter_records = [
                _make_key_record("\r", True, vk=0x0D, scan=0x1C),
                _make_key_record("\r", False, vk=0x0D, scan=0x1C),
            ]
            count = _write_console_records(kernel32, h_conin, enter_records)
            return count > 0
        finally:
            kernel32.CloseHandle(h_conin)
    except Exception:
        return False


def send_console_text(text: str, press_enter: bool = True) -> bool:
    """
    Inject full text (with Unicode and Vim mode support) directly into the live `agy` input box:
    1. If Vim mode is enabled, send Esc -> 'i' to enter INSERT mode cleanly before typing.
    2. Write text in balanced chunks so the TUI processes every character reliably.
    3. If press_enter is True, exit INSERT mode (Esc) in Vim mode and press Enter to submit.
    """
    if sys.platform != "win32":
        return False

    try:
        kernel32 = ctypes.windll.kernel32
        h_conin = kernel32.CreateFileW(
            "CONIN$",
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if h_conin in (-1, 0, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
            return False

        try:
            vim_mode = is_agy_vim_mode_enabled()

            if vim_mode:
                esc_records = [
                    _make_key_record("\x1b", True, vk=0x1B, scan=0x01),
                    _make_key_record("\x1b", False, vk=0x1B, scan=0x01),
                ]
                _write_console_records(kernel32, h_conin, esc_records)
                time.sleep(0.2)

                i_records = [
                    _make_key_record("i", True, vk=0x49, scan=0x17),
                    _make_key_record("i", False, vk=0x49, scan=0x17),
                ]
                _write_console_records(kernel32, h_conin, i_records)
                time.sleep(0.2)

            chunk_size = 48
            for i in range(0, len(text), chunk_size):
                chunk = text[i : i + chunk_size]
                records = []
                for ch in chunk:
                    records.append(_make_key_record(ch, True, vk=0, scan=0))
                    records.append(_make_key_record(ch, False, vk=0, scan=0))
                _write_console_records(kernel32, h_conin, records)
                time.sleep(0.015)

            if press_enter:
                time.sleep(0.25)
                if vim_mode:
                    esc_records = [
                        _make_key_record("\x1b", True, vk=0x1B, scan=0x01),
                        _make_key_record("\x1b", False, vk=0x1B, scan=0x01),
                    ]
                    _write_console_records(kernel32, h_conin, esc_records)
                    time.sleep(0.25)

                enter_records = [
                    _make_key_record("\r", True, vk=0x0D, scan=0x1C),
                    _make_key_record("\r", False, vk=0x0D, scan=0x1C),
                ]
                _write_console_records(kernel32, h_conin, enter_records)

            return True
        finally:
            kernel32.CloseHandle(h_conin)
    except Exception:
        return False


def build_single_line_task_prompt(task: Task, project_dir: Path, tasks_file_path: Path) -> str:
    """
    Build a single-line prompt for the interactive `agy` input field so embedded newlines
    do not trigger premature submission.
    """
    task_id = task["id"]
    raw_lines = [line.strip() for line in task["content"].splitlines() if line.strip()]
    compact_body = " | ".join(raw_lines)

    prompt = (
        f"[Task #{task_id}] Project Root: {project_dir} | Tasks File: {tasks_file_path} | "
        f"Execute Task #{task_id}: {compact_body} | "
        f"Requirements: 1. Read relevant README.md and docs if referenced. "
        f"2. Apply the requested code modifications cleanly. "
        f"3. Update Task #{task_id} header in {tasks_file_path.name} to [COMPLETED]. "
        f"4. Commit changes with Conventional Commits and provide a concise summary."
    )
    return prompt


# ==============================================================================
# Readiness and Turn Completion Monitoring via Log & transcript.jsonl
# ==============================================================================

def get_transcript_path(conv_id: str) -> Path:
    """Return the path to transcript.jsonl for a given conversation ID."""
    return get_agy_brain_dir() / conv_id / ".system_generated" / "logs" / "transcript.jsonl"


def read_transcript_steps(transcript_path: Path) -> List[dict]:
    """Safely read all JSONL steps from transcript.jsonl."""
    if not transcript_path.is_file():
        return []
    steps: List[dict] = []
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    steps.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return steps


def is_turn_complete(new_steps: List[dict]) -> bool:
    """
    Determine whether the agent has finished the current task turn:
    1. A new USER_INPUT step exists for the submitted task.
    2. No background step with status RUNNING is still pending a SYSTEM_MESSAGE completion.
    3. The final step is a PLANNER_RESPONSE with status DONE, no tool_calls, and non-empty content.
    """
    if not new_steps:
        return False

    last_user_idx = -1
    for i, step in enumerate(new_steps):
        if step.get("type") == "USER_INPUT":
            last_user_idx = i

    if last_user_idx == -1:
        return False

    turn_steps = new_steps[last_user_idx + 1 :]
    if not turn_steps:
        return False

    for i, step in enumerate(turn_steps):
        if step.get("status") == "RUNNING":
            has_completion_msg = any(
                s.get("type") == "SYSTEM_MESSAGE" for s in turn_steps[i + 1 :]
            )
            if not has_completion_msg:
                return False

    last_step = turn_steps[-1]
    if (
        last_step.get("type") == "PLANNER_RESPONSE"
        and last_step.get("status") == "DONE"
        and not last_step.get("tool_calls")
        and bool(str(last_step.get("content", "")).strip())
    ):
        return True

    return False


def detect_active_conversation_from_log(log_file: Path, fallback_conv_id: Optional[str] = None) -> Optional[str]:
    """Extract the active conversation UUID from the `agy` CLI log file."""
    if not log_file.is_file():
        return fallback_conv_id
    try:
        text = log_file.read_text(encoding="utf-8", errors="replace")
        m_fwd = re.findall(r"Forwarding user message to conversation ([0-9a-fA-F-]{36})", text)
        if m_fwd:
            return m_fwd[-1]
        m_created = re.findall(r"Created conversation ([0-9a-fA-F-]{36})", text)
        if m_created:
            return m_created[-1]
        m_resumed = re.findall(r"Resuming conversation ([0-9a-fA-F-]{36})", text)
        if m_resumed:
            return m_resumed[-1]
    except Exception:
        pass
    return fallback_conv_id


def wait_for_agy_ready(log_file: Path, proc: subprocess.Popen, timeout: float = 35.0) -> bool:
    """
    Wait until the interactive `agy` TUI finishes initialization and login/experiments
    so injected text is not lost or reset.
    """
    start = time.time()
    ready_input_seen_at: Optional[float] = None

    while time.time() - start < timeout:
        if proc.poll() is not None:
            return False

        if log_file.is_file():
            try:
                text = log_file.read_text(encoding="utf-8", errors="replace")
                if "Experiments refreshed after login" in text or "Timed out waiting for experiments" in text:
                    time.sleep(1.0)
                    return True
                if "CLI ready for user input" in text:
                    if ready_input_seen_at is None:
                        ready_input_seen_at = time.time()
                    elif time.time() - ready_input_seen_at >= 6.0:
                        return True
            except Exception:
                pass

        time.sleep(0.25)

    return proc.poll() is None


def orchestrate_tasks_in_live_session(
    proc: subprocess.Popen,
    target_tasks: List[Task],
    project_dir: Path,
    tasks_file: Path,
    initial_conv_id: Optional[str],
    log_file: Path,
    auto_next_delay: float = 3.5,
) -> None:
    """
    Background orchestrator thread that injects tasks sequentially into the open `agy`
    session, monitors transcript.jsonl for completion, marks tasks [COMPLETED], and
    automatically dispatches the next task.
    """
    if not wait_for_agy_ready(log_file, proc):
        return

    active_conv_id = detect_active_conversation_from_log(log_file, initial_conv_id)

    for idx, task in enumerate(target_tasks):
        if proc.poll() is not None:
            return

        task_id = task["id"]
        total = len(target_tasks)
        conv_label = active_conv_id or "New-Session"
        set_console_title(
            f"Antigravity Live Runner [Session: {conv_label}] - Running Task #{task_id} ({idx + 1}/{total})"
        )

        baseline_steps_count = 0
        if active_conv_id:
            t_path = get_transcript_path(active_conv_id)
            baseline_steps_count = len(read_transcript_steps(t_path))

        log_size_before = log_file.stat().st_size if log_file.is_file() else 0

        prompt_text = build_single_line_task_prompt(task, project_dir, tasks_file)
        send_console_text(prompt_text, press_enter=True)

        submitted = False
        wait_submit_start = time.time()
        while time.time() - wait_submit_start < 9.0:
            if proc.poll() is not None:
                return
            if log_file.is_file():
                try:
                    with open(log_file, "r", encoding="utf-8", errors="replace") as lf:
                        lf.seek(log_size_before)
                        recent_log = lf.read()
                    m_fwd = re.findall(r"Forwarding user message to conversation ([0-9a-fA-F-]{36})", recent_log)
                    if m_fwd:
                        new_conv = m_fwd[-1]
                        if new_conv != active_conv_id:
                            active_conv_id = new_conv
                            baseline_steps_count = 0
                        submitted = True
                        break
                except Exception:
                    pass

            if active_conv_id:
                curr_steps = read_transcript_steps(get_transcript_path(active_conv_id))
                if any(s.get("type") == "USER_INPUT" for s in curr_steps[baseline_steps_count:]):
                    submitted = True
                    break

            time.sleep(0.3)

        if not submitted and proc.poll() is None:
            send_console_key_enter()
            time.sleep(1.5)
            active_conv_id = detect_active_conversation_from_log(log_file, active_conv_id)

        quiescent_since: Optional[float] = None
        last_file_size = -1

        while proc.poll() is None:
            if not active_conv_id:
                active_conv_id = detect_active_conversation_from_log(log_file, active_conv_id)
                if not active_conv_id:
                    time.sleep(1.0)
                    continue

            t_path = get_transcript_path(active_conv_id)
            if not t_path.is_file():
                time.sleep(1.0)
                continue

            try:
                curr_size = t_path.stat().st_size
            except Exception:
                curr_size = -1

            all_steps = read_transcript_steps(t_path)
            new_steps = all_steps[baseline_steps_count:]

            if is_turn_complete(new_steps):
                if curr_size == last_file_size and curr_size > 0:
                    if quiescent_since is None:
                        quiescent_since = time.time()
                    elif time.time() - quiescent_since >= 4.0:
                        break
                else:
                    last_file_size = curr_size
                    quiescent_since = time.time()
            else:
                quiescent_since = None
                last_file_size = curr_size

            time.sleep(1.0)

        if proc.poll() is not None:
            return

        try:
            mark_task_as_completed(tasks_file, task_id)
        except Exception:
            pass

        if idx < total - 1:
            next_id = target_tasks[idx + 1]["id"]
            for remaining in range(int(auto_next_delay), 0, -1):
                if proc.poll() is not None:
                    return
                set_console_title(
                    f"Antigravity Live Runner [Done #{task_id}] - Sending Task #{next_id} in {remaining}s..."
                )
                time.sleep(1.0)
        else:
            set_console_title(
                f"Antigravity Live Runner [Session: {active_conv_id}] - All tasks completed ({total}/{total})"
            )


def run_interactive_pipeline(
    project_dir_raw: str,
    tasks_file_raw: str,
    session_id: str,
    model: str = DEFAULT_MODEL,
    mode: str = "accept-edits",
    effort: str = "from-task",
    dangerously_skip_permissions: bool = True,
    task_id: Optional[str] = None,
    no_auto_next: bool = False,
    pause_at_end: bool = True,
) -> int:
    """
    Launch `agy` in live interactive mode and orchestrate pending tasks sequentially.
    Permission skipping and auto-continue are always enabled.
    """
    if sys.platform == "win32":
        try:
            os.system("chcp 65001 >nul")
        except Exception:
            pass
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    project_dir = clean_to_absolute_path(project_dir_raw)
    tasks_file = clean_to_absolute_path(tasks_file_raw)

    set_console_title(f"Antigravity Live Runner [Session: {session_id}]")

    print("=" * 78)
    print("             ANTIGRAVITY TASK RUNNER - LIVE INTERACTIVE TUI             ")
    print("=" * 78)
    print(f"Project    : {project_dir}")
    print(f"Tasks File : {tasks_file}")
    print(f"Session    : {session_id}")
    print(f"Model      : {model} | Mode: {mode}")
    print("=" * 78)

    if not project_dir.is_dir():
        print(f"[ERROR] Project directory not found: {project_dir}")
        if pause_at_end:
            input("\nPress Enter to close...")
        return 1

    if not tasks_file.is_file():
        print(f"[ERROR] Tasks file not found: {tasks_file}")
        if pause_at_end:
            input("\nPress Enter to close...")
        return 1

    try:
        all_pending_tasks, _ = parse_tasks_file(tasks_file)
    except Exception as e:
        print(f"[ERROR] Failed to parse tasks file: {e}")
        if pause_at_end:
            input("\nPress Enter to close...")
        return 1

    target_tasks: List[Task] = []
    if task_id:
        found = [t for t in all_pending_tasks if str(t["id"]) == str(task_id)]
        if not found:
            with open(tasks_file, "r", encoding="utf-8") as f:
                content = f.read()
            m = re.search(
                rf"^#\s*{re.escape(str(task_id))}(?:[ \t]+\[[^\]]+\])?(?:\s*:\s*([a-zA-Z]+))?.*?\n(.*?)(?=\n#|\Z)",
                content,
                flags=re.MULTILINE | re.DOTALL,
            )
            if m:
                target_tasks = [
                    {
                        "id": str(task_id),
                        "effort": (m.group(1) or "medium").lower(),
                        "content": m.group(2).strip(),
                    }
                ]
            else:
                print(f"[ERROR] Task #{task_id} was not found in the tasks file.")
                if pause_at_end:
                    input("\nPress Enter to close...")
                return 1
        else:
            target_tasks = found
    else:
        target_tasks = all_pending_tasks

    if not target_tasks:
        print("\n[i] No pending tasks to execute. All tasks are already completed.")
        if pause_at_end:
            input("\nPress Enter to close...")
        return 0

    print(f"\n[+] Queued {len(target_tasks)} task(s) for sequential execution in live agy session:")
    for t in target_tasks:
        print(f"    - Task #{t['id']:<4} | Effort: {t['effort'].upper():<8}")

    first_effort = effort if (effort and effort != "from-task") else target_tasks[0]["effort"]
    resolved_model, resolved_effort_flag = resolve_agy_model_and_effort(model, first_effort)

    clean_session = (session_id or "").strip()
    brain_dir = get_agy_brain_dir()
    session_exists_in_brain = bool(clean_session and (brain_dir / clean_session).is_dir())

    agy_executable = shutil.which("agy") or "agy"
    temp_log_file = Path(tempfile.gettempdir()) / f"agytask_live_{uuid.uuid4().hex[:8]}.log"

    # Note: Do not pass `-i` here because `-i` forces agy to create a new conversation
    # and ignore `--conversation`. Launch directly and inject tasks via CONIN$.
    cmd = [
        agy_executable,
        "--add-dir", str(project_dir),
        "--model", resolved_model,
        "--mode", mode,
        "--log-file", str(temp_log_file),
        "--dangerously-skip-permissions",
    ]

    if session_exists_in_brain:
        cmd.extend(["--conversation", clean_session])
        print(f"[+] Resuming existing session: {clean_session}")
    else:
        print(f"[i] Session ({clean_session}) not found in brain; starting a unified live session.")

    if resolved_effort_flag:
        cmd.extend(["--effort", resolved_effort_flag])

    print(f"[+] Active Model: {resolved_model} | Mode: {mode} | Permissions: Auto-Skip | Auto-Continue: On")
    print("[+] Launching live agy TUI and dispatching tasks automatically...\n")
    time.sleep(0.6)

    try:
        proc = subprocess.Popen(cmd, cwd=str(project_dir))

        orchestrator = threading.Thread(
            target=orchestrate_tasks_in_live_session,
            args=(
                proc,
                target_tasks,
                project_dir,
                tasks_file,
                clean_session if session_exists_in_brain else None,
                temp_log_file,
                3.5,
            ),
            daemon=True,
        )
        orchestrator.start()

        return_code = proc.wait()
        return return_code

    except KeyboardInterrupt:
        print("\n\n[!] Live agy session interrupted by user (Ctrl+C).")
        return 130
    except FileNotFoundError:
        print("\n[ERROR] `agy` executable not found in PATH. Please ensure Antigravity CLI is installed.")
        if pause_at_end:
            input("\nPress Enter to close...")
        return 127
    finally:
        try:
            if temp_log_file.is_file():
                temp_log_file.unlink(missing_ok=True)
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Antigravity Live Interactive Task Runner")
    parser.add_argument("--project-dir", required=True, help="Target project directory path")
    parser.add_argument("--tasks-file", required=True, help="Markdown tasks file path")
    parser.add_argument("--session", required=True, help="Conversation / Session ID")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model ID for agy")
    parser.add_argument("--mode", default="accept-edits", help="Agent execution mode")
    parser.add_argument("--effort", default="from-task", help="Reasoning effort override or from-task")
    parser.add_argument("--task-id", default=None, help="Run only a specific task by ID")

    args = parser.parse_args()

    exit_code = run_interactive_pipeline(
        project_dir_raw=args.project_dir,
        tasks_file_raw=args.tasks_file,
        session_id=args.session,
        model=args.model,
        mode=args.mode,
        effort=args.effort,
        dangerously_skip_permissions=True,
        task_id=args.task_id,
        no_auto_next=False,
        pause_at_end=True,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
