"""One opt-in diagnostic switch shared by runtime modules."""
import sys

DEBUG = "--debug" in sys.argv


def debug_log(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)
