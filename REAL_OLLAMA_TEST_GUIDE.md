# Adding a Real-Ollama Test to `tests/test_api.py`

A short, practical guide for the one gap your test suite doesn't cover: proving that
`generate_answer` in `app/llm.py` actually talks to a **real, running Ollama server**
and parses a **real** response — not a mocked one.

---

## Should you add it? My verdict: yes

You said it yourself — you're pushing this to GitHub. That changes the calculus:

- **The risk the test adds (failing on machines without Ollama) is neutralized by
  `@pytest.mark.skipif`.** On your machine with Ollama running, it runs and proves the
  whole pipeline. On GitHub, a teammate's laptop, or a CI runner with no Ollama, pytest
  simply *skips* it (shown as `s`, which is **not** a failure). It can never turn your CI
  red over an environmental issue.
- **The value it adds is real proof.** `test_ask_uses_mocked_answer` proves the `/ask`
  wiring is correct, but the fake generator never touches `app/llm.py`'s real
  `requests.post(...)`. This test is the only thing that proves the request shape, the
  `stream: false` chat call, and the `response.json()["message"]["content"]` parsing
  still work against the actual Ollama API.
- **The danger without it:** a future refactor of `llm.py` (changing the endpoint, the
  payload, or the response parsing) could pass **all** 6 of your current tests and still
  be broken in real use. That's the gap this closes.

The "skip it" arguments are fair — the assertion is loose and LLM output can flake — but
those are weaknesses of *one test*, not a reason to ship a suite that never exercises its
hardest real dependency. It's ~12 lines. Add it.

## What exactly the test does

1. Checks whether anything is listening on `localhost:11434` (Ollama's default port)
   using a raw socket connection with a 1-second timeout — **no HTTP request**.
2. If **no** server is listening, `@pytest.mark.skipif` skips the test at **collection
   time** (before any test runs). Pytest reports it as `s`, never `F`.
3. If **yes**, it runs the real flow: upload `data/samples/ask_sample.docx` → `POST /ask`
   → real chunk search → real call to Ollama → asserts a 200 response and that the answer
   loosely references the document.

## Prerequisites (do this once, on your machine)

1. **Ollama installed and running.** On Windows that's the Ollama app (tray icon) or
   `ollama serve` in a terminal.
2. **The model pulled.** `app/llm.py` uses `llama3.2:3b`:

   ```powershell
   ollama pull llama3.2:3b
   ```

   The socket check only proves *a server is listening* — it cannot tell whether the
   model is downloaded. If the model is missing, `generate_answer` returns the string
   `"Unable to generate an answer: ..."` and the test fails on the keyword assertion.

3. **Sanity-check the chat API directly** (proves server + model before you touch pytest):

   ```powershell
   Invoke-RestMethod -Uri "http://localhost:11434/api/chat" -Method Post -ContentType "application/json" -Body '{\"model\":\"llama3.2:3b\",\"messages\":[{\"role\":\"user\",\"content\":\"Say hi\"}],\"stream\":false}'
   ```

   Expect a JSON object with a `.message.content`.

## The code to add to `tests/test_api.py`

Three pieces: an `import socket` line, a module-level helper, and the test itself. The
helper and the `@pytest.mark.skipif` must sit at **module level** (not inside a function),
because pytest evaluates the skip condition when it *collects* the file — before any test
runs.

Add `import socket` next to the existing imports at the top:

```python
import socket
```

Add this module-level helper (right after the `isolated_client` fixture is fine):

```python
def _ollama_reachable() -> bool:
    try:
        with socket.create_connection(("localhost", 11434), timeout=1):
            return True
    except OSError:
        return False
```

Then the test itself (add it after `test_ask_uses_mocked_answer`):

```python
@pytest.mark.skipif(
    not _ollama_reachable(), reason="Ollama not running on localhost:11434"
)
def test_ask_with_real_ollama(isolated_client):
    with open("data/samples/ask_sample.docx", "rb") as f:
        isolated_client.post(
            "/upload",
            files={
                "file": (
                    "ask_sample.docx",
                    f,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

    response = isolated_client.post("/ask", json={"question": "What was the revenue?"})
    assert response.status_code == 200

    answer = response.json()["answer"].lower()
    # Loose check on purpose: LLM output is non-deterministic, so an exact string
    # match would be flaky. We only require the answer to reference the document.
    assert "revenue" in answer or "85 million" in answer
```

## Running it and reading the output

From the project root (`c:\Users\Thomas\financial-ai`), with your venv active:

```powershell
venv\Scripts\python -m pytest tests\test_api.py -v
```

(`pytest tests\test_api.py -v` also works if pytest is already on your PATH.)

Two possible results for the new test:

| Situation                                     | Output                                             | Meaning                                     |
| --------------------------------------------- | -------------------------------------------------- | ------------------------------------------- |
| Ollama running + model pulled                 | `test_ask_with_real_ollama PASSED`                 | Real HTTP path works end-to-end.            |
| Ollama not installed / not running            | `test_ask_with_real_ollama SKIPPED` → shown as `s` | Correct behavior — skipped, not failed.     |

To **prove the skip works**: stop Ollama, re-run, and you should see `s` instead of a
failure. Restart Ollama and it should pass again.

## What happens when you push to GitHub

Right now: **nothing special** — on any machine without Ollama the test is skipped, so the
repo stays green everywhere. That's the whole point of `skipif`.

When you later wire up GitHub Actions (or any shared CI), the same logic protects you:
Windows/Linux runners don't have Ollama installed by default, `_ollama_reachable()`
returns `False`, and the test is skipped. **No CI setup needed.**

If you ever want CI to *actually run* the test instead of skipping it, you'd install
Ollama in the workflow — that downloads a real model (~2 GB) and makes the job slower and
flakier for marginal benefit:

```yaml
# OPTIONAL — only if you truly want CI to hit a real Ollama (not recommended yet)
      - name: Install Ollama
        run: |
          curl -fsSL https://ollama.com/install.sh | sh
          ollama pull llama3.2:3b
      - name: Run tests
        run: |
          ollama serve &
          pytest tests -v
```

Recommendation: keep `skipif`, skip the install step. The local run is the real proof;
CI's job is to catch *code* regressions, which your 6 mocked tests already do.

## Caveats / flakiness (know what you're signing up for)

1. **This test is slower than the rest.** It loads sentence-transformers for the
   embeddings (several seconds) plus a real model call (10–180 s depending on your
   machine). Expect `pytest` to take a minute+ when Ollama is on.
2. **The assertion can occasionally flake.** LLM output is non-deterministic. "The answer
   mentions revenue / 85 million" is a soft guarantee; an odd generation could fail it
   even when everything works. Re-run before debugging — that's the nature of real-LLM
   tests.
3. **Port open ≠ model present.** If you skipped `ollama pull llama3.2:3b`, the test
   *runs* (port is open) but fails, because `generate_answer` returns its
   `"Unable to generate an answer: ..."` error string. Pull the model first.
4. **It depends on `data/samples/ask_sample.docx`** — same as your existing tests, so no
   new dependency, but keep running pytest from the project root.

### Optional hardening

A clean real-Ollama failure looks very different from a model-not-pulled failure. If you
want the test to tell them apart, `generate_answer` swallows its own exceptions and
returns error *strings* — so a failed model call still yields HTTP 200. Guard against the
error string explicitly:

```python
    assert response.status_code == 200
    answer = response.json()["answer"].lower()

    # generate_answer returns an error STRING instead of raising, so a 200 is
    # not proof on its own — check the answer isn't an error message.
    assert "unable to generate" not in answer, f"Ollama returned an error: {answer}"
    assert "revenue" in answer or "85 million" in answer
```

## Quick recap — the 3 rules

1. Helper and `@pytest.mark.skipif` at **module level** — the skip condition is evaluated
   at collection time, before any test runs.
2. `ollama pull llama3.2:3b` + a running server makes the test *run*; without them it
   correctly *skips* (`s`), never fails.
3. Assert loosely (a keyword, not an exact string), and remember a 200 status is not proof
   on its own because `generate_answer` returns error strings instead of raising.

---

*Part of the Step 8 line in the README: `tests/test_api.py` proves the wiring; this test
proves the real LLM call. Commit it with the rest of Step 8.*