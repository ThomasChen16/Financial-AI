import { useState, useEffect } from 'react'
import { uploadFile, ask, health, listUploads, deleteUpload } from "./api";
import "./App.css";

// Ready-made questions shown when the user clicks the "?" help button.
const SUGGESTED_QUESTIONS = [
  "What was the reported revenue and how did it change year over year?",
  "What were the main financial results — profit, margins, cash flow?",
  "What key risks or challenges did management mention?",
  "What were the main growth drivers this quarter?",
  "What guidance or outlook did the company give for the future?",
  "Did management mention any headwinds or market conditions?",
  "What are the key announcements from the call?",
  "How does this quarter compare to the previous one?",
];

const appImage = "/images/ai-financial-advisor-icon.jpg";

export default function App() {
  // The file selected by the user for upload, or null when no file is selected.
  const [file, setFile] = useState(null);
  // The question entered by the user.
  const [question, setQuestion] = useState("");
  // The answer returned by the API for the current question.
  const [answer, setAnswer] = useState("");
  // Search or retrieval results returned by the API.
  const [results, setResults] = useState([]);
  // True while an upload or ask request is in flight (disable buttons).
  const [busy, setBusy] = useState(false);
  // The name of the most recently indexed file.
  const [uploadedName, setUploadedName] = useState("");
  // True while the "?" suggestion panel is open.
  const [showSuggestions, setShowSuggestions] = useState(false);
  // Status message plus its visual kind: "info" | "success" | "error" | "pending".
  const [status, setStatusState] = useState({ text: "Checking connection...", kind: "info" });
  const setStatus = (text, kind = "info") => setStatusState({ text, kind });
  // Stores the files indexed by the backend for upload history display.
  const [uploadedFiles, setUploadedFiles] = useState([])
  // Filename currently being deleted, so only that row's button shows as busy.
  const [deletingName, setDeletingName] = useState("")

  // Check on load that the backend is reachable so a missing server is
  // reported immediately instead of failing silently on the first click.
  useEffect(() => {
    let cancelled = false;
    health().then((h) => {
      if (cancelled) return;
      if (h.ok) {
        setStatus(`Connected — ${h.data.index_total} chunks indexed`, "success");
      } else {
        setStatus("Backend offline — start uvicorn and refresh", "error");
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);
  
  // Load previously indexed files so the upload history can be shown.
  useEffect(() => {
    let cancelled = false;

    listUploads().then((r) => {
      if (cancelled) return;
      if (r.ok) setUploadedFiles(r.data.files || []);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  // Prevent the form from reloading the page, then upload the selected file.
  async function onUpload(event) {
    event.preventDefault();

    // There is nothing to upload until the user selects a file.
    if (!file) return;

    setBusy(true);
    setStatus("Uploading and indexing...", "pending");
    try {
      // Send the file to the API and update the UI with the result.
      const r = await uploadFile(file);
      if (r.ok) {
        setUploadedName(file.name);
        setStatus(`Indexed ${r.data.chunks} chunks — ${r.data.index_total} total in index`, "success");
        // Refresh the "Uploaded files" panel so the new/updated file appears right away.
        listUploads().then((list) => {
          if (list.ok) setUploadedFiles(list.data.files || []);
        });
      } else {
        setStatus(`Upload failed: ${r.data.detail}`, "error");
      }
    } catch (error) {
      setStatus(`Upload error: ${error.message}`, "error");
    } finally {
      setBusy(false);
    }
  }

  // Delete the uploaded file from the backend and refresh the frontend on every place that showed it (panel, chunk counter, and last indexed note)
  async function onDelete(file) {
    const confirmed = window.confirm(
      `Delete "${file.filename}"? Its indexed chunks are removed and you will need to upload it again to ask about it.`
    );
    // if cancel don't delete
    if (!confirmed) return;

    setDeletingName(file.filename);
    setStatus(`Deleting ${file.filename}...`, "pending");

    try {
      const r = await deleteUpload(file.filename, file.file_type);
      if (!r.ok) {
        setStatus(`Delete failed: ${r.data.detail}`, "error");
        return;
      }

      // re-read the panel from the backend, which is the source of truth
      const list = await listUploads();
      if (list.ok) setUploadedFiles(list.data.files || []);

      // the last index not emust not keep point at a delete file
      setUploadedName((name) => (name === file.filename ? "" : name));

      // with nothign left indexed, the answer/evidence on screen from the delete file should be empty
      if (r.data.index_total === 0) {
        setAnswer("")
        setResults([]);
      }

      setStatus(`Deleted ${file.filename} - ${r.data.index_total} chunks indexed`, "success");
    } catch (error) {
      setStatus(`Delete error: ${error.message}`, "error")
    } finally {
      setDeletingName("");
    }
  }

  // Shared by the Ask form and the suggestion chips: sends a query to the API
  // and updates the answer, evidence, and status.
  async function submitAsk(text) {
    const query = (text || "").trim();

    // There is nothing to ask until the user asks a question.
    if (!query) return;

    setBusy(true);
    setAnswer("");
    setResults([]);
    setStatus("Thinking...", "pending");
    try {
      // Send user query to the API and update the UI with the result.
      const r = await ask(query);
      if (r.ok) {
        setAnswer(r.data.answer);
        setResults(r.data.results);
        setStatus("Answered", "success");
      } else {
        setStatus(`Ask failed: ${r.data.detail}`, "error");
      }
    } catch (error) {
      setStatus(`Ask error: ${error.message}`, "error");
    } finally {
      setBusy(false);
    }
  }

  async function onAsk(event) {
    event.preventDefault();
    await submitAsk(question);
  }

  // A suggestion chip fills the input and asks right away (one click).
  function useSuggestion(text) {
    setQuestion(text);
    setShowSuggestions(false);
    submitAsk(text);
  }

  // format ISO timestamps into a short local time like "Sep 23, 10:30 AM"
  function formatUploadedAt(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }
  
  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          {appImage ? (
            <img className="brand-mark" src={appImage} alt="" aria-hidden="true" />
          ) : (
            <span className="brand-mark" aria-hidden="true"></span>
          )}
          <div className="brand-text">
            <h1>Financial AI</h1>
            <p className="tagline">Ask questions about your earnings transcripts</p>
          </div>
        </div>
        <div className={`status-pill ${status.kind}`} role="status" aria-live="polite">
          {busy && <span className="spinner" aria-hidden="true" />}
          <span className="status-dot" aria-hidden="true" />
          <span>{status.text}</span>
        </div>
      </header>

      <main className="app-main">
        <div className="app-content">
          <div className="grid">
            <section className="card">
              <div className="card-title">
                <h2>1 · Upload a transcript</h2>
              </div>
              <form onSubmit={onUpload} className="upload-form">
                <label className="file-label">
                  <input type="file" accept=".pdf,.docx" disabled={busy}
                        onChange={(e) => setFile(e.target.files[0])} />
                  <span className={`file-chip ${file ? "has-file" : ""}`}>
                    {file ? `✓ ${file.name}` : "Choose a .pdf or .docx file"}
                  </span>
                </label>
                <button className="btn btn-primary" type="submit" disabled={busy || !file}>
                  Upload
                </button>
              </form>
              {uploadedName && <p className="uploaded-note">Last indexed: {uploadedName}</p>}
            </section>

            <section className="card">
              <div className="ask-head">
                <div className="card-title">
                  <h2>2 · Ask a question</h2>
                </div>
                <button type="button" className="help-button"
                        onClick={() => setShowSuggestions(!showSuggestions)}
                        aria-label="Show suggested questions"
                        aria-expanded={showSuggestions}
                        aria-controls="suggestion-panel"
                        title="Need ideas? Show suggested questions">
                  ?
                </button>
              </div>
              <form onSubmit={onAsk} className="ask-form">
                <input className="ask-input" value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      placeholder="Ask about the document..." disabled={busy} />
                <button className="btn btn-primary" type="submit" disabled={busy || !question.trim()}>
                  Ask
                </button>
              </form>
              {showSuggestions && (
                <div className="suggestions" id="suggestion-panel">
                  <p className="suggestions-label">Stuck? Try one of these:</p>
                  <ul className="suggestion-list">
                    {SUGGESTED_QUESTIONS.map((suggestion) => (
                      <li key={suggestion}>
                        <button type="button" className="question-chip" disabled={busy}
                                onClick={() => useSuggestion(suggestion)}>
                          {suggestion}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          </div>

          <div className="stack">
            <section className="card answer-card">
              <div className="card-title">
                <h2>Answer</h2>
              </div>
              {answer && <p className="answer-text">{answer}</p>}
            </section>

            <section className="card evidence-card">
              <div className="card-title evidence-head">
                <h2>Evidence</h2>
                {results.length > 0 && <span className="count-badge">{results.length} retrieved</span>}
              </div>
              {results.length > 0 ? (
                <ol className="evidence-list">
                  {results.map((r, i) => (
                    <li key={i} className="evidence-item">
                      <span className="evidence-index" aria-hidden="true">{i + 1}</span>
                      <span className="evidence-score">{r.score.toFixed(3)}</span>
                      <p className="evidence-text">{r.text}</p>
                    </li>
                  ))}
                </ol>
              ) : null}
            </section>
          </div>
        </div>

        <aside className="card files-card" aria-label="Uploaded files">
          <div className="card-title files-head">
            <h2>Uploaded files</h2>
            {uploadedFiles.length > 0 && (
              <span className="count-badge">
                {uploadedFiles.length} {uploadedFiles.length === 1 ? "file" : "files"}
              </span>
            )}
          </div>
          {uploadedFiles.length > 0 ? (
            <ul className="file-list">
              {uploadedFiles.map((f) => (
                <li key={`${f.filename}-${f.file_type}`} className="file-row">
                  <span className="file-type-badge">{f.file_type.toUpperCase()}</span>
                  <span className="file-info">
                    <span className="file-name" title={f.filename}>{f.filename}</span>
                    <span className="file-meta">
                      {f.chunk_count} chunk{f.chunk_count === 1 ? "" : "s"} · {formatUploadedAt(f.uploaded_at)}
                    </span>
                  </span>

                  <button
                    type="button"
                    className="file-delete"
                    onClick={() => onDelete(f)}
                    disabled={busy || deletingName === f.filename}
                    aria-label={`Delete ${f.filename}`}
                    title={`Delete ${f.filename}`}
                  >
                    {deletingName === f.filename ? (
                      <span className="spinner" aria-hidden="true" />
                    ) : (
                      <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
                        <path
                          d="M4 7h16M10 11v6M14 11v6M6 7l1 12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-12M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1.8"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                      </svg>
                    )}
                  </button>
                  
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty-state">No files uploaded yet.</p>
          )}
        </aside>
      </main>

      <footer className="app-footer">
        Runs 100% locally · FAISS retrieval + Ollama generation
      </footer>
    </div>
  );
}