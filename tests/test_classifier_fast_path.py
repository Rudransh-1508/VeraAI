import asyncio

from classifier import ReplyClassifier
from llm_client import LLMClient


class DummyLLM(LLMClient):
    async def complete(self, prompt: str, max_tokens: int = 600) -> str:
        return "{}"


def test_classifier_fast_path_yes():
    clf = ReplyClassifier(DummyLLM())
    result = asyncio.run(clf.classify("yes", 1))
    assert result.intent == "EXPLICIT_YES"


def test_classifier_fast_path_auto_reply():
    clf = ReplyClassifier(DummyLLM())
    result = asyncio.run(
        clf.classify("Thank you for contacting our clinic. We will get back to you", 1)
    )
    assert result.intent == "AUTO_REPLY"
