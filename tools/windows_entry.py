"""Packaged GUI entry point with an isolated build-verification command."""
import sys


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        from frozen_smoke import RunSmokeTest
        sys.exit(RunSmokeTest(sys.argv[2]))
    from main import Main
    sys.exit(Main())
