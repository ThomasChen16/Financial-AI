# financial-ai — the complete rebuild guide

A RAG (Retrieval-Augmented Generation) app that answers questions about earnings
transcripts, rebuilt from scratch as a learning project. The old auto-generated
scaffold lives in `_archive_scaffold/` (gitignored) — leave it there until the
rebuild is done and you're confident.

This README is the **living guide for the whole project**. Each step below is
self-contained: what to build, the concepts, how to discover the APIs yourself,
which design decisions are yours to make, how to prove it works, and the pitfalls
we already hit. If you get lost, come back here.

---

## The data flow (keep this in your head at all times)

```
  upload PDF/DOCX
       │  parse        Step 2
       ▼
     plain text
       │  chunk        Step 3
       ▼
     chunks (~500 tokens)
       │  embed        Step 4
       ▼
     vectors ──store──▶ FAISS index      Step 5
                              ▲
  user question ──embed──▶ vector
                              │  search (top-k)
                              ▼
                        relevant chunks
                              │  prompt + generate        Step 7
                              ▼
                       answer + citations
```

Everything above the "user question" line is **indexing** — done once per document.
Everything below is **querying** — done per question.

---

## How we work (so it actually sticks)

1. Each step below is a goal + acceptance criteria + resources. **Never the code.**
2. You read the resources, **experiment in the REPL**, and write the code yourself.
3. You run it, then ship it to me (code + output + any errors). I review and explain
   what's right, what's wrong, and *why*.
4. We prove each piece works before moving on.

Core habits you'll practice every step:
- **Discover APIs yourself**: `python` → `import lib` → `dir(lib)`, `help(lib.x)`,
  and `type(...)` on your objects. This replaces "look it up and copy."
- **Read tracebacks from the bottom up** — the last line tells you what actually broke.
- **Commit after each step.** Small commits that each mean something.
- **Pin dependencies deliberately** — remember why our `sentence-transformers==2.2.2`
  broke: an unpinned transitive dep (`huggingface_hub`) moved on and removed an API
  the pinned package used. `requirements.txt` is a contract you choose, not a snapshot.

---

## Command cheat-sheet (Windows PowerShell)

```powershell
# Run Python from the project venv — never your system python!
.\venv\Scripts\python.exe -V
.\venv\Scripts\python.exe -m pip install -r requirements.txt   # install deps
.\venv\Scripts\python.exe -m pip freeze                        # snapshot of installed packages
.\venv\Scripts\python.exe tests\sanity_parser.py               # run a test script
.\venv\Scripts\python.exe                                       # REPL — your best learning tool
.\venv\Scripts\python.exe -m uvicorn app.api:app --reload      # run the web API (Step 6+)
git status ; git add . ; git commit -m "message" ; git log --oneline
```

> **Why `.\venv\Scripts\python.exe` and not `python`?** `python` can resolve to a
> different interpreter (you have 3.11 / 3.13 / 3.14 installed). The venv python is
> the only one that sees the project's installed packages. `py -0` lists all pythons.

---

## Step guides

Same shape every step: **goal → concept → discover → design → prove**. Read the
resource, experiment in the REPL, *then* write the file. Never type code you can't
explain. End every step with a git commit.

### Step 1 — `requirements.txt` (dependency contract)

**Files:** `requirements.txt` (exists, empty).

**Goal:** declare only the *direct* dependencies the parser needs — `pdfplumber` and
`python-docx` — with a pinning strategy you can defend.

**Concept — dependency pinning.** Your venv holds ~90 packages because installing a
library pulls in its transitive dependencies. `requirements.txt` lists what *your
code imports directly* plus the version constraints you care about:
- `==X.Y.Z` — exact; reproducible, but you must upgrade deliberately.
- `>=X.Y` — floor; pip picks newer. Most permissive, most surprises.
- `~=X.Y` — compatible-range; patch/minor within the line, no major jumps.

**Why pin at all?** We lived this: `sentence-transformers==2.2.2` imported a name
from `huggingface_hub`; pip had installed the newest `huggingface_hub`, which removed
that name → `ImportError`. A pinned direct dep can still break on an unpinned
transitive one.

**Discover:**
```python
.\venv\Scripts\python.exe -m pip freeze          # what's actually installed
.\venv\Scripts\python.exe -m pip show pdfplumber  # one package: version + dependencies
```

**Do:** write the two deps with your chosen pins + a one-line comment each; run
`pip install -r requirements.txt` — it should print "Requirement already satisfied"
for both (proves your contract matches reality).

**Acceptance:** install exits 0; every line has a comment you can explain.

---

### Step 2 — `app/parser.py` (PDF/DOCX → plain text)

**Files:** `app/parser.py` (empty); `tests/make_sample_docx.py`; `tests/sanity_parser.py`.

**Goal:**
```python
def extract_pdf_text(path: str) -> str: ...
def extract_docx_text(path: str) -> str: ...
```

**Concept — learning any library from its docs.** This step is *not* about
pdfplumber. It's about the skill: *"how do I figure out an unfamiliar library?"*
Always: `dir()` and `help()` first → official docs → experiments in the REPL.

**Discover (REPL, before writing any code):**
```python
>>> import pdfplumber
>>> dir(pdfplumber)                    # what does the module expose? (look for open)
>>> help(pdfplumber.open)              # what does open() accept / return?
>>> with pdfplumber.open("data/samples/<file>.pdf") as pdf:
...     type(pdf)                      # what object is this?
...     type(pdf.pages)                # iterable of pages?
...     pdf.pages[0].extract_text()    # the whole game in one call
>>> from docx import Document
>>> help(Document)                     # constructor options
>>> doc = Document("data/samples/sample.docx")
>>> type(doc.paragraphs)               # iterable of what? run dir() on one item
```

**Read:** [pdfplumber (PyPI) → "Python library" → "Extracting text"](https://pypi.org/project/pdfplumber/),
[python-docx → User Guide → Quickstart](https://python-docx.readthedocs.io/en/latest/).

**Design decisions you own:**
- PDF: loop pages, call `extract_text()` per page. Keep a per-page marker (e.g.
  `[p.1]`) so later steps can cite *which page* a fact came from? Your call.
- `extract_text()` can return `None` on scanned/empty pages. What's your policy?
- DOCX: `doc.paragraphs` includes empties. Filter or keep? Why?

**Prove it:**
1. `tests/make_sample_docx.py` builds `data/samples/sample.docx` (2–3 paragraphs)
   using python-docx itself.
2. Drop a real PDF into `data/samples/`.
3. `tests/sanity_parser.py` runs both functions, prints truncated text, exits 0.

**Acceptance:** docx text round-trips exactly; pdf text has recognizable words;
`sanity_parser.py` exits 0 from the repo root.

**Pitfalls we already hit (don't relearn them):**
- `from pdfplumber import PDF` then `pdfplumber.open(...)` → `NameError`. You imported
  the *class*, not the module. Use `import pdfplumber`.
- `from docx import Documents` → doesn't exist. It's `Document` (singular).

---

### Step 3 — `app/chunker.py` (text → chunks)

**Files:** `app/chunker.py` (empty); `tests/sanity_chunker.py`.

**Goal:**
```python
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[dict]: ...
```
Each chunk is a dict — you decide the keys (e.g. `text`, `index`).

**Concept — why chunk at all?** Two reasons:
1. LLMs have a limited context window; a 40-page transcript won't fit.
2. Retrieval works on *focused* units — a question matches a paragraph, not a book.
So we cut the transcript into ~500-token pieces and retrieve only the few most
relevant ones. **Tokens** ≈ 4 characters / ¾ of a word of English text — the unit
LLMs count context in.

**Concept — designing an algorithm (the real lesson).** We're not looking up an API
here; we're *designing* one. Questions to answer with your own reasoning:
- Where are the cut points? Cutting at exact character counts splits words in half —
  fix that. Cutting at sentence/paragraph boundaries keeps meaning intact but gives
  uneven sizes. Which matters more for retrieval?
- What is **overlap** for? If chunk N ends mid-idea, chunk N+1 repeats the tail so
  the idea isn't cut off. Tradeoff: overlap = redundant storage + more exact-match
  hits; too little = lost context. ~50–100 tokens is a sane starting point.
- Estimating tokens without a tokenizer: `len(text) // 4` is a fine proxy for English.

**Do:** write `chunk_text`, your design, your comments. Build a quick sanity script.

**Prove it (write these as assertions):**
- Concatenating the chunk texts reconstructs the original *exactly* (no lost/added
  chars) — accounting for overlap deliberately.
- With overlap > 0, chunk boundaries repeat a little content.
- Input smaller than `chunk_size` → exactly one chunk.
- Your metadata survives into each chunk.

**Acceptance:** the invariants above hold on your sample transcript text.

---

### Step 4 — `app/embeddings.py` (chunks → vectors)

**Files:** `app/embeddings.py` (empty); `tests/sanity_embeddings.py`.

**Goal:**
```python
def embed_texts(texts: list[str]) -> np.ndarray: ...   # shape (n, 384)
def embed_query(text: str) -> np.ndarray: ...          # shape (384,)
```

**Concept — what an embedding *is*.** A neural net trained so that semantically
similar sentences land *close together* in a high-dimensional space. Input "The CFO
resigned." → a list of 384 numbers. Similar sentences → similar numbers; unrelated
topics → different directions. This is the dictionary that lets us answer "which
chunks are about this question?"

**Discover (REPL):**
```python
>>> from sentence_transformers import SentenceTransformer
>>> model = SentenceTransformer("all-MiniLM-L6-v2")   # downloads on first run (needs internet once)
>>> vectors = model.encode(["The CFO resigned.", "The CEO quit today.", "I like pizza."])
>>> vectors.shape                  # (3, 384) — one row per sentence
>>> type(vectors)                  # numpy array
```

**Read:** [sbert.net → Sentence Transformer Usage](https://www.sbert.net/).

**Design decisions you own:**
- Loading the model is slow — load it **once** at module level / lazily, not per call.
- Batching: `model.encode(list)` handles batches; you only need to think about
  batch size at scale.
- Do you **normalize** (`vectors / np.linalg.norm(vectors, axis=1, keepdims=True)`)
  so inner product == cosine similarity? Write down why or why not — you'll need it
  in Step 5.

**Prove it:** encode three sentences — two related, one unrelated. The two related
ones must have higher dot product / smaller distance than the unrelated one. Print
the numbers and be ready to explain them.

**Acceptance:** shapes are right; related sentences score closer than unrelated ones.

---

### Step 5 — `app/store.py` (save + search vectors)

**Files:** `app/store.py` (empty); `tests/sanity_store.py`.

**Goal:**
```python
class VectorStore:
    def add(self, texts: list[str], vectors: np.ndarray) -> None: ...
    def search(self, query: np.ndarray, k: int = 5) -> list[dict]: ...  # chunk text + score
    def save(self, path: str) -> None: ...
    def load(self, path: str) -> None: ...
```
(Method names are yours to finalize — this is a suggested shape.)

**Concept — vector search with FAISS.** FAISS is a C++ library (with a Python
wrapper) that finds the *k nearest* vectors to a query, fast. Two index types:
- `IndexFlatL2` — Euclidean distance (smaller = better).
- `IndexFlatIP` — inner product. If your vectors are *normalized* (Step 4 decision),
  inner product == cosine similarity (larger = better).

**Concept — index vs metadata.** The FAISS index stores only numbers. The *text* of
each chunk lives in your own parallel list. Index position `i` ↔ `my_texts[i]`. When
you search, FAISS returns positions + distances; you look up the text yourself.

**Discover (REPL):**
```python
>>> import faiss
>>> index = faiss.IndexFlatIP(384)          # dim must match your embeddings
>>> index.add(vectors)                       # vectors: float32, shape (n, 384)
>>> scores, positions = index.search(query.reshape(1, -1), k=5)   # query must be 2-D!
>>> index.ntotal                             # how many vectors are in the index
>>> faiss.write_index(index, "data/indexes/sample.index")
>>> index2 = faiss.read_index("data/indexes/sample.index")
```

**Read:** [faiss.ai](https://faiss.ai/) → "What is similarity search" (short!) → the
wiki / getting-started examples.

**Design decisions you own:**
- Keep the mapping index→text in memory alongside; persist it (pickle/json) with a
  matching name so `save`/`load` restore both.
- Where to save: `data/indexes/` (gitignored).
- float32: numpy defaults to float64 — FAISS often needs float32. Figure out when.

**Prove it:** add ~5 chunks of a real transcript, search with one of them, assert it
returns itself first. Save → reload → same results.

**Acceptance:** search returns the most similar chunk first; persistence round-trips.

---

### Step 6 — `app/api.py` (FastAPI web layer)

**Files:** `app/api.py` (empty). FastAPI ties Steps 2–5 together.

**Goal (core):**
```python
app = FastAPI(...)
@app.post("/upload")   # accept PDF/DOCX → parse → chunk → embed → store
@app.post("/ask")      # question → embed → search → (Step 7) answer
@app.get("/health")    # simple "alive" check
```

**Concept — running a web server.** A client sends an **HTTP request** (method +
path + body) to a server on a port; your app answers with a status code and a JSON
body. FastAPI maps decorators to routes: `@app.post("/ask")` = "when a POST arrives
at /ask, run this function."

**Discover — start tiny before wiring the whole pipeline:**
1. FastAPI tutorial: First Steps → Path Parameters → Query Parameters → Request Body
   → Request Files. Follow it *in your own venv*.
2. Run `python -m uvicorn app.api:app --reload` and open http://127.0.0.1:8000/docs —
   those docs are generated from your function signatures. A free API console.
3. Test with curl:
   - `curl http://127.0.0.1:8000/health`
   - upload: `curl -F "file=@data/samples/sample.docx" http://127.0.0.1:8000/upload`

**Read:** [FastAPI Tutorial](https://fastapi.tiangolo.com/tutorial/) → First Steps →
Request Files → Testing (TestClient lets you test without a running server).

**Design decisions you own:**
- Save uploaded files to `data/uploads/` (gitignored) before parsing.
- Pydantic model for the `/ask` request (`{"question": "..."}`).
- What should `/ask` do *before* Step 7 exists? Return the retrieved chunks + a
  placeholder answer — proof the retrieval half works.

**Acceptance:** upload a docx/pdf sample → 200 + you can see it got chunked/stored
(print counts); `/ask` returns retrieved text. Manual curl counts as proof.

---

### Step 7 — `app/llm.py` (generate answers with Ollama)

**Files:** `app/llm.py` (empty).

**Goal:**
```python
def generate_answer(question: str, chunks: list[dict]) -> str: ...
```
calls a local LLM (Ollama) over HTTP.

**Concept — HTTP from Python.** Ollama runs a server on `localhost:11434`. Talking to
it is just building a URL, a JSON body, and reading the JSON response — no special
library needed (`requests` or even stdlib `urllib`).

**Discover:**
1. Install Ollama (https://ollama.com) and pull a model: `ollama pull llama3.2:3b`
   (or mistral).
2. `curl http://localhost:11434/api/chat -d '{"model":"llama3.2:3b","messages":[{"role":"user","content":"Say hi"}]}'`
3. In Python: `import requests; help(requests.post)` — figure out how to send the
   JSON and read `response.json()`.

**Read:** [Ollama API docs → Endpoints → Chat/Generate](https://docs.ollama.com/api/)
— note the exact keys (`model`, `messages` or `prompt`, plus `stream: false` for
simple one-shot calls).

**Concept — prompt engineering (the actual skill).** An LLM takes a *prompt* and
continues it. To ground an answer in your transcript:
- A **system message**: "You are an analyst. Answer using ONLY the context. If it
  isn't in the context, say so."
- Put the retrieved chunks (with source markers) into the **user message**, then the
  question.
You'll iterate on this wording a lot in practice — that's normal and expected.

**Acceptance:** `generate_answer` returns a string that, when the chunks contain the
answer, mentions it convincingly; when they don't, it says it doesn't know. (Try both
cases.) Handle "Ollama not running" gracefully (error message, not a crash).

---

### Step 8 — wiring + integration test (the finish line)

**Goal:** `POST /upload` runs parse → chunk → embed → store end-to-end; `POST /ask`
runs embed → search → generate; `tests/test_api.py` proves it.

**Concept — integration tests & temp files.** FastAPI's `TestClient` can post a real
file from `data/samples/`, but the test should not clobber your real `data/uploads`
and indexes. Options you'll research: `tmp_path` fixture, per-test index names,
os.path context managers. Small real-data end-to-end beats 20 mocks for *this*
project.

**Design decisions you own:**
- Each `/upload` builds a fresh index (simplest) — worth a comment about what
  production would do differently (appending, multiple docs).
- Error paths: upload a `.txt` → 400 with a message. Question before any upload →
  sensible error.
- Where does the pipeline live: all inside `app/api.py` endpoints, or thin endpoints
  calling small functions? Spreading it out = your call; be able to defend it.

**Acceptance (your final demo):**
- `curl -F "file=@..." http://localhost:8000/upload` → 200 + counts printed.
- `curl -d '{"question":"What risks did management mention?"}' http://localhost:8000/ask`
  → an answer grounded in the transcript, with page/source markers from Step 2's
  metadata (if you kept them).
- Both covered by `tests/test_api.py`.

---

## Glossary (build this as you go)

- **venv** — isolated folder with its own Python + packages; your app never touches
  your system Python.
- **direct vs transitive dependency** — things your code imports vs. things those
  things import.
- **chunk** — a ~500-token slice of the transcript; the unit retrieval searches.
- **token** — ~4 characters / ¾ word of English text; what LLMs count context in.
- **embedding / vector** — a list of numbers (here 384) encoding meaning; similar
  meaning ⇒ "close" numbers.
- **cosine similarity** — cos of the angle between two vectors; ranges −1…1. When
  vectors are normalized, `dot(a,b)` == cosine similarity.
- **index (FAISS)** — a structure that answers "which stored vector is nearest to my
  query vector?" fast.
- **top-k** — the k best matches; RAG typically retrieves 3–10 chunks.
- **RAG** — Retrieval-Augmented Generation: find evidence in a corpus, then have an
  LLM answer *using that evidence*, with the evidence as context.
- **HTTP / REST** — the protocol the web runs on; methods GET/POST/DELETE, paths,
  status codes (200 OK, 400 bad request, 404 not found).
- **Pydantic model** — a class that both validates and documents request/response
  JSON; FastAPI turns it into the /docs schema.

---

## Troubleshooting & lessons learned (so far)

1. **Some imports "cannot be resolved".** → Wrong interpreter selected. Bottom-right
   of VS Code → pick `venv` (not system, not `.venv` — we archived the empty one).
   Or check `.vscode/settings.json` pins the venv path.
2. **`ImportError: cannot import name 'cached_download' from 'huggingface_hub'`**
   → stale pin. A pinned old package met a new unpinned dependency. Fix: upgrade the
   direct package (`sentence-transformers>=2.7`) — we already did (5.7.0).
3. **`NameError: pdfplumber is not defined`** → imported the class, not the module.
   `import pdfplumber`, then `pdfplumber.open(...)`.
4. **`ImportError: cannot import name 'Documents' from 'docx'`** → it's `Document`.
5. **`from services.llm import check_ollama_running` → ImportError** → the function
   didn't exist yet. Import only what exists.
6. **Old libraries on Python 3.14** → `SyntaxWarning`s (e.g. anyio "return in
   finally") and removed APIs. When in doubt, prefer Python 3.13/3.11 for this era
   of pinned stack, and always `pip install` from a clean venv.
7. **pip reports weird "exit code 1" in PowerShell** → often just PowerShell wrapping
   stderr text (the `python.exe :` prefix). Check the actual message and
   `$LASTEXITCODE`; pip prints its own ERROR/SUCCESS lines.
8. **Reading tracebacks** → the *last* line is the real error. The top frames are
   context. Read bottom-up every time.

---

## Progress log

- [x] Scaffold archived to `_archive_scaffold/` (delete when confident)
- [x] Fresh layout: `app/` `tests/` `data/samples/` + venv pinned in VS Code
- [ ] **Step 1** — `requirements.txt` (files exist, empty)
- [ ] **Step 2** — `app/parser.py` + sanity tests
- [ ] **Step 3** — `app/chunker.py`
- [ ] **Step 4** — `app/embeddings.py`
- [ ] **Step 5** — `app/store.py`
- [ ] **Step 6** — `app/api.py`
- [ ] **Step 7** — `app/llm.py`
- [ ] **Step 8** — end-to-end + `tests/test_api.py`

Update the checkboxes as you land each step and commit. Old scaffold archived.