"""Cross-service constants shared across packages."""

from __future__ import annotations

import re

REQUEST_ID_HEADER = "X-Request-ID"
CLIENT_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
