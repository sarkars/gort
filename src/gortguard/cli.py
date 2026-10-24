import argparse

from gortguard import __version__


def main(argv=None):
    parser = argparse.ArgumentParser(prog="gort", description="GORT command line (stub).")
    parser.add_argument("--version", action="version", version=f"gort {__version__}")
    parser.parse_args(argv)
    print("gort: no commands yet. This package is in design.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
