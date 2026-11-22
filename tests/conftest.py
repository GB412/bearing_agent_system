from __future__ import annotations

import pytest

from bearing_agent_system import DesignBriefService, SQLiteDesignBriefStore


@pytest.fixture
def service(tmp_path):
    return DesignBriefService(SQLiteDesignBriefStore(tmp_path / "brief.sqlite3"))
