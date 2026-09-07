"""DeepSeek Responses streaming parser tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from rag_llm_services_llm.deepseek import parse_responses_sse


async def _lines(values: list[str]) -> AsyncIterator[str]:
    for value in values:
        yield value


@pytest.mark.asyncio
async def test_responses_stream_parser_handles_semantic_terminal_events() -> None:
    events = [
        event
        async for event in parse_responses_sse(
            _lines(
                [
                    "event: response.output_text.delta",
                    'data: {"delta":"Hello "}',
                    "",
                    "event: response.output_text.delta",
                    'data: {"delta":"[S1]"}',
                    "",
                    "data: [DONE]",
                    "",
                    "event: response.completed",
                    (
                        'data: {"response":{"id":"resp_1","model":"deepseek-v4-flash",'
                        '"status":"completed","output_text":"Hello [S1]",'
                        '"usage":{"input_tokens":5,"output_tokens":3,"total_tokens":8}}}'
                    ),
                    "",
                ]
            )
        )
    ]

    assert [event.event_type for event in events] == [
        "response.output_text.delta",
        "response.output_text.delta",
        "response.completed",
    ]
    assert events[0].delta == "Hello "
    assert events[1].delta == "[S1]"
    assert events[-1].response is not None
    assert events[-1].response.content == "Hello [S1]"


@pytest.mark.asyncio
async def test_responses_stream_parser_surfaces_incomplete_and_failed_events() -> None:
    events = [
        event
        async for event in parse_responses_sse(
            _lines(
                [
                    "event: response.incomplete",
                    'data: {"response":{"error":{"code":"length","message":"max output"}}}',
                    "",
                    "event: response.failed",
                    'data: {"response":{"error":{"code":"server","message":"failed"}}}',
                    "",
                ]
            )
        )
    ]

    assert events[0].event_type == "response.incomplete"
    assert events[0].error_code == "length"
    assert events[1].event_type == "response.failed"
    assert events[1].error_code == "server"
