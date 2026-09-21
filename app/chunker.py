# Split extracted text into chunks for processing

# overlap helps maintain context between chunks
# split text into chunks of chunk_size characters
def chunk_text(text:str, chunk_size: int=500, overlap: int=50) -> dict:
    # validate chunk_size and overlap
    if chunk_size < 100:
        raise ValueError("chunk_size must be at least 100 characters.")
    
    if overlap >= chunk_size:
        raise ValueError("overlap must be less than chunk_size.")
    
    if not text or not text.strip():
        raise ValueError("text cannot be empty.")

    chunks = []
    start = 0
    index = 0
    
        
    while start < len(text):
        end = start + chunk_size  # cut point for the chunk
        
        # for leftover text that is less than chunk_size, so just immediately add it as a chunk and break the loop
        if end >= len(text):
            chunks.append({"text": text[start:], "index": index})
            break
        
        # find the last whitespace character before the end point to avoid cutting words in half
        while end > start and not text[end].isspace():
            end -= 1 
        
        # prevent the while loop from going in front of end point, if it does, just use the original end point    
        if end == start:
            end = start + chunk_size
        
        chunks.append({"text": text[start:end], "index": index})
        
        start = end - overlap # move the start point forward like a sliding window
        index += 1 # increment the index for the next chunk
        
    
    return {
        "chunks": chunks,
        "total_chunks": len(chunks)
    }
        
         

    