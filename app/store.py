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
    
    # Add a list of texts and their corresponding vectors to the store
    def add(self, texts: list[str], vectors: np.ndarray) -> None:
        # Edge case: Ensure that the number of texts = the number of vectors
        if len(texts) != vectors.shape[0]:
            raise ValueError("The number of texts must match the number of vector rows")
        
        # Convert vector to float32 for FAISS compatibility
        vectors = vectors.astype("float32")
        # Add the vectors to the FAISS index
        self.index.add(vectors)
        # Extend the texts list with the new texts
        self.texts.extend(texts)
        
    
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
        # Write the texts list to a separate sidecar file for persistence
        # (name must match the one load() reads: file_path + ".texts.json")
        with open(file_path + ".texts.json", "w", encoding="utf-8") as f:
            json.dump(self.texts, f)

    # Load the FAISS index from a file
    def load(self, file_path: str) -> None:
        # Read the FAISS index from the file path
        loaded_index = faiss.read_index(file_path)
        
        # Update the dimension and index with the loaded index
        self.dimension = loaded_index.d
        self.index = loaded_index
        
        # Read the texts from the separate file
        with open(file_path + ".texts.json", "r", encoding="utf-8") as f:
            self.texts = json.load(f)
        
        # Ensure that the number of texts matches the number of vectors in the index
        assert self.index.ntotal == len(self.texts), "index/text count mismatch - broken save?"