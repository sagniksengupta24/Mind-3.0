"""Token accounting: Ollama usage metadata reaches transcript decode + summary.

Mocked only (never a live Ollama call):
1. driver._query_ollama accumulates prompt_eval_count / eval_count into
   totals and per-call decode events.
2. runner.extract_transcript_tuple persists those totals into the
   transcript decode block.
3. runner.evaluate_transcripts aggregates them into the run summary.
"""

from __future__ import annotations

from types import SimpleNamespace

from mind3.benchmarks.runner import BenchmarkRunner, BenchmarkTask, BenchmarkTranscript
from mind3.core.driver import PhaseDriver


class _MockResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _MockClient:
    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = list(payloads)
        self.posts = 0

    def post(self, endpoint: str, json: dict) -> _MockResponse:
        self.posts += 1
        return _MockResponse(self._payloads.pop(0))


def _chat_payload(content: str, prompt_eval: int, eval: int) -> dict:
    return {
        "message": {"role": "assistant", "content": content},
        "prompt_eval_count": prompt_eval,
        "eval_count": eval,
    }


def _bare_driver(client: _MockClient) -> PhaseDriver:
    driver = PhaseDriver.__new__(PhaseDriver)
    driver.ollama_url = "http://127.0.0.1:11434"
    driver.decode_temperature = 0.0
    driver.decode_num_predict = 4096
    driver.decode_num_ctx = 8192
    driver.decode_seed = 43
    driver.model = "qwen2.5-coder:7b"
    driver.generation_format = "text"
    driver._ollama_force_json = False
    driver._ollama_extra_options = None
    driver.client = client
    driver.total_prompt_tokens = 0
    driver.total_completion_tokens = 0
    driver.model_usage_known = False
    driver.model_cost_usd = 0.0
    driver.model_cost_known = False
    driver._decode_events = []
    driver._last_decode = {}
    return driver


def test_query_ollama_accumulates_usage_counts() -> None:
    driver = _bare_driver(_MockClient([
        _chat_payload("module a; endmodule", 120, 45),
        _chat_payload("module b; endmodule", 200, 60),
    ]))
    driver._query_ollama([{"role": "user", "content": "first"}])
    driver._query_ollama([{"role": "user", "content": "second"}])
    assert driver.total_prompt_tokens == 320
    assert driver.total_completion_tokens == 105
    assert driver.total_tokens == 425
    assert driver.model_usage_known is True
    assert len(driver._decode_events) == 2
    assert driver._decode_events[0]["prompt_eval_count"] == 120
    assert driver._decode_events[1]["eval_count"] == 60


def test_query_ollama_without_usage_metadata_stays_unknown() -> None:
    driver = _bare_driver(_MockClient([
        {"message": {"role": "assistant", "content": "module a; endmodule"}},
    ]))
    driver._query_ollama([{"role": "user", "content": "first"}])
    assert driver.model_usage_known is False
    assert driver.total_tokens == 0
    assert driver._decode_events == []


def _task(task_id: str = "counter_04") -> BenchmarkTask:
    return BenchmarkTask(
        task_id=task_id,
        category="counters",
        name="johnson_counter_8b",
        natural_language_spec="8-bit twisted-ring Johnson counter",
        expected_ports=[
            {"name": "clk", "direction": "input", "width": 1},
            {"name": "rst_n", "direction": "input", "width": 1},
            {"name": "q", "direction": "output", "width": 8},
        ],
        expected_properties=["assert property (@(posedge clk) q == q);"],
        functional_requirements=["8-bit counter"],
        verification_requirements=[],
        sva_properties=[
            "assert property (@(posedge clk) q == q);",
            "assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> q == 8'h00);",
        ],
        clock_reset_assumptions="clk rising edge; active-low synchronous rst_n",
        benchmark_origin="unit-test",
    )


def _stub_driver(prompt: int, completion: int, known: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        transcript=[],
        model="qwen2.5-coder:7b",
        provider="ollama",
        max_repairs=3,
        workspace=None,
        transcript_file=None,
        verifier=SimpleNamespace(detected_versions={}),
        sandbox=SimpleNamespace(),
        parser_mode="strict",
        _decode_events=[],
        _parse_attempts=1,
        total_prompt_tokens=prompt,
        total_completion_tokens=completion,
        model_usage_known=known,
        decode_config=lambda: {"temperature": 0.0, "seed": 43, "generation_format": "text"},
    )


def test_transcript_decode_block_carries_token_totals() -> None:
    runner = BenchmarkRunner.__new__(BenchmarkRunner)
    transcript = runner.extract_transcript_tuple(_task(), _stub_driver(320, 105), False)
    assert transcript.decode["prompt_tokens"] == 320
    assert transcript.decode["completion_tokens"] == 105
    assert transcript.decode["total_tokens"] == 425
    assert transcript.decode["model_usage_known"] is True


def test_transcript_decode_block_unknown_usage_is_explicit() -> None:
    runner = BenchmarkRunner.__new__(BenchmarkRunner)
    transcript = runner.extract_transcript_tuple(_task(), _stub_driver(0, 0, known=False), False)
    assert transcript.decode["total_tokens"] == 0
    assert transcript.decode["model_usage_known"] is False


def _transcript_with_tokens(task_id: str, prompt: int, completion: int) -> BenchmarkTranscript:
    runner = BenchmarkRunner.__new__(BenchmarkRunner)
    task = _task(task_id)
    transcript = runner.extract_transcript_tuple(task, _stub_driver(prompt, completion), False)
    transcript.provider = "ollama"
    return transcript


def test_summary_aggregates_token_totals(tmp_path) -> None:
    runner = BenchmarkRunner.__new__(BenchmarkRunner)
    runner.tasks_file = tmp_path / "tasks.jsonl"
    runner.tasks_file.write_text("{}\n", encoding="utf-8")
    transcripts = [
        _transcript_with_tokens("counter_04", 320, 105),
        _transcript_with_tokens("arbiter_02", 200, 60),
    ]
    summary = runner.evaluate_transcripts(transcripts, required_min_tasks=2, diagnostic=True)
    assert summary.total_prompt_tokens == 520
    assert summary.total_completion_tokens == 165
    assert summary.total_tokens == 685
    assert summary.token_usage_known is True


def test_summary_token_unknown_when_any_transcript_unknown(tmp_path) -> None:
    runner = BenchmarkRunner.__new__(BenchmarkRunner)
    runner.tasks_file = tmp_path / "tasks.jsonl"
    runner.tasks_file.write_text("{}\n", encoding="utf-8")
    good = _transcript_with_tokens("counter_04", 320, 105)
    runner2 = BenchmarkRunner.__new__(BenchmarkRunner)
    bad = runner2.extract_transcript_tuple(_task("arbiter_02"), _stub_driver(0, 0, known=False), False)
    bad.provider = "ollama"
    summary = runner.evaluate_transcripts([good, bad], required_min_tasks=2, diagnostic=True)
    assert summary.total_prompt_tokens == 320
    assert summary.token_usage_known is False
