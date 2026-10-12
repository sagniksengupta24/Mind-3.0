"""Allow ``python -m tools.cdc_checker``."""

from .cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
