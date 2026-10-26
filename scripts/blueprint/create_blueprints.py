"""File interface for TASK-203, reusing the backend core without starting the app."""

from blueprint_tool.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
