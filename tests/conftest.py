from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


TYPETREEFLOW_CREDENTIAL_ENV_NAMES = (
    "TYPETREEFLOW_EMAIL",
    "TYPETREEFLOW_API_KEY",
    "TYPETREEFLOW_LPSN_EMAIL",
    "TYPETREEFLOW_LPSN_USERNAME",
    "TYPETREEFLOW_LPSN_PASSWORD",
    "TYPETREEFLOW_WORKSPACE",
)


@pytest.fixture(autouse=True)
def isolate_typetreeflow_credentials_env():
    for name in TYPETREEFLOW_CREDENTIAL_ENV_NAMES:
        os.environ.pop(name, None)
    yield
    for name in TYPETREEFLOW_CREDENTIAL_ENV_NAMES:
        os.environ.pop(name, None)
