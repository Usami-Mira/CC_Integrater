from __future__ import annotations

import uuid
from datetime import datetime


def make_run_id() -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"{ts}-{short}"
