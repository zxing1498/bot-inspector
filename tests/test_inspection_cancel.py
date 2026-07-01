from src.inspection_cancel import (
    is_active,
    is_cancelled,
    mark_active,
    mark_inactive,
    request_cancel,
)


def test_cancel_flow():
    mark_active("demo")
    assert is_active("demo")
    assert not is_cancelled("demo")

    assert request_cancel("demo") is True
    assert is_cancelled("demo")

    mark_inactive("demo")
    assert not is_active("demo")
    assert not is_cancelled("demo")


def test_request_cancel_inactive():
    assert request_cancel("nobody") is False
