# convert text chunks into vector embeddings for semantic search and retrieval
from sentence_transformers import SentenceTransformer
import numpy as np


model = None # default value for the model

# initialize the model for embedding generation
def get_model():
    global model # global variable to store the model instance
    if model is not None:
        return model
    
    print("Loading the model...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    return model

# convert text into vector embeddings
def embed_texts(chunks: list[str]) -> np.ndarray:
    # get the model
    model = get_model()
    
    # validate the text input
    if not chunks:
        raise ValueError("Chunks list is empty.")
    
    # generate embeddings for the chunk list and convert to numpy array for easier handling afterwards
    embeddings = model.encode(chunks, convert_to_numpy=True)
    # normalize to match the chunk embeddings for cosine similarity
    embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    
    return embeddings
    
# when user inputs a query, convert it into vector embeddings for semantic search and retrieval
def embed_query(text:str) -> np.ndarray:
    # get the model
    model = get_model()
    
    # validate the text input
    if not text or not text.strip():
        raise ValueError("Query text cannot be empty.")
    
    # generate embeddings for the query and convert to numpy array for easier handling afterwards
    embedding = model.encode(text, convert_to_numpy=True)
    # normalize the embedding vector for cosine similarity
    # `embedding` is a 1-D vector, so normalize by its single overall norm.
    embedding = embedding / np.linalg.norm(embedding, keepdims=True)
    
    return embedding
    