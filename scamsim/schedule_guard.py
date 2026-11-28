"""Quiet windows: times when this project must not do heavy work (ADR 0004).

Two other projects share the Oracle VM and the Databricks Free Edition account (whose daily
compute quota is shared too), and each has a weekly run that must not be slowed down:

| Window (America/Chicago)   | Protects                       |
|----------------------------|--------------------------------|
| Monday 00:00 to 13:00      | Bank Health's weekly run        |
| Wednesday 00:00 to 18:00   | the CECL Lifetime Loss Lab run  |

"Heavy work" means simulation runs, feature builds, training, graph jobs and big downloads.
Anything that starts heavy work asks `is_quiet_window()` first and waits if the answer is yes.
The live demo endpoint is not heavy work: it stays up, inside its memory cap.

Each window includes its start minute and excludes its end minute: Monday 12:59 is quiet,
Monday 13:00 is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

# The windows are written in Chicago wall-clock time, because that is how the other projects'
# schedules are written. Converting to this zone first means daylight saving is handled for us:
# "Monday 13:00" stays 13:00 local time all year, whether that is 18:00 or 19:00 UTC.
CHICAGO = ZoneInfo("America/Chicago")

MONDAY = 0  # datetime.weekday() numbers: Monday = 0 ... Sunday = 6
WEDNESDAY = 2


@dataclass(frozen=True)
class QuietWindow:
    weekday: int
    start: time  # included
    end: time  # excluded
    protects: str


QUIET_WINDOWS: tuple[QuietWindow, ...] = (
    QuietWindow(MONDAY, time(0, 0), time(13, 0), "Bank Health weekly run"),
    QuietWindow(WEDNESDAY, time(0, 0), time(18, 0), "CECL Lifetime Loss Lab run"),
)


def is_quiet_window(dt: datetime) -> bool:
    """True if `dt` falls inside a quiet window, so heavy work must wait.

    `dt` must carry a time zone (for example `datetime.now(UTC)`). A time without one is refused:
    "06:00" on a server set to UTC and on a PC set to Chicago are different moments, and guessing
    wrong would let a heavy job start in the middle of another project's run.
    """
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("is_quiet_window needs a time-zone-aware datetime, e.g. datetime.now(UTC)")
    local = dt.astimezone(CHICAGO)
    wall_clock = local.time().replace(tzinfo=None)
    return any(
        local.weekday() == w.weekday and w.start <= wall_clock < w.end for w in QUIET_WINDOWS
    )
