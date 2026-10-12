"""C2 decode probe: verify Ollama options plumbing, format modes, and usage accounting.

Sends three tiny generations (json / text / json-schema) with pinned decode
options and prints eval counts + verdicts. No stop sequences are used by the
pipeline; the stop probe documents strip-vs-keep behavior for the record.
"""
import json
import sys
import urllib.request

OLLAMA = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5-coder:7b"


def call(messages, options, fmt=None, stop=None):
    payload = {"model": MODEL, "messages": messages, "stream": False, "options": dict(options)}
    if stop:
        payload["options"]["stop"] = stop
    if fmt is not None:
        payload["format"] = fmt
    req = urllib.request.Request(OLLAMA, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    base_options = {"temperature": 0, "seed": 42, "num_predict": 64, "num_ctx": 8192}
    tiny = [{"role": "user", "content": "Reply with exactly: module ok; endmodule"}]

    print("== probe 1: format=json (legacy default) ==")
    try:
        r = call(tiny, base_options, fmt="json")
        print("content:", repr(r["message"]["content"][:200]))
        print("prompt_eval:", r.get("prompt_eval_count"), "eval:", r.get("eval_count"))
    except Exception as exc:  # noqa: BLE001 - probe must report, not crash
        print("FAILED:", exc)

    print("== probe 2: format=text (Track F) ==")
    try:
        r = call(tiny, base_options)
        print("content:", repr(r["message"]["content"][:200]))
        print("prompt_eval:", r.get("prompt_eval_count"), "eval:", r.get("eval_count"))
    except Exception as exc:
        print("FAILED:", exc)

    print("== probe 3: format=json-schema (Track J) ==")
    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "const": "write_file"},
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["action", "path", "content"],
    }
    try:
        r = call(
            [{"role": "user", "content": "Emit the WriteFileAction for file x.sv with content 'hi'."}],
            base_options,
            fmt=schema,
        )
        content = r["message"]["content"]
        print("content:", repr(content[:300]))
        try:
            obj = json.loads(content)
            print("schema-valid JSON:", set(obj) == {"action", "path", "content"})
        except Exception:
            print("schema-valid JSON: False")
        print("prompt_eval:", r.get("prompt_eval_count"), "eval:", r.get("eval_count"))
    except Exception as exc:
        print("FAILED (schema format unsupported?):", exc)

    print("== probe 4: stop-sequence behavior (documents strip-vs-keep) ==")
    try:
        r = call(tiny, base_options, stop=["endmodule"])
        print("content:", repr(r["message"]["content"][:200]))
        print("stop token kept:", "endmodule" in r["message"]["content"])
    except Exception as exc:
        print("FAILED:", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
