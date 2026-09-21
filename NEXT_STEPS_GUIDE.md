# Financial AI — Next Steps Guide

Steps 1–8 are done: a complete, tested RAG backend (parse → chunk → embed → store →
retrieve → Ollama → answer). This guide maps the road forward in priority order and goes
deep on the first item — the **React frontend** — in the same learn-by-doing style as
`STORE_GUIDE.md`. Peek at the reference code only after trying yourself.

---

## The roadmap (30-second version)

| # | Step | What it gives you | Effort |
|---|------|-------------------|--------|
| 1 | **Step 9 — React frontend** | Something people can click: upload & ask, answers + evidence | One afternoon |
| 2 | **Step 10 — CI on GitHub** | Every push runs `pytest` automatically | ~15 minutes |
| 3 | **Housekeeping** | Fix the two tiny gaps (`pytest` undeclared, `node_modules` not ignored) | 5 minutes |
| 4 | **Stretch goals** | Streaming answers, citations UI, multi-document, Docker | Later |

Why this order:

- **Frontend first.** Your backend is proven and tested, but nobody can *use* it yet.
  A browser UI turns "code that works" into "a thing you can demo". It's also the
  biggest learning win remaining.
- **CI second.** The repo is already public on GitHub. One small file makes every
  future commit self-checking instead of relying on "it passed on my machine".
- **Housekeeping** whenever you're in the mood — both are one-line edits.

---

## Step 9 — the React frontend

### What you're building

A single-page UI wired to your running API:

| UI element                    | Calls           | Shows                                          |
| ----------------------------- | --------------- | ---------------------------------------------- |
| File picker + Upload button   | `POST /upload`  | `filename`, `chunks`, `index_total`            |
| Question box + Ask button     | `POST /ask`     | `answer`, and the retrieved chunks + scores    |
| Optional health chip on load  | `GET /health`   | "ok · N chunks indexed"                        |

The backend doesn't change except for **one addition: CORS middleware** (explained
below). Everything else is `fetch`.

### The one big idea: your browser and FastAPI are two different origins

Right now *you* test the API with `curl.exe`. A browser page loaded from
`http://localhost:5173` (Vite's default) is a **different origin** than the API at
`http://localhost:8000` — and browsers block cross-origin `fetch` calls unless the
server says it's OK. That rule is **CORS** (Cross-Origin Resource Sharing).

Two ways to fix it:

1. **Add CORS middleware to the API** (recommended — one edit, and you understand the
   rule forever). Add to `app/api.py`, after `app = FastAPI()`:

   ```python
   from fastapi.middleware.cors import CORSMiddleware

   app.add_middleware(
       CORSMiddleware,
       allow_origins=["http://localhost:5173"],  # Vite dev server
       allow_methods=["*"],
       allow_headers=["*"],
   )
   ```

   If you use a different dev port, change the origin to match.

2. **Use Vite's dev proxy** (no CORS needed at all — the browser only sees one origin).
   Create `frontend/vite.config.js`:

   ```js
   export default {
     server: {
       proxy: {
         "/upload": "http://localhost:8000",
         "/ask":    "http://localhost:8000",
         "/health": "http://localhost:8000",
       },
     },
   };
   ```

   …then your `fetch` URLs become relative (`"/upload"` instead of
   `"http://localhost:8000/upload"`).

Your call. Most tutorials and the "learning the reason" path → **option 1**.

### Scaffold the project (prereq: Node.js LTS)

```powershell
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm run dev          # opens http://localhost:5173
```

`--template react` = plain JavaScript (no TypeScript) — one fewer concept to juggle
while you learn React the first time.

### File 1 — `frontend/src/api.js` (the API client)

Keep all `fetch` calls in one place so the UI never worries about URLs:

```js
const API = "http://localhost:8000"; // or "" if you used the Vite proxy

export function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);
  return fetch(`${API}/upload`, { method: "POST", body: form }).then((r) =>
    r.json().then((data) => ({ ok: r.ok, status: r.status, data }))
  );
}

export function ask(question) {
  return fetch(`${API}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  }).then((r) =>
    r.json().then((data) => ({ ok: r.ok, status: r.status, data }))
  );
}
```

**Why `.then` + `({ok, status, data})`?** FastAPI's error responses have a *different*
shape than success responses: success returns your JSON object, but a 400 returns
`{"detail": "..."}`. Wrapping both keeps the UI logic uniform: check `ok`, and if it's
false show `data.detail`.

### File 2 — `frontend/src/App.jsx` (the UI)

Replace the template's `App.jsx`. The key React habits to notice: state via `useState`,
`onChange` to read inputs, `onSubmit` handlers, and `results.map(...)` to render a
list:

```jsx
import { useState } from "react";
import { uploadFile, ask } from "./api";

export default function App() {
  const [file, setFile] = useState(null);
  const [question, setQuestion] = useState("");
  const [status, setStatus] = useState("");
  const [answer, setAnswer] = useState("");
  const [results, setResults] = useState([]);

  async function onUpload(event) {
    event.preventDefault();
    if (!file) return;
    const r = await uploadFile(file);
    setStatus(
      r.ok
        ? `Indexed ${r.data.chunks} chunks — ${r.data.index_total} total in index`
        : `Upload failed: ${r.data.detail}`
    );
  }

  async function onAsk(event) {
    event.preventDefault();
    if (!question.trim()) return;
    const r = await ask(question);
    if (r.ok) {
      setAnswer(r.data.answer);
      setResults(r.data.results);
      setStatus("");
    } else {
      setAnswer("");
      setResults([]);
      setStatus(`Ask failed: ${r.data.detail}`);
    }
  }

  return (
    <div>
      <h1>Financial AI</h1>

      <form onSubmit={onUpload}>
        <input type="file" accept=".pdf,.docx"
               onChange={(e) => setFile(e.target.files[0])} required />
        <button type="submit">Upload</button>
      </form>

      <p>{status}</p>

      <form onSubmit={onAsk}>
        <input value={question}
               onChange={(e) => setQuestion(e.target.value)}
               placeholder="Ask about the document…" size={50} />
        <button type="submit">Ask</button>
      </form>

      <h2>Answer</h2>
      <p>{answer}</p>

      <h2>Evidence (retrieved chunks)</h2>
      <ol>
        {results.map((r, i) => (
          <li key={i}>
            <strong>{r.score.toFixed(3)}</strong> — {r.text}
          </li>
        ))}
      </ol>
    </div>
  );
}
```

**Design decisions you own (be able to defend them):**

- Should the "Evidence" section exist? The backend already *returns* the retrieved
  chunks — showing them is what makes the answer trustworthy (this is the "citations"
  idea from the old README). I'd keep it.
- Error strings: remember `generate_answer` returns `"Unable to generate an answer: ..."`
  as a *successful 200* when Ollama's down. The UI will faithfully show that string —
  bonus point if you detect it and display a friendlier message.

### Accept it works (your demo script)

1. Terminal A: `ollama serve`
2. Terminal B: `.\venv\Scripts\python.exe -m uvicorn app.api:app --reload`
3. Terminal C: `cd frontend ; npm run dev`
4. Browser → http://localhost:5173 → upload `data/samples/ask_sample.docx` → ask
   *"What was the revenue?"* → see an answer **and** the evidence list.
5. Kill Ollama, ask again → you should see the graceful error string, not a crash.

### Don't forget for the commit

- Add `node_modules/` to `.gitignore` (it's big and regenerable — never commit it):

  ```text
  # ---- Node.js ----
  node_modules/
  frontend/dist/
  ```

- Commit the backend CORS change **and** the frontend together (one atomic step:
  "Step 9: React frontend + CORS").

## Step 10 — CI on GitHub (cheap insurance)

Your test suite is *designed* to be CI-safe: the real-Ollama test self-skips when
Ollama isn't there, so `pytest` passes on a bare runner. That means you can wire up
GitHub Actions in ~15 minutes and never touch it again.

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest

      - name: Run tests
        run: pytest tests -v
```

**The first run is slow** — the runner has no HuggingFace cache, so the embedding model
(~90 MB) downloads once during the upload test. After that, GitHub caches pip'd
packages; accept the one-time cost for now.

**What you'll see on GitHub:** a green ✔ next to every commit that passes, a red ✖ +
the failing test when it doesn't. Your mock-based tests are the real guard here; the
Ollama test shows `s` (skipped) — by design.

## Housekeeping (5 minutes)

1. **Declare `pytest` in `requirements.txt`.** Your tests import it but it isn't
   listed — it only works because it happens to be installed in your venv. Find your
   installed version and pin it:

   ```powershell
   .\venv\Scripts\python.exe -m pip show pytest   # look at "Version"
   ```

   then add e.g. `pytest==7.4.3` (match what you actually have) under a
   `# Development` comment.

2. **Add `node_modules/` to `.gitignore`** (done above — needed before the frontend
   commit).

3. **When you're confident**, delete `_archive_scaffold/` and remove its `.gitignore`
   line. Nothing in the app imports from it — it was reference material.

## Stretch goals (later — pick one at a time)

- **Streaming answers.** Today `/ask` waits for the whole model response (up to 180s).
  Change `app/llm.py` to `"stream": true` and forward tokens to the browser (SSE or
  chunked `fetch`) — a big perceived-speed win for the demo.
- **Real citations with page/source markers.** The parser already returns pages; chunk
  the text with markers like `[p.3]` and the LLM will cite them. The UI can then show
  *which part of the document* the answer came from.
- **Multiple documents.** Right now every upload shares one FAISS index
  (`indexes/default.index`). A `DELETE /document` or per-document namespaces would
  make it a multi-corpus app.
- **Better retrieval.** Hybrid search (BM25 keywords + vector), or re-rank the top-10
  chunks before sending to the LLM.
- **Docker.** A `Dockerfile` for the backend makes the project runnable anywhere
  without a Python setup dance — useful once the frontend exists too.
- **Frontend tests.** Once you have a frontend, `vitest` can unit-test `api.js` /
  `App.jsx` the same way `pytest` tests the backend.

## Working rules that got you here (keep them)

1. **One commit per step**, with a message that says what and why
   (`"Step 9: React frontend + CORS"`).
2. **Prove it before committing** — the demo script isn't optional.
3. **Read errors bottom-up**, and don't copy code you can't explain back.

---

**This is the last big step.** After the frontend, the project is a complete,
demoable, CI-tested full-stack RAG app you built from scratch. The stretch goals are
the queue you can keep pulling from at your own pace.