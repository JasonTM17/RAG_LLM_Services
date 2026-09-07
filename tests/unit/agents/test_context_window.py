"""Context window manager tests."""

from rag_llm_services_agents.context_window import ContextWindowManager, HistoryMessage


def test_context_window_keeps_recent_messages_within_limits() -> None:
    manager = ContextWindowManager(max_messages=2, max_chars=50)
    history = [
        HistoryMessage("user", "first"),
        HistoryMessage("assistant", "second"),
        HistoryMessage("user", "third"),
    ]

    selected = manager.select(history)

    assert [message.content for message in selected.messages] == ["second", "third"]
    assert selected.omitted_count == 1


def test_context_window_truncates_single_oversized_message_from_the_left() -> None:
    selected = ContextWindowManager(max_messages=4, max_chars=5).select(
        [HistoryMessage("user", "abcdefghij")]
    )

    assert selected.messages[0].content == "fghij"
    assert selected.total_chars == 5
