import os

from fastapi import FastAPI, File, HTTPException, UploadFile

from app.chunker import chunk_text
from app.embeddings import embed_query, embed_texts
from app.parser import extract_text_from_file
from app.store import VectorStore
from app.llm import generate_answer
from pydantic import BaseModel


# Initialize the FastAPI app
app = FastAPI()

UPLOAD_DIR = "data/uploads"
INDEX_PATH = "data/indexes/default.index"
ALLOWED_EXTENSIONS = {".pdf", ".docx"}

# Initialize the vector store, reloading the last-persisted index so uploads
# survive a server restart.
store = VectorStore(dimension=384)
if os.path.exists(INDEX_PATH):
    try:
        store.load(INDEX_PATH)
    except Exception as e:
        print(f"Warning: could not load existing index ({e}); starting empty.")


@app.post("/upload")
def upload_file(file: UploadFile = File(...)):
    # Accept PDF/DOCX --> parse --> chunk --> embed --> store
    # 1. Validate the file type BEFORE saving anything to disk
    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type \"{extension or 'none'}\". Only PDF and DOCX are allowed.",
        )

    # 2. Sanitize the filename so uploads can"t escape data/uploads (path traversal)
    safe_name = os.path.basename((file.filename or "").replace("\\", "/"))
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    upload_path = os.path.join(UPLOAD_DIR, safe_name)

    try:
        # 3. Stream the upload to disk
        with open(upload_path, "wb") as f:
            f.write(file.file.read())

        # 4. Run the pipeline: parse --> chunk --> embed --> store
        parsed_text = extract_text_from_file(upload_path)
        chunked_text = chunk_text(parsed_text["text"])

        # Separate the chunked text into individual chunk strings
        texts = [c["text"] for c in chunked_text["chunks"]]
        embedded_text = embed_texts(texts)

        store.add(texts, embedded_text)
        store.save(INDEX_PATH)

        return {
            "filename": safe_name,
            "chunks": chunked_text["total_chunks"],
            "pages": parsed_text.get("pages"),
            "index_total": store.index.ntotal,
        }
    except (FileNotFoundError, ValueError) as e:
        # Expected user-facing failures => clean 400 instead of a 500
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        file.file.close()

# Pydantic model for the /ask request body: {"question": "..."}
class AskRequest(BaseModel):
    question: str


@app.post("/ask")
def user_asked(request: AskRequest):
    # 1. Validate inputs
    query = request.question.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    # Queries are search instructions, not documents to index. Chunking a
    # query would create multiple searches and make the combined result less
    # meaningful. Limit oversized input instead; document text is chunked
    # during upload before it is embedded and stored.
    if len(query) > 10_000:
        raise HTTPException(
            status_code=400,
            detail="Query is too long. Please limit it to 10,000 characters.",
        )

    # Only ask once something has been uploaded/indexed
    if store.index.ntotal == 0:
        raise HTTPException(
            status_code=400,
            detail="No transcripts uploaded yet. Upload a file first.",
        )

    # 2. Embed the query in the same space as the stored document chunks
    query_embedding = embed_query(query)

    # 3. Search the top-5 most similar chunks from the pdf/docx
    results = store.search(query_embedding, top_k=5)
    
    # 4. Call the LLM to form the answer to the user
    answer = generate_answer(query, results)
    
    # 5. Return the echo of the question + the retrieved chunks (auto-JSON)
    return {
        "question": query,
        "answer": answer,
        "results": results,
    }
    
# GET because we are retrieving info on status    
@app.get("/health")
def health_check():
    # Cheap "alive" check: proves the process responds and reports how many
    # chunks are indexed, without loading the model or doing a search.
    return {"status": "ok", "index_total": store.index.ntotal}