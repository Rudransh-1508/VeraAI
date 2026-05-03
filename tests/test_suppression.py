from suppression import SuppressionStore


def test_suppression_keys_and_hostile():
    store = SuppressionStore()
    store.suppress("key_1")
    assert store.is_suppressed("key_1") is True

    store.mark_hostile("m_123", days=1)
    assert store.is_hostile("m_123") is True
