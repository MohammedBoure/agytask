# `agytask/` Package Directory

This directory contains the core source code for the `agytask` package and CLI/GUI runner.

## Files & Responsibilities

1. **`__init__.py`**:
   - Public Python API exports (`run_tasks`, `execute_task`, `run_stream_command`, `run_interactive_pipeline`, `launch_ui`, `AntigravityTaskRunnerUI`, `parse_tasks_file`, `mark_task_as_completed`, `clean_to_absolute_path`, `fetch_available_models`, `resolve_agy_model_and_effort`, `DEFAULT_MODEL`, `__version__`).

2. **`models.py`**:
   - Live model discovery by invoking `agy models` (`fetch_available_models`, `parse_agy_models_output`) with a built-in fallback list (`FALLBACK_MODELS`).
   - Model/effort resolution (`resolve_agy_model_and_effort`) to align model IDs and reasoning tiers with `agy` CLI.

3. **`icons.py`**:
   - Crisp vector SVG icon renderer (`get_icon`, `get_pixmap`) using `PySide6.QtSvg.QSvgRenderer`.

4. **`ui.py`**:
   - Modern PySide6 desktop GUI (`AntigravityTaskRunnerUI`, `launch_ui`) for selecting the project directory, Markdown tasks file, live models, agent mode, effort, and session ID.
   - Displays a live-polling task table (`QTableWidget`) and activity log (`QPlainTextEdit`), with auto-approve permissions (`--dangerously-skip-permissions`) and auto-continue always enabled.

5. **`interactive_worker.py`**:
   - Live interactive orchestrator that launches `agy` in the target conversation, injects tasks sequentially via `WriteConsoleInputW` (`CONIN$`), monitors `transcript.jsonl` for turn completion, marks tasks `[COMPLETED]`, and automatically dispatches the next task.

6. **`parser.py`**:
   - Path normalization (`clean_to_absolute_path`), Markdown task parsing (`parse_tasks_file`), and atomic completion marking (`mark_task_as_completed`).

7. **`runner.py`**:
   - Non-interactive subprocess streaming (`run_stream_command`), automatic retry/recovery (`execute_task`), and sequential pipeline execution (`run_tasks`).

8. **`cli.py`**:
   - Click-based command-line interface (`agytask`) supporting `--ui` / `--gui`, `-i` / `--interactive`, `--task-id`, `--model`, `--mode`, `--effort`, `--session`, and `-y` / `--yes`.
