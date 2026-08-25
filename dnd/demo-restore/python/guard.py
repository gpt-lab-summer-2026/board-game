"""Name guard for translated commands.

The implementation lives in the ghost package (`ghost/nlguard.py`) because the
in-game console needs the same check and two copies of a tuned threshold is one
copy too many. This module stays so `from guard import check` keeps working.
"""
import os
import sys

sys.path.append(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PlanarAlly", "ghost")
)

from nlguard import check, unrequested_names  # noqa: F401,E402
