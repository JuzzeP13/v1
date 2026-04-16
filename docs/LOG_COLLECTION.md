# Full Log Collection

Use this on the problematic PC when analysis hangs or returns repeated timeout errors.

## How to run

1. Open project folder.
2. Run:

```bat
collect_full_logs.bat
```

3. Reproduce the issue in the UI.
4. Stop the server with `Ctrl+C` in the collector window.

## Files to share

- `logs\full_runtime_YYYYMMDD_HHMMSS.log`
- `logs\full_diagnostics.log`

## What is captured

- Full server stdout/stderr runtime output.
- Structured JSONL events: queue start/stop, state snapshots, per-site analysis steps, Ollama request start/success/timeout/error, lock recovery.
