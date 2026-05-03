from composer import _build_conv_id, _is_expired, _strip_urls


def test_build_conv_id_safe():
    conv_id = _build_conv_id("merchant_123", "trigger_456")
    assert conv_id.startswith("conv_")
    assert "merchant" in conv_id


def test_is_expired():
    assert _is_expired("2026-05-01T00:00:00Z", "2026-05-02T00:00:00Z") is True
    assert _is_expired("2026-05-03T00:00:00Z", "2026-05-02T00:00:00Z") is False


def test_strip_urls():
    text = "Check this https://example.com now"
    assert _strip_urls(text) == "Check this now"
