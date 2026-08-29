"""Allow ``python -m fpl_ai`` to run the CLI."""

from fpl_ai.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
