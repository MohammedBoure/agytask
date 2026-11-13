# agytask - Antigravity Task Runner

A Python package, CLI tool, and **PySide6** desktop application for automating sequential Markdown task pipelines with **Antigravity (`agy`)**, featuring live interactive TUI orchestration and real-time model discovery.

---

## Project Structure

- **[`pyproject.toml`](file:///D:/git/agytask/pyproject.toml)**: Package metadata, dependencies (`click`, `PySide6`), and `agytask` console script entry point.
- **[`main.py`](file:///D:/git/agytask/main.py)**: Direct entry point; launches the PySide6 desktop GUI when run without arguments or with `--ui` / `--gui`, and delegates to the CLI otherwise.
- **[`.gitignore`](file:///D:/git/agytask/.gitignore)**: Git ignore rules.
- **[`README.md`](file:///D:/git/agytask/README.md)**: Project overview and usage guide.
- **[`agytask/`](file:///D:/git/agytask/agytask/)**: Core package source directory (see [`agytask/README.md`](file:///D:/git/agytask/agytask/README.md) for per-file details).

---

## Desktop GUI (PySide6)

Launch the desktop interface directly:

```bash
python main.py
```

Or after editable installation:

```bash
agytask --ui
```

### Key Features:
1. **Live Model Discovery (`agy models`)**: Automatically queries `agy models` in the background on startup (with a manual Refresh button) so newly available models appear immediately.
2. **Always-On Automation**: Tool permission skipping (`--dangerously-skip-permissions`) and sequential auto-continue between tasks are always enabled without cluttering the interface.
3. **Session Management**: Auto-discovers recent conversations from `~/.gemini/antigravity-cli/brain` and lets you resume an existing session or start a unified new one.
4. **Live Task Table**: Parses Markdown task files, separates pending and completed tasks, and auto-reloads whenever the tasks file changes on disk.
5. **Interactive & Shell Launchers**: Run all pending tasks, run a single selected task, or open an interactive `agy` shell in the project directory.

---

## Installation (Editable Mode)

```bash
pip install -e .
```

---

## Command-Line Interface (CLI)

```bash
agytask [OPTIONS]
```

| Option | Short | Description | Default |
| :--- | :--- | :--- | :--- |
| `--gui` / `--ui` | | Launch the PySide6 desktop GUI | `False` |
| `--interactive` | `-i` | Run tasks sequentially inside the live `agy` TUI | `False` |
| `--project-dir` | `-p` | Target project directory | `.` |
| `--tasks-file` | `-f` | Path to the Markdown tasks file | `TASKS.md` |
| `--session` | `-s` | Conversation / Session ID | Auto-generated UUID |
| `--model` | `-m` | Model ID for `agy` | `gemini-3.8-flash-medium` |
| `--mode` | | Agent execution mode (`accept-edits`, `auto`, `plan`) | `accept-edits` |
| `--effort` | | Reasoning effort (`from-task`, `low`, `medium`, `high`, `xhigh`, `max`) | `from-task` |
| `--task-id` | | Run only a specific task by numeric ID | `None` |
| `--retries` | | Automatic recovery retries on failure | `2` |
| `--task-timeout` | | Per-task timeout in minutes (`0` to disable) | `20.0` |
| `--yes` | `-y` | Skip confirmation prompts | `False` |
| `--help` | `-h` | Show help message | |
| `--version` | | Show version | |
