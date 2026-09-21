# Step 5 — `app/store.py`, played from the ground up

A learning guide for *you*, because you said you're stuck and this is the first time
you've built something like this. Your README deliberately does **not** hand you the
code — this guide fills the gap when you're stuck. It explains the concepts, walks
through every method, lists the classic traps, and ends with a reference solution
you can compare against (peek at it only after trying yourself).

---

## The 30-second version

Your RAG pipeline so far:

```
chunks (Step 3) ──embed (Step 4)──▶ vectors ──store (Step 5)──▶ FAISS index
```

Step 4 turned each chunk into a row of 384 numbers (an *embedding*). Step 5 is the
**storage + retrieval** layer. It must answer two questions:

1. "Here are chunk texts and their vectors — remember them."
2. "Here is a query vector — which remembered chunks are closest, and **what text are they**?"

That second question is the trap. FAISS will happily answer "closest *row numbers*" —
but it does **not** know the words. **Your class is the thing that re-attaches words
to numbers.** That sentence is the entire step.

---

## The one big idea: index vs metadata (read until it's obvious)

```python
self.index   # a FAISS object: rows of float32 numbers + a nearest-neighbour algorithm
self.texts   # YOUR parallel python list: the human-readable text for each row
```

**Rule: row `i` in `self.index` ⇔ `self.texts[i]`. Always. No exceptions.**

- `self.index` stores **only numbers**. It doesn't know about sentences, files, pages, or citations.
- `self.texts` stores **only words**. It can't be searched for similarity.
- Together they're a vector store. Apart, they're a brick and a spoon.

**Now re-read the `store.py` you wrote and you'll see all the gaps are the same one gap:**

| Where      | What's wrong                                                        |
| ---------- | ------------------------------------------------------------------- |
| `add()`    | Takes `texts` but **drops them** — `self.texts` never grows.        |
| `search()` | Returns `f'Text for index {i}'` — a **made-up string**, because `self.texts` was never filled. |
| `save()` / `load()` | Persist **only the numbers**. After reload, `self.texts` is empty again. |

Everything else in your file is genuinely fine. The fix is not a new library, a new
trick, or more FAISS knowledge — it's **keeping the text beside the numbers, both in
memory and on disk**.

---

## What you already got right (don't change it)

- The `class VectorStore` shape — `add` / `search` / `save` / `load` — matches the
  README's suggested interface.
- Creating the index at the right dimension: `faiss.IndexFlatL2(dimension)`,
  where `dimension` must equal your embedding size (384 for `all-MiniLM-L6-v2`).
- The basic FAISS calls: `index.add(...)`, `index.search(...)`, `faiss.write_index`,
  `faiss.read_index`. Those are real and correct.

---

## Method by method — what each one must do, and why

### `__init__(self, dimension)`

Two jobs:

1. **Build the index at the right dimension.** Design decision that is yours to own:
   - `IndexFlatL2` — Euclidean distance. **Smaller score = more similar.**
   - `IndexFlatIP` — inner product (dot product). **If your vectors are normalized,
     this equals cosine similarity. Larger score = more similar.**
   
   In Step 4 you *explicitly* normalized your chunk and query embeddings "for cosine
   similarity". So `IndexFlatIP` is the *consistent* choice here — pick it, and write
   that reasoning in a comment so future-you remembers why. (Keeping `L2` also works —
   it ranks the same — but then your scores are distances, and the words "score" and
   "distance" in your search results should match which one you chose.)
2. **Start the parallel text list**: `self.texts = []`.

### `add(self, texts, vectors)`

Four things, in order:

1. **Guard**: `len(texts)` must equal `vectors.shape[0]` (one text per vector row).
   If they mismatch, `raise ValueError(...)` *now* — a loud error today beats a silent
   text-vs-numbers desync bug three documents later.
2. **Cast**: `vectors = vectors.astype('float32')`. numpy's default is `float64`, but
   FAISS is a C++ library that stores `float32`. This is the "Figure out when" bullet
   from the README — the answer is *here*, in `add` (and again in `search`).
3. **Feed the numbers to FAISS**: `self.index.add(vectors)`.
4. **Keep the words yourself**: `self.texts.extend(texts)`.

> Use `extend(...)`, not `=`. `extend` **appends** to the list. Step 6 `/upload`
> will call `add` once per document — `extend` means a second document's chunks get
> added after the first document's, at new positions. `=` would wipe the first
> document and silently break every saved position.

Step 4 is the line you were missing.

### `search(self, query, top_k=5)`

Walk through the whole flow:

1. **Empty check**: if `self.index.ntotal == 0`, `return []`. Searching an empty index
   is undefined behaviour / junk.
2. **Shape it**: your `embed_query` returns shape `(384,)` — *one* vector. FAISS wants
   a 2-D array, shape `(1, 384)`. So:
   ```python
   query = query.reshape(1, -1).astype('float32')
   ```
   (`-1` means "figure out the size for me".)
3. **The call**: `scores, positions = self.index.search(query, top_k)`.
   Note the return order — **scores first, positions second**. That's the opposite of
   what almost everyone guesses first try.
4. **Handle the `-1` sentinel**: if the index holds fewer than `top_k` vectors, FAISS
   fills the missing result slots with `-1`. So:
   ```python
   pos = positions[0][i]
   if pos == -1:
       continue
   ```
   Never let `-1` reach `self.texts[pos]` — `self.texts[-1]` is the *last* element,
   which is subtly wrong and very confusing.
5. **Map numbers → words**: the real text is `self.texts[pos]`. This is the line that
   replaces your `f'Text for index {i}'` placeholder.
6. **Build the result list**:
   ```python
   results.append({'text': self.texts[pos], 'score': float(scores[0][i])})
   ```
   Two details: name the key to match your metric (`score` for `IndexFlatIP`,
   `distance` for `IndexFlatL2`), and wrap in `float(...)` — FAISS returns
   `numpy.float32`, which json/HTTP (Step 6) cannot serialize.

FAISS already sorts results best-first, so your list is in the right order for free.

### `save(self, path)` / `load(self, path)`

The README says it exactly: *"persist it (pickle/json) with a matching name so
`save`/`load` restore **both**."* "Both" = the index **and** the text list.

**`save`**:
1. Make sure the target folder exists: `os.makedirs(os.path.dirname(path), exist_ok=True)`.
   `data/indexes/` is gitignored, so it may not exist yet — FAISS will refuse to write
   into a folder that isn't there.
2. Write the numbers: `faiss.write_index(self.index, path)`.
3. Write the words **next to it**, with a matching name — e.g. `path + ".texts.json"`:
   ```python
   with open(path + ".texts.json", "w", encoding="utf-8") as f:
       json.dump(self.texts, f)
   ```
   Why JSON instead of `pickle`? A `.json` sidecar is human-readable — open it in an
   editor when you're debugging and *see* the chunks. JSON also only stores plain text,
   which is all you need here.

**`load`**:
1. Read the numbers back: `self.index = faiss.read_index(path)`.
   Also grab `self.dimension = self.index.d` so the loaded store reports the right
   dimension for future `add` calls.
2. Read the words back from the sidecar:
   ```python
   with open(path + ".texts.json", "r", encoding="utf-8") as f:
       self.texts = json.load(f)
   ```
3. (Nice safety net) assert the two halves agree:
   ```python
   assert self.index.ntotal == len(self.texts), "index/text count mismatch — was the save complete?"
   ```
   If the sidecar is missing or stale, this fails loudly instead of returning fake-looking
   search results.

**Why does saving both matter?** Because a retrieval system whose results say
`Text for index 0` isn't retrieving — it's lying in a way that *looks* like it works.
Persistence matters exactly as much: `load` without the text list reproduces the same
lie from disk.

---

## The classic mistakes checklist (tick yours against this)

- [ ] `add()` ignores `texts` (never fills `self.texts`)
- [ ] `search()` returns a placeholder string instead of `self.texts[pos]`
- [ ] forgot `query.reshape(1, -1)` (FAISS needs 2-D)
- [ ] forgot `.astype('float32')` (numpy gives float64 by default)
- [ ] swapped the return order — it's `scores, positions`, not `positions, scores`
- [ ] `-1` sentinel not filtered (index shorter than `top_k`)
- [ ] `save`/`load` persist only the index, not the text sidecar
- [ ] `IndexFlatL2` vs Step 4's normalization — inconsistent metric story (`distance`
      vs `score`, smaller vs larger better)
- [ ] returning numpy types (`numpy.float32`, `numpy.int64`) instead of python `float`/`int`

That first bullet — "add ignores texts" — is the one behind everything else you felt
was missing.

---

## Prove it works (the acceptance test)

Your README's acceptance criteria for this step:

> *add ~5 chunks of a real transcript, search with one of them, assert it returns
> itself first. Save → reload → same results.*

Two levels, both useful.

### Level 1 — store only (fast, no model, no internet)

Invent 5 random normalized vectors with numpy and check the store logic *in isolation*.
This isolates "is my store correct?" from "does the embedding model work?" — great for
debugging:

```python
from app.store import VectorStore
import numpy as np

rng = np.random.default_rng(0)
vecs = rng.normal(size=(5, 384)).astype('float32')          # random rows
vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)   # normalize (like Step 4 does)
texts = [f"chunk {i}" for i in range(5)]

store = VectorStore(dimension=384)
store.add(texts, vecs)

top = store.search(vecs[2].reshape(1, -1), top_k=3)         # same shape trick as search
assert top[0]['text'] == 'chunk 2', top                      # must return itself first
assert isinstance(top[0]['score'], float)                    # python float, not numpy
print("Level 1 OK:", top)
```

### Level 2 — the real thing (uses your Steps 3 and 4)

```python
# tests/sanity_store.py  — save this file, then run from the repo root:
#   .\venv\Scripts\python.exe tests\sanity_store.py
import os
import sys
import tempfile

# Make `import app.*` work when this script is run from the tests/ folder.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chunker import chunk_text
from app.embeddings import embed_texts, embed_query
from app.store import VectorStore

text = """The CFO resigned after a disagreement about the quarterly forecast.
The company beat its revenue targets by 12 percent in Q2.
Management mentioned risks around supply chain and inflation.
The board approved a new investment in AI research.
Bonuses will be paid out in December."""

chunks = chunk_text(text, chunk_size=200, overlap=0)['chunks']   # your Step 3
chunk_texts = [c['text'] for c in chunks]
vectors = embed_texts(chunk_texts)                               # your Step 4 -> shape (n, 384)

store = VectorStore(dimension=vectors.shape[1])
store.add(texts=chunk_texts, vectors=vectors)

# 1) Search with the FIRST chunk's own vector -> it must be the top hit.
q = embed_query(chunk_texts[0])
top = store.search(q, top_k=3)
assert top[0]['text'] == chunk_texts[0], \
    f"Expected the chunk itself first, got: {top[0]['text'][:40]!r}"
print("self-match OK   |", top[0]['text'][:50], "| score:", top[0]['score'])

# 2) Persistence round-trip: save -> fresh store -> load -> same results.
path = os.path.join(tempfile.gettempdir(), "store_sanity.index")
store.save(path)

fresh = VectorStore(dimension=vectors.shape[1])
fresh.load(path)
top_after = fresh.search(q, top_k=3)
assert [r['text'] for r in top_after] == [r['text'] for r in top], \
    "Reload changed the results!"
print("round-trip OK   |", top_after[0]['text'][:50], "| score:", top_after[0]['score'])

os.remove(path)
os.remove(path + ".texts.json")
print("ALL GOOD — Step 5 works.")
```

Run it with `.\venv\Scripts\python.exe tests\sanity_store.py`.

Notes:
- The **first** run downloads `all-MiniLM-L6-v2` (needs internet once, a few tens of MB).
- That `sys.path` insert at the top is a real Python gotcha: when you run a script,
  Python adds the *script's folder* (`tests/`) to the import path — **not** the repo
  root. Without the insert, `from app.chunker import ...` fails with
  `ModuleNotFoundError` even though the package exists.
- `chunk_size=200, overlap=0` is just to keep the sample short; overlap must be
  `< chunk_size` (your Step 3 enforces that), and `0` is fine.

---

## Reference solution (peek ONLY after trying yourself)

```python
# app/store.py — a fixed, annotated version
import faiss
import json
import numpy as np
import os


class VectorStore:
    def __init__(self, dimension: int):
        self.dimension = dimension
        # IP = inner product. Step 4 normalizes every vector, so inner product
        # == cosine similarity. LARGER score = MORE similar.
        self.index = faiss.IndexFlatIP(dimension)
        # THE parallel text list: row i of the index <-> self.texts[i]. Always.
        self.texts = []

    def add(self, texts: list[str], vectors: np.ndarray) -> None:
        # one text per vector, in the same order — guard the pairing
        if len(texts) != vectors.shape[0]:
            raise ValueError(
                f"{len(texts)} texts but {vectors.shape[0]} vectors — they must match."
            )
        # FAISS is a C library: it wants float32. numpy defaults to float64.
        vectors = vectors.astype('float32')
        self.index.add(vectors)      # the numbers go into FAISS ...
        self.texts.extend(texts)     # ... the words stay with us, same positions

    def search(self, query: np.ndarray, top_k: int = 5) -> list[dict]:
        if self.index.ntotal == 0:
            return []
        # embed_query returns shape (dim,); FAISS needs (1, dim)
        query = query.reshape(1, -1).astype('float32')
        # NOTE: scores come FIRST, positions second — easy to swap by accident
        scores, positions = self.index.search(query, top_k)
        results = []
        for i in range(len(positions[0])):
            pos = positions[0][i]
            if pos == -1:            # fewer than top_k vectors stored
                continue
            results.append({
                'text': self.texts[pos],     # the real chunk text
                'score': float(scores[0][i]),  # python float (JSON-safe for Step 6)
            })
        return results

    def save(self, path: str) -> None:
        # data/indexes/ is gitignored and may not exist yet
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        faiss.write_index(self.index, path)
        # sidecar file: numbers live in `path`, words live in `path + ".texts.json"`
        with open(path + ".texts.json", "w", encoding="utf-8") as f:
            json.dump(self.texts, f)

    def load(self, path: str) -> None:
        self.index = faiss.read_index(path)
        self.dimension = self.index.d
        with open(path + ".texts.json", "r", encoding="utf-8") as f:
            self.texts = json.load(f)
        assert self.index.ntotal == len(self.texts), "index/text count mismatch — broken save?"
```

---

## Where this plugs in next (Step 6, the API)

```
/upload  → parse → chunk → embed_texts → store.add(texts, vectors) → store.save("data/indexes/doc.index")
/ask     → embed_query(question) → store.search(query_vec, k=5) → [{'text', 'score'}, ...]
```

```python
store = VectorStore(dimension=384)                  # 384 = all-MiniLM-L6-v2 vector size
store.add(chunk_texts, vectors)                     # from your Steps 3 + 4
store.save("data/indexes/earnings.index")
# ...later, in /ask...
store.load("data/indexes/earnings.index")
results = store.search(embed_query("What risks did management mention?"), top_k=5)
for r in results:          # r['text'] is real chunk text — citations work now
    print(r['score'], r['text'][:60])
```

---

## Glossary for this step

- **`ntotal`** — property on a FAISS index: how many vectors are currently stored.
  Use it for the empty-search guard and the load sanity assert.
- **`astype('float32')`** — numpy: convert to 32-bit floats. FAISS requires float32;
  float64 wastes 2× memory and is the classic "why is FAISS mad at me" cause.
- **Sentinel `-1`** — FAISS's way of saying "no vector here" when `top_k` is bigger
  than `ntotal`. `self.texts[-1]` would silently grab the *last* chunk — always filter it.
- **Sidecar file** — a helper file that rides beside the main one (`path + ".texts.json"`
  next to `path`). Like a race-car sidecar: it doesn't drive, but you're stuck without it.
- **Inner product vs Euclidean distance** — IP is the dot product (an angle measure);
  for normalized vectors that's cosine similarity, **higher = closer**. L2 is straight-line
  distance, **lower = closer**. Same ranking, opposite meaning of the number.

---

## What to do right now

1. Try to fix `store.py` yourself, using the checklist as your spec — especially:
   *keep the texts*, *map positions back in `search`*, *save both halves*.
2. Save the Level 2 script as `tests/sanity_store.py` and make it pass.
3. Commit (this marks Step 5's checkbox in the README):

   ```powershell
   git add app/store.py tests/sanity_store.py
   git commit -m "Step 5: vector store keeps text with vectors + persistence round-trip"
   ```

4. Send me your final `store.py` **and** the sanity script output, and I'll review it
   and explain the *why* of anything you want. If you copied the reference solution,
   be ready to explain back to me: **why must `self.texts` exist in two places —
   in memory and on disk — for search to be truthful after a `load`?**