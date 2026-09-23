# Store for managing the FAISS index and associated metadata
import faiss
import numpy as np
import os
import json

class VectorStore:
    # Initialize the VectorStore with a specified dimension for the vectors
    def __init__(self, dimension: int):
        self.dimension = dimension
        # Create a FAISS index for IP
        self.index = faiss.IndexFlatIP(dimension)
        # List to hold the original texts corresponding to the vectors in the index
        self.texts = []
        # Cretaes an empty list to store the source filename for each text chunk
        # Stays aligned with self.texts
        self.sources = []
        # Reserves a variable for storing the original vector data.
        # Could later be used to rebuild the FAISS index
        self.vectors = None
    
    # Add a list of texts and their corresponding vectors to the store
    def add(self, texts: list[str], vectors: np.ndarray, source=None) -> None:
        # Edge case: Ensure that the number of texts = the number of vectors
        if len(texts) != vectors.shape[0]:
            raise ValueError("The number of texts must match the number of vector rows")
        
        # Convert vector to float32 for FAISS compatibility
        vectors = vectors.astype("float32")
        # Add the vectors to the FAISS index
        self.index.add(vectors)
        # Extend the texts list with the new texts
        self.texts.extend(texts)
        # Extend the source list with the source filename for each text chunk
        self.sources.extend([source] * len(texts))
        # Store the vectors so the complete set can be reused or rebuilt later
        self.vectors = vectors if self.vectors is None else np.concatenate([self.vectors, vectors], axis=0)
    
    # Remove chunks owned by source and rebuild the index with the deleted vector rows(FAISS can't remove)
    def remove_source(self, source) -> int:
        # A missing source cannot match any stored chunk, so there is nothing to remove.
        if not source:
            return 0

        # Build a True/False mask: True means the chunk should remain in the store.
        keep = [s != source for s in self.sources]

        # Count how many chunks belong to the source being removed.
        removed = len(keep) - sum(keep)
        if removed == 0:
            return 0

        # Remove the matching texts and source names while preserving their alignment.
        self.texts = [t for t, k in zip(self.texts, keep) if k]
        self.sources = [s for s, k in zip(self.sources, keep) if k]

        # Keep only the corresponding vector rows. These vectors are needed to rebuild FAISS.
        kept = self.vectors[keep].astype("float32") # bool-list indexing works on numpy arrays

        # FAISS indexes do not support deleting rows here, so create a fresh index.
        fresh = faiss.IndexFlatIP(self.dimension)
        if len(kept):
            # Add the remaining vectors to the new index.
            fresh.add(kept)
        self.index = fresh
        # Keep the in-memory vector array synchronized with the rebuilt index.
        self.vectors = kept

        # Tell the caller how many chunks were deleted.
        return removed
        
    
    # Search for the top_k most similar vectors to the given user query vector
    def search(self, query: np.ndarray, top_k: int=5) -> list[dict]:
        # Edge case: Ensure index is not empty before searching
        if self.index.ntotal == 0:
            return []
        
        # Perform the search in the FAISS index
        # Convert query to float32 for FAISS compatibility
        query = query.reshape(1, -1).astype("float32")
        
        scores, indices = self.index.search(query, top_k)
        results = []
        for i in range(len(indices[0])):
            # Get the position of the found vector in the original texts list
            pos = indices[0][i]
            if pos == -1:
                continue
            results.append({
                # Text corresponding to the found vector
                "text": self.texts[pos],
                # Similarity score 
                "score": float(scores[0][i])
            })
        
        return results
        
    # Save the current state of the FAISS index to a file
    def save(self, file_path: str) -> None:
        # Ensure the directory exists before saving the index
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # Write the FAISS index to the file path
        faiss.write_index(self.index, file_path)
        # Write texts and source metadata to a sidecar file for persistence.
        # Its name must match the path used by load(): file_path + ".texts.json".
        with open(file_path + ".texts.json", "w", encoding="utf-8") as f:
            json.dump({"texts": self.texts, "sources": self.sources}, f)

    # Load the FAISS index from a file
    def load(self, file_path: str) -> None:
        # Read the FAISS index from the file path
        loaded_index = faiss.read_index(file_path)
        
        # Update the dimension and index with the loaded index
        self.dimension = loaded_index.d
        self.index = loaded_index
        
        # Read the texts from the separate file
        with open(file_path + ".texts.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Support the legacy format, which stored only a list of texts.
        if isinstance(data, list):
            self.texts = data
            self.sources = [None] * len(data)
        else:
            # Load both text content and source metadata from the current format.
            self.texts = data["texts"]
            self.sources = data.get("sources", [None] * len(self.texts))

        # Recover the vectors from the loaded IndexFlat so the index can be rebuilt later.
        self.vectors = loaded_index.reconstruct_n(0, loaded_index.ntotal).astype("float32")
        
        
        # Ensure that the number of texts matches the number of vectors in the index
        assert self.index.ntotal == len(self.texts), "index/text count mismatch - broken save?"