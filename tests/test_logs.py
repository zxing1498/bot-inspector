from src.probes.logs import query_logs


def test_log_skip_mode():
    result = query_logs({"type": "skip"})
    assert result.ok is True
    assert result.trace_id == "skipped"
