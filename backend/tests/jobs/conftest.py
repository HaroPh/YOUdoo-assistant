# backend/tests/jobs/conftest.py
"""Isolation cho test jobs: LOGS_DIR trỏ tmp_path, JOBS dict snapshot/restore
(job thật đăng ký lúc import không rò giữa các test)."""
import pytest

from jobs import registry


@pytest.fixture(autouse=True)
def _isolate_jobs(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "LOGS_DIR", tmp_path / "jobs")
    saved = dict(registry.JOBS)
    yield
    registry.JOBS.clear()
    registry.JOBS.update(saved)
