"""RouterAgent intent classification tests."""

from rag_llm_services_agents.router_agent import AgentIntent, RouterAgent


def test_router_maps_required_intents() -> None:
    router = RouterAgent()
    examples = {
        "What is retrieval augmented generation?": AgentIntent.ASK,
        "Explain chunk reranking": AgentIntent.EXPLAIN,
        "Give me a deep dive on embeddings": AgentIntent.DEEP_DIVE,
        "Summarize these notes": AgentIntent.SUMMARIZE,
        "Make a quiz about DeepSeek": AgentIntent.QUIZ,
        "Create flashcards for pgvector": AgentIntent.FLASHCARD,
        "Build a learning plan for RAG": AgentIntent.LEARNING_PLAN,
        "Compare vector search versus keyword search": AgentIntent.COMPARE,
        "Make a mock exam": AgentIntent.EXAM,
        "Review my understanding": AgentIntent.REVIEW,
    }

    for message, expected in examples.items():
        route = router.route(message)
        assert route.intent == expected
        assert 0.0 <= route.confidence <= 1.0


def test_router_uses_ask_fallback_for_unclear_intent() -> None:
    route = RouterAgent().route("tell me something useful")

    assert route.intent == AgentIntent.ASK
    assert route.reason == "default ask fallback"
