"""
Embedding Service
=================

Purpose: Convert text chunks into vector embeddings for semantic search.

This service handles the third step in the RAG pipeline:
  Split into chunks → Generate embeddings

Architecture Flow:
  1. Receive list of text chunks from chunker service
  2. Convert each chunk into 384-dimensional vector using SentenceTransformer
  3. Return embeddings array with metadata
  4. Pass embeddings to FAISS index for storage

Why Embeddings Matter:
  - Convert text to numbers that represent meaning
  - Similar meanings = similar vectors (mathematically close)
  - Enables semantic search (find "revenue" even if word "revenue" not in text)
  - 384 dimensions captures semantic meaning efficiently

Model Choice: all-MiniLM-L6-v2
  - Fast: ~1000 sentences/second on CPU
  - Accurate: Good balance of speed and quality
  - Lightweight: Only 80MB model size
  - Free: No API costs, runs locally
  - Standard: 384-dimensional output vectors

Tech Stack:
  - SentenceTransformers: HuggingFace library for embeddings
  - all-MiniLM-L6-v2: Pre-trained model
  - NumPy: For vector operations

TODO List:
  - [ ] Initialize SentenceTransformer model
      - Load all-MiniLM-L6-v2 on startup
      - Cache model in memory (don't reload for each request)
      - Use CPU (no GPU required for this model)
      - Add model warmup on first load
  - [ ] Implement generate_embeddings() function
      - Accept list of text chunks
      - Batch process for efficiency
      - Return numpy array of shape (num_chunks, 384)
      - Handle empty chunks gracefully
  - [ ] Implement single embedding function
      - For query embedding (user questions)
      - Same model, single text input
  - [ ] Add batching logic
      - Process 32 chunks at a time (memory efficient)
      - Show progress for large batches (>100 chunks)
  - [ ] Add error handling
      - Handle model loading failures
      - Handle memory issues with very large batches
      - Validate input text (not empty, not too long)
  - [ ] Return structured output:
      {
          "embeddings": [[0.123, -0.456, ...], ...],  # 384-dim vectors
          "chunk_count": 15,
          "model": "all-MiniLM-L6-v2",
          "dimensions": 384
      }
  - [ ] Add caching
      - Cache embeddings to disk (avoid regenerating)
      - Check if embeddings already exist for file
      - Invalidate cache when source file changes
  - [ ] Add unit tests
      - Test embedding generation
      - Test batch processing
      - Test similarity (similar texts = similar vectors)
      - Test edge cases (empty text, very long text)
  - [ ] Performance optimization
      - Use model.encode() with show_progress_bar for large batches
      - Consider GPU acceleration if available
      - Normalize embeddings for cosine similarity

Example Usage:
    from services.embedding import generate_embeddings, get_query_embedding
    
    # Generate embeddings for chunks
    result = generate_embeddings(chunks)
    embeddings = result["embeddings"]  # Shape: (15, 384)
    
    # Generate embedding for user query
    query_vec = get_query_embedding("What risks did management mention?")
    # Shape: (384,) - single vector
"""

from typing import Dict, List, Any, Union
import numpy as np

# TODO: Import SentenceTransformer
# from sentence_transformers import SentenceTransformer
from sentence_transformers import SentenceTransformer


# Initialize model globally (load once on startup)
model = NotImplemented
def get_model():
    """
    Get or intialize the SentenceTransformer model.
    Lazy loading - only load when first needed;
    """
    global model
    if model is None:
        # Add logging
        print("Loading SentenceTransformer model...")
        model = SentenceTransformer('all-MiniLM-L6-v2')
        print("Model loaded successfully!")
    return model

def generate_embeddings(chunks: List[Dict[str, Any]], batch_size: int = 32) -> Dict[str, Any]:
    """
    Generate embeddings for list of text chunks.
    
    Args:
        chunks: List of chunk dictionaries from chunker service
                Each chunk must have 'text' key
        batch_size: Number of chunks to process at once (default: 32)
        
    Returns:
        Dictionary containing:
            - embeddings: numpy array of shape (num_chunks, 384)
            - chunk_count: Number of chunks processed
            - model: Model name used
            - dimensions: Embedding dimensions (384)
            
    Raises:
        ValueError: If chunks list is empty or invalid
        RuntimeError: If model fails to load
    """
    # Validate input
    if not chunks:
        raise ValueError("Chunks list cannot be empty")
    
    # # Extract text from chunks
    texts = [chunk.get('text') for chunk in chunks]
    
    # Filter out empty texts
    valid_indices = [i for i, text in enumerate(texts) if text and text.strip()]
    valid_texts = [texts[i] for i in valid_indices]

    if not valid_texts:
        raise ValueError("No valid text content in chunks")

    
    # Get model
    model = get_model()
    
    # Generate embeddings in batches
    all_embeddings = []

    for i in range(0, len(valid_texts), batch_size):
        batch = valid_texts[i:i + batch_size]
        
        # Generate embeddings for batch
        batch_embeddings = model.encode(
            batch,
            show_progress_bar=len(valid_texts) > 50, # Show progress for large batches
            convert_to_numpy=True,
            normalized_embeddings=True  # Normalize for cosine similarity
        )
    # Combined all batches
    embeddings = np.vstack(all_embeddings)
    
    # Create full embeddings array (including empty chunks)
    full_embeddings = np.zeros((len(chunks), 384))
    for idx, valid_idx in enumerate(valid_indices):
        full_embeddings[valid_idx] = embeddings[idx]

    # Return structured result
    return {
        'embeddings': full_embeddings,
        'chunk_count': len(chunks),
        'model': 'all-MiniLM-L6-v2',
        'dimensions': 384
    }


def get_query_embedding(query: str) -> np.ndarray:
    """
    Generate embedding for user query.
    
    Args:
        query: User's question (e.g., "What risks did management mention?")
        
    Returns:
        numpy array of shape (384,) - single embedding vector
        
    Raises:
        ValueError: If query is empty
    """
    # Validate input
    if not query or not query.strip():
        raise ValueError("Query cannot be empty")

    # Get model
    model = get_model()

    # Generate embedding
    embedding = model.encode(
        query,
        convert_to_numpy=True,
        normalized_embeddings=True # Normalize for cosine similarity
    )

    return embedding


# TODO: Add utility functions
def compute_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
    """
    Compute cosine similarity between two embeddings.
     
    Returns:
        Float between -1 and 1 (1 = identical, 0 = unrelated, -1 = opposite)
     """
    # Since embeddings are normalized, cosine similarity = dot product
    return float(np.dot(embedding1, embedding2))
    

def find_most_similar(query_embedding: np.ndarray, 
                      embeddings: np.ndarray, 
                      top_k: int = 5) -> List[int]:
    """
    Find indices of most similar embeddings to query.
    
    Args:
        query_embedding: Shape (384,)
        embeddings: Shape (num_chunks, 384)
        top_k: Number of top results to return
       
    Returns:
        List of indices of most similar chunks
    """
    # Compute cosine similarities
    similarities = np.dot(embeddings, query_embedding)
    
    # Get top k indices
    top_indices = np.argsort(similarities)[-top_k:][::-1]
    
    return top_indices.tolist()

def save_embeddings(embeddings: np.ndarray, file_path: str):
    """
    Save embeddings to disk for caching.
    """
    np.save(file_path, embeddings)


def load_embeddings(file_path: str) -> np.ndarray:
    """
    Load embeddings from disk cache.
    """
    return np.load(file_path)