import sys

if sys.version_info < (3, 11):
    print(
        f"five-clis requires Python 3.11 or later. "
        f"You are running Python {sys.version_info.major}.{sys.version_info.minor}.",
        file=sys.stderr,
    )
    sys.exit(1)
