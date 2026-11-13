"""
cli.py - Command-line interface (CLI) with PySide6 GUI and live interactive (agy) support.
"""

import sys
import uuid
from pathlib import Path
from typing import Optional

import click

from .models import DEFAULT_MODEL
from .parser import clean_to_absolute_path
from .runner import run_tasks


@click.command(
    name="agytask",
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Automated task runner for executing Antigravity Markdown task pipelines.",
)
@click.option(
    "-p", "--project-dir",
    type=str,
    default=".",
    show_default=True,
    help="Path to the target project directory.",
)
@click.option(
    "-f", "--tasks-file",
    type=str,
    default="TASKS.md",
    show_default=True,
    help="Path to the Markdown tasks file.",
)
@click.option(
    "-s", "--session",
    type=str,
    default=None,
    help="Conversation / Session ID. Generates a new UUID if omitted.",
)
@click.option(
    "-m", "--model",
    type=str,
    default=DEFAULT_MODEL,
    show_default=True,
    help="Model ID to use with agy.",
)
@click.option(
    "--mode",
    type=click.Choice(["accept-edits", "auto", "plan"]),
    default="accept-edits",
    show_default=True,
    help="Agent execution mode.",
)
@click.option(
    "--effort",
    type=str,
    default="from-task",
    show_default=True,
    help="Reasoning effort override (low, medium, high, xhigh, max, or from-task).",
)
@click.option(
    "-i", "--interactive",
    is_flag=True,
    default=False,
    help="Run tasks sequentially inside the live interactive agy TUI.",
)
@click.option(
    "--task-id",
    type=str,
    default=None,
    help="Execute only a specific task by its numeric ID.",
)
@click.option(
    "--gui", "--ui",
    "launch_gui",
    is_flag=True,
    default=False,
    help="Launch the PySide6 desktop GUI.",
)
@click.option(
    "--retries",
    type=int,
    default=2,
    show_default=True,
    help="Number of automatic recovery retries if a task fails.",
)
@click.option(
    "--task-timeout",
    type=float,
    default=20.0,
    show_default=True,
    help="Per-task timeout in minutes (0 to disable).",
)
@click.option(
    "-y", "--yes",
    is_flag=True,
    default=False,
    help="Skip confirmation prompts and start execution immediately.",
)
@click.version_option(
    version="0.3.0",
    prog_name="agytask",
    message="%(prog)s version %(version)s",
)
def main(
    project_dir: str,
    tasks_file: str,
    session: Optional[str],
    model: str,
    mode: str,
    effort: str,
    interactive: bool,
    task_id: Optional[str],
    launch_gui: bool,
    retries: int,
    task_timeout: float,
    yes: bool,
) -> None:
    """Main CLI entry point for agytask."""
    if launch_gui:
        from .ui import launch_ui
        launch_ui()
        return

    resolved_proj = clean_to_absolute_path(project_dir)
    if not resolved_proj.is_dir():
        if not yes and sys.stdin.isatty():
            click.secho(f"[!] Project directory does not exist: {resolved_proj}", fg="yellow")
            while True:
                user_proj = click.prompt("Enter a valid project directory path", type=str, default=".")
                resolved_proj = clean_to_absolute_path(user_proj)
                if resolved_proj.is_dir():
                    break
                click.secho(f"[!] Invalid directory path: {resolved_proj}", fg="red")
        else:
            click.secho(f"[ERROR] Project directory not found: {resolved_proj}", fg="red", err=True)
            sys.exit(1)

    candidate_tasks = Path(tasks_file)
    if candidate_tasks.is_absolute() or candidate_tasks.is_file():
        resolved_tasks = clean_to_absolute_path(candidate_tasks)
    else:
        resolved_tasks = clean_to_absolute_path(resolved_proj / tasks_file)

    if not resolved_tasks.is_file():
        if not yes and sys.stdin.isatty():
            click.secho(f"[!] Tasks file not found: {resolved_tasks}", fg="yellow")
            while True:
                user_file = click.prompt("Enter a valid tasks file path", type=str, default="TASKS.md")
                c_file = Path(user_file)
                if c_file.is_absolute() or c_file.is_file():
                    resolved_tasks = clean_to_absolute_path(c_file)
                else:
                    resolved_tasks = clean_to_absolute_path(resolved_proj / user_file)

                if resolved_tasks.is_file():
                    break
                click.secho(f"[!] File not found: {resolved_tasks}", fg="red")
        else:
            click.secho(f"[ERROR] Tasks file not found: {resolved_tasks}", fg="red", err=True)
            sys.exit(1)

    final_session = session
    if not final_session:
        if not yes and sys.stdin.isatty():
            click.echo("\n--- Session Management ---")
            click.echo("1. Start a New Dedicated Session (Recommended)")
            click.echo("2. Resume Existing Session by Conversation ID")
            choice = click.prompt("Select option", type=click.Choice(["1", "2"]), default="1")
            if choice == "2":
                input_id = click.prompt("Enter Conversation ID to resume", type=str, default="").strip()
                if input_id:
                    final_session = input_id
                else:
                    final_session = f"agy-session-{uuid.uuid4().hex[:10]}"
                    click.secho(f"[!] Empty input. Generated new session ID: {final_session}", fg="yellow")
            else:
                final_session = f"agy-session-{uuid.uuid4().hex[:10]}"
        else:
            final_session = f"agy-session-{uuid.uuid4().hex[:10]}"

    click.secho(f"[*] Bound Session ID: {final_session}", fg="green")

    if interactive:
        from .interactive_worker import run_interactive_pipeline
        exit_code = run_interactive_pipeline(
            project_dir_raw=str(resolved_proj),
            tasks_file_raw=str(resolved_tasks),
            session_id=final_session,
            model=model,
            mode=mode,
            effort=effort,
            task_id=task_id,
            pause_at_end=False,
            task_timeout=max(0.0, task_timeout) * 60.0,
        )
        sys.exit(exit_code)

    click.echo("=" * 70)
    click.secho("                ANTIGRAVITY TASK RUNNER PIPELINE                ", fg="cyan", bold=True)
    click.echo("=" * 70)

    try:
        results = run_tasks(
            project_dir=resolved_proj,
            tasks_file=resolved_tasks,
            session_id=final_session,
            model=model,
            retries=retries,
            auto_confirm=yes,
            interactive=(not yes),
            task_timeout=max(0.0, task_timeout) * 60.0,
        )

        if results.get("status") in ("completed", "empty"):
            sys.exit(0)
        elif results.get("status") == "cancelled":
            sys.exit(130)
        else:
            sys.exit(1)

    except KeyboardInterrupt:
        click.secho("\n[!] Execution stopped safely by user.", fg="yellow")
        sys.exit(130)
    except Exception as exc:
        click.secho(f"\n[ERROR] Unexpected error: {exc}", fg="red", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
