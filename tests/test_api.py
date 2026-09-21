# Automatically test is the endpoints in api.py works
from fastapi.testclient import TestClient
from app.api import app, VectorStore
import pytest
import socket

# reusable function designed to set up baseline state environment before a test runs and cleanning it up afterwards
# tmp_path creates a new temp folder on disk for each test and deletes it after
@pytest.fixture
def isolated_client(monkeypatch, tmp_path):
    # Swap out the shared production store for a brand-new, empty one
    fresh_store = VectorStore(dimension=384)
    # Go to app.api find variable store and replace it with fresh_store
    monkeypatch.setattr("app.api.store", fresh_store)
    
    # Redirect where /uploda writes file and saves the index
    monkeypatch.setattr("app.api.UPLOAD_DIR", str(tmp_path / "upload"))
    monkeypatch.setattr("app.api.INDEX_PATH", str(tmp_path / "indexes" / "default.index"))
    
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
    
