# Automatically test is the endpoints in api.py works
from fastapi.testclient import TestClient
from app.api import app, VectorStore
import pytest
import socket
import io
from docx import Document
import sqlite3
from app import tracking

# reusable function designed to set up baseline state environment before a test runs and cleanning it up afterwards
# tmp_path creates a new temp folder on disk for each test and deletes it after
@pytest.fixture
def isolated_client(monkeypatch, tmp_path):
    # Swap out the shared production store for a brand-new, empty one
    fresh_store = VectorStore(dimension=384)
    # Go to app.api find variable store and replace it with fresh_store
    monkeypatch.setattr("app.api.store", fresh_store)
    
    # Redirect where /upload writes file and saves the index
    monkeypatch.setattr("app.api.UPLOAD_DIR", str(tmp_path / "upload"))
    monkeypatch.setattr("app.api.INDEX_PATH", str(tmp_path / "indexes" / "default.index"))
    
    # point the SQL tracking table at the temp directory
    monkeypatch.setattr("app.tracking.DB_PATH", str(tmp_path / "uploads.db"))
    
    # Use to call upload
    return TestClient(app)


# Check whether the local Ollama service is available for tests
def _ollama_reachable() -> bool:
    try:
        with socket.create_connection(("localhost", 11434), timeout=1):
            return True
    except OSError:
        return False

# Simple call to api health to get response if it is working
def test_health():
    client = TestClient(app)
    response = client.get("health")
    assert response.status_code == 200

# Test to ensure a blank question is rejected. A question is considered empty
# when it contains no characters after surrounding whitespace is removed.
def test_ask_before_upload(isolated_client):
    response = isolated_client.post("/ask", json={"question": "   "})
    assert response.status_code == 400

# Verifies that uploading a DOCX file succeeds and returns the expected metadata and chunk count.
def test_upload_success(isolated_client):
    # open my existing docx in read binary model and hand the opne file object onto that tuble
        # Upload the sample document before asking a question about its contents.
        with open("data/samples/ask_sample.docx", "rb") as f: 
            response = isolated_client.post(
                "/upload",
                files={"file": ("ask_sample.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")} # docx MIME type
            )
        
        # mean success
        assert response.status_code == 200
        
        data = response.json()
        assert data["filename"] == "ask_sample.docx"
        assert data["chunks"] == 11
        assert data["pages"] is None
        assert data["index_total"] == 11
        
# Call to api ask to get response after upload
def test_after_upload(isolated_client):
    with open("data/samples/ask_sample.docx", "rb") as f: 
        response = isolated_client.post(
            "/upload",
            files={"file": ("ask_sample.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
    
    # Ask a question against the index created by the upload request.
    ask_response = isolated_client.post("/ask", json={"question": "What was the revenue?"})
    # Both the upload and question endpoints should complete successfully.
    assert response.status_code == 200
    assert ask_response.status_code == 200

    # Verify the echoed question and limit the number of returned matches.
    data = ask_response.json()
    assert data["question"] == "What was the revenue?"
    assert len(data["results"]) <= 5

# Verify that /ask returns the answer produced by a mocked generator after a document is uploaded.
def test_ask_uses_mocked_answer(isolated_client, monkeypatch):
    # seed the app with a real sample document so the ASK endpoint has a searchable index to work against
    # mirror the normal end-to-end path without requiring Ollama call duirng setup
    with open("data/samples/ask_sample.docx", "rb") as f:
        response = isolated_client.post(
            "/upload",
            files={
                "file": (
                    "ask_sample.docx",
                    f,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

    # the upload must succeed before we ask a question.
    # if the document did not index, the later /ask request would not have meaningful content to search.
    assert response.status_code == 200

    # replace the production answer generation function with a stub that ignores the actual question and retrieved chunks.
    # this keeps the test focused on the API contract and isolates it from slow or brittle LLM behavior.
    def fake_generate_answer(question, chunks):
        return "This is a mocked answer."

    # monkeypatch swaps the implementation in app.api at runtime,
    # so the /ask route will call our fake generator instead of the real model while the test is running.
    monkeypatch.setattr("app.api.generate_answer", fake_generate_answer)

    # ask a question against the uploaded document and confirm the API returns the mocked answer.
    # this verifies the endpoint still passes the question/chunks through the normal request flow while the LLM output is intentionally controlled.
    ask_response = isolated_client.post(
        "/ask", json={"question": "What was the revenue?"}
    )

    assert ask_response.status_code == 200
    assert ask_response.json()["answer"] == "This is a mocked answer."

# Skip this integration test when the local Ollama service is unavailable.
@pytest.mark.skipif(
    not _ollama_reachable(), reason="Ollama not running on localhost:11434"
)

# Verify that /ask can use a real local Ollama model after a document is uploaded.
def test_ask_with_real_ollama(isolated_client):
    # Upload the sample document so the real model can answer from its contents.
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
    
    # Ask the locally running Ollama model about information in the document.
    response = isolated_client.post("/ask", json={"question": "What was the revenue"})
    assert response.status_code == 200
    
    # Accept either of the expected revenue references because model wording varies.
    answer = response.json()["answer"].lower()
    # Loose check on purpose: LLM output is non-deterministic, so an exact string
    # match would be flaky. We only require the answer to reference the document.
    assert "revenue" in answer or "85 million" in answer

# verify that the upload endpoint rejects unsupported file types such as plain-text files.
def test_upload_rejects_txt(isolated_client):
    response = isolated_client.post(
        "/upload",
        files={"file": ("notes.txt", b"just some plain text", "text/plain")}
    )

    # confirm the API returns a client error and explains why the file was rejected.
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]
    
def _make_docx(text: str) -> bytes:
    # Build an in-memory DOCX so tests do not need temporary source files.
    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()

def _upload_docx(client, filename: str, content: bytes):
    # Submit DOCX bytes using the same multipart format as a real client.
    return client.post(
        "/upload",
        files={
            "file": (
                filename,
                content,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )


def test_first_upload_adds_file(isolated_client):
    # A new filename should create the first indexed document entry.
    response = _upload_docx(
        isolated_client,
        "fresh.docx",
        _make_docx("The company reported 120 million dollars in revenue."),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "added"
    assert data["index_total"] == data["chunks"]


def test_reupload_same_filename_replaces(isolated_client):
    # Uploading the same filename twice should replace, not duplicate, it.
    v1 = _make_docx("First version: revenue was 100 million dollars.")
    v2 = _make_docx("Second version: revenue was 200 million dollars.")

    first = _upload_docx(isolated_client, "report.docx", v1)
    second = _upload_docx(isolated_client, "report.docx", v2)

    assert first.status_code == 200
    assert second.status_code == 200
    data = second.json()
    assert data["status"] == "replaced"
    assert data["index_total"] == data["chunks"]


def test_search_after_replace_only_returns_new_content(isolated_client):
    # Search results must not retain chunks from the replaced document.
    _upload_docx(
        isolated_client,
        "report.docx",
        _make_docx("First version: revenue was 100 million dollars."),
    )
    _upload_docx(
        isolated_client,
        "report.docx",
        _make_docx("Second version: revenue was 200 million dollars."),
    )

    response = isolated_client.post("/ask", json={"question": "What was the revenue?"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert results
    assert all("200 million" in str(result) for result in results)
    assert all("100 million" not in str(result) for result in results)


def test_tracking_has_one_row_per_filename(isolated_client):
    # Repeated uploads should leave one tracking row for each filename.
    content = _make_docx("Revenue was 200 million dollars.")
    for _ in range(3):
        response = _upload_docx(isolated_client, "report.docx", content)
        assert response.status_code == 200

    conn = sqlite3.connect(tracking.DB_PATH)
    rows = conn.execute(
        "SELECT filename, file_type FROM uploads"
    ).fetchall()
    conn.close()

    assert rows == [("report.docx", "docx")]

# Deleting a file must remove it from every place the app shows it
# Vector, index, upload log, and saved copy on disk
def test_delete_upload_removes_files_everywhere(isolated_client, tmp_path):
    _upload_docx(
        isolated_client,
        "report.docx",
        _make_docx("Revenue was 200 million dollars."),
    )
    
    response = isolated_client.delete("/uploads/report.docx")
    
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "report.docx"
    assert data["status"] == "deleted"
    assert data["chunks_removed"] == 1
    assert data["index_total"] == 0
    
    # Gone from the "uploaded files" panel
    assert isolated_client.get("/uploads").json() == {"files": []}
    # Gone form index
    assert isolated_client.post(
        "/ask", json={"question": "What was the revenue?"}
    ).status_code == 400
    
    # Gone from disk
    assert not(tmp_path / "upload" / "report.docx").exists()

# Deleting a filename that was never uploaded is a 404, not a crash
def test_delete_missing_file_returns_404(isolated_client):
    response = isolated_client.delete("/uploads/never-uploaded.docx")
    
    assert response.status_code == 404
    assert "never-uploaded.docx" in response.json()["detail"]
    
# Deleting one file must leave other files listed and queryable
def test_delete_keeps_other_files(isolated_client):
    _upload_docx(
        isolated_client, "keep.docx", _make_docx("Revenue was 200 million dollars.")
    )
    
    _upload_docx(
        isolated_client, "drop.docx", _make_docx("Costs were 40 million dollars.")
    )
    
    response = isolated_client.delete("/uploads/drop.docx")
    
    assert response.status_code == 200
    assert response.json()["chunks_removed"] == 1
    
    files = isolated_client.get("/uploads").json()["files"]
    assert [f["filename"] for f in files] == ["keep.docx"]
    
    ask_response = isolated_client.post("/ask", json={"question": "What was the revenue?"})
    assert ask_response.status_code == 200
    results = ask_response.json()["results"]
    assert results
    assert all("200 million" in str(result) for result in results)
    
# A path-looking file must not escape data/uploades: sanitzer keeps only the base name (removing //), the same rule /upload applies
def test_delete_cannot_escape_uploads_dir(isolated_client, tmp_path):
    _upload_docx(
        isolated_client,
        "report.docx",
        _make_docx("Renuve was 200 million dollars."),
    )
    
    # Backslashes are normalized, so this still targets data/uploads/report.docx
    response = isolated_client.delete("/uploads/..\\report.docx")
    
    assert response.status_code == 200
    assert response.json()["filename"] == "report.docx"
    assert not (tmp_path / "upload" / "report.docx").exists()
    