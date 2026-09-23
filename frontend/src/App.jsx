import { useState, useEffect } from 'react'
import { uploadFile, ask, health } from "./api";
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
      } else {
        setStatus(`Upload failed: ${r.data.detail}`, "error");
      }
    } catch (error) {
      setStatus(`Upload error: ${error.message}`, "error");
    } finally {
      setBusy(false);
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

      <main>
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
      </main>

      <footer className="app-footer">
        Runs 100% locally · FAISS retrieval + Ollama generation
      </footer>
    </div>
  );
}