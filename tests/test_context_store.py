from context_store import ContextStore
from models import ContextPush


def test_context_store_push_and_get():
    store = ContextStore()
    push = ContextPush(
        scope="merchant",
        context_id="m_001",
        version=1,
        payload={"merchant_id": "m_001", "name": "Test"},
        delivered_at="2026-05-02T10:00:00Z",
    )

    ack = store.push(push)
    assert ack.accepted is True
    assert store.get("merchant", "m_001") == {"merchant_id": "m_001", "name": "Test"}
    assert store.get_version("merchant", "m_001") == 1


def test_context_store_rejects_stale_version():
    store = ContextStore()
    push_v2 = ContextPush(
        scope="merchant",
        context_id="m_002",
        version=2,
        payload={"merchant_id": "m_002"},
        delivered_at="2026-05-02T10:00:00Z",
    )
    push_v1 = ContextPush(
        scope="merchant",
        context_id="m_002",
        version=1,
        payload={"merchant_id": "m_002", "old": True},
        delivered_at="2026-05-02T10:05:00Z",
    )

    store.push(push_v2)
    ack = store.push(push_v1)
    assert ack.accepted is False
    assert ack.reason == "stale_version"
    assert store.get_version("merchant", "m_002") == 2
