from conversation import ConversationStore, ConvState


def test_conversation_history_and_repetition():
    store = ConversationStore()
    conv = store.get_or_create("conv_1", "m_1", None, "t_1")

    conv.add_turn("vera", "Hello")
    conv.add_turn("merchant", "Hi")
    conv.add_sent_body("Hello")

    history = conv.history_text()
    assert "[VERA]: Hello" in history
    assert "[MERCHANT]: Hi" in history
    assert conv.is_body_repeat("Hello") is True

    store.transition("conv_1", ConvState.ENGAGED)
    assert store.get("conv_1").state == ConvState.ENGAGED
