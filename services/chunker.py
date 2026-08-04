"""
Text Chunker Service
====================

Purpose: Split extracted transcript text into smaller, manageable chunks for embedding and retrieval.

This service handles the second step in the RAG pipeline:
  Extract text → Split into chunks

Architecture Flow:
  1. Receive raw text from parser service
  2. Split text into chunks (typically 500-1000 tokens)
  3. Preserve metadata (page numbers, paragraph numbers)
  4. Return list of chunks with metadata
  5. Pass chunks to embedding service

Why Chunking Matters:
  - LLMs have context limits (can't process entire 50-page transcript at once)
  - Smaller chunks = more precise retrieval
  - Enables citation of specific sections
  - Reduces noise in retrieval results

Chunking Strategy:
  - Split by paragraphs first (maintains semantic coherence)
  - Target size: 500-800 tokens per chunk
  - Overlap: 50-100 tokens between chunks (preserves context)
  - Preserve page numbers for citations
  - Keep related content together (Q&A pairs, sections)

Tech Stack:
  - Custom chunking logic (no external library needed)
  - Token counting (tiktoken or simple word count)

TODO List:
  - [ ] Implement chunk_text() function
      - Split by paragraphs
      - Respect token limits (500-800 tokens)
      - Add overlap between chunks (50-100 tokens)
      - Preserve page markers [Page X]
  - [ ] Implement smart chunking
      - Don't split in middle of sentences
      - Keep Q&A pairs together
      - Handle tables as single chunks
  - [ ] Add metadata tracking
      - Track source page for each chunk
      - Track paragraph numbers
      - Track character positions
  - [ ] Return structured output:
      {
          "chunks": [
              {
                  "text": "chunk content...",
                  "page": 3,
                  "paragraph": 2,
                  "char_start": 150,
                  "char_end": 850,
                  "token_count": 650
              }
          ],
          "total_chunks": 15,
          "source": "Amazon_Q1_2026.pdf"
      }
  - [ ] Add chunk size validation
      - Warn if chunks exceed 1000 tokens
      - Warn if chunks are too small (<200 tokens)
  - [ ] Add unit tests
      - Test with short text
      - Test with long text
      - Test with multi-page content
      - Test edge cases (empty text, single paragraph)
  - [ ] Handle special cases:
      - Tables (keep as single chunk)
      - Lists (keep together)
      - Speaker labels in transcripts (Q: / A:)

Example Usage:
    from services.chunker import chunk_text
    
    result = chunk_text(extracted_text, chunk_size=500, overlap=50)
    for chunk in result["chunks"]:
        print(f"Page {chunk['page']}: {chunk['text'][:100]}...")
"""

from typing import Dict, List, Any
import re

# overlap is the number of tokens to overlap between chunks to preserve context for retrieval.
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> Dict[str, Any]:
    """
    Split text into chunks for embedding.
    
    Args:
        text: Raw extracted text from parser
        chunk_size: Target number of tokens per chunk (default: 500)
        overlap: Number of overlapping tokens between chunks (default: 50)
        
    Returns:
        Dictionary containing:
            - chunks: List of chunk dictionaries with text and metadata
            - total_chunks: Total number of chunks created
            - source: Original filename (extracted from text markers)
            
    Raises:
        ValueError: If chunk_size or overlap are invalid
    """
    # Validate inputs
    if chunk_size < 100:
        raise ValueError("chunk_size must be at least 100 tokens")
  
    if overlap >= chunk_size:
        raise ValueError("overlap must be less than chunk_size")
    
    if not text or not text.strip():
        raise ValueError("Text cannot be empty")
    
    
    # Extract source filename from text markers
    source_match = re.search(r'\[Source: ([^\]]+)\]', text)
    source = source_match.group(1) if source_match else "unknown"

    # Split text into paragraphs
    paragraphs = text.split('\n\n')
    
    # Initialize chunk tracking
    chunks = []
    current_chunk = []
    current_tokens = 0
    current_page = 1
    current_paragraph = 0
    
    # Iterate through paragraphs and build chunks
    for para in paragraphs:
        # Check if paragraph contains page markers
        page_match = re.search(r'\[Page (\d+)]', para)
        if page_match:
            current_page = int(page_match.group(1))
            current_paragraph = 0
        
        # If adding this paragraph exceeds chunk size, save current chunk
        para_tokens = len(para.split())
        if current_tokens + para_tokens > chunk_size and current_chunk:
            # Save current chunk
            chunk_text = '\n\n'.join(current_chunk)
            chunks.append({
                'text': chunk_text,
                'page': current_page,
                'paragraph': current_paragraph,
                'token_count': current_tokens
            })
            
            # Start new chunk with overlap
            # Keep last few paragraphs for context
            current_chunk = current_chunk[-2:] if len(current_chunk) > 2 else current_chunk
            current_tokens = sum(len(p.split()) for p in current_chunk)
        
        # Add paragraph to current chunk
        current_chunk.append(para)
        current_tokens += para_tokens
        current_paragraph += 1
    
    # Don't forget the last chunk
    if current_chunk:
        chunk_text = '\n\n'.join(current_chunk)
        chunks.append({
            'text': chunk_text,
            'page': current_page,
            'paragraph': current_paragraph,
            'token_count': current_tokens
        })
    
    # Return structured result
    return {
        'chunks': chunks,
        'total_chunks': len(chunks),
        'source': source
    }


# helper functions
def count_tokens(text: str) -> int:
    """
    Count approximate number of tokens in text.
     
    For production, use tiktoken for accurate counting.
    For now, use word count as approximation (1 word ≈ 1.3 tokens).
    """
    # Simple approximation: words * 1.3
    return int(len(text.split()) * 1.3)
    

def find_sentence_boundary(text: str, position: int) -> int:
    """
    Find the nearest sentence boundary to avoid splitting mid-sentence.
    """
    if position < 0:
        position = 0
    if position >= len(text):
        return len(text)

    boundary_chars = '.!?\n'

    # Search backward for a nearby sentence boundary first
    for idx in range(position, -1, -1):
        if text[idx] in boundary_chars:
            # Return the index after the boundary and any trailing whitespace
            next_pos = idx + 1
            while next_pos < len(text) and text[next_pos].isspace():
                next_pos += 1
            return next_pos

    # If no previous boundary found, search forward
    for idx in range(position, len(text)):
        if text[idx] in boundary_chars:
            next_pos = idx + 1
            while next_pos < len(text) and text[next_pos].isspace():
                next_pos += 1
            return next_pos

    # Fall back to end of text
    return len(text)

def merge_small_chunks(chunks: List[Dict], min_size: int = 200) -> List[Dict]:
    """
    Merge chunks that are too small with adjacent chunks.
    
    Args:
        chunks: List of chunk dictionaries with 'text' and 'token_count' keys
        min_size: Minimum token count threshold (default: 200)
        
    Returns:
        List of merged chunks, with small chunks combined with adjacent chunks
    """
    if not chunks:
        return chunks
    
    merged = []
    i = 0
    
    while i < len(chunks):
        current_chunk = chunks[i].copy()
        
        # If current chunk is too small, merge with next chunk
        if current_chunk.get('token_count', 0) < min_size and i + 1 < len(chunks):
            next_chunk = chunks[i + 1].copy()
            
            # Merge text with paragraph separator
            merged_text = current_chunk['text'] + '\n\n' + next_chunk['text']
            merged_token_count = current_chunk.get('token_count', 0) + next_chunk.get('token_count', 0)
            
            # Keep metadata from current chunk, update token count
            current_chunk['text'] = merged_text
            current_chunk['token_count'] = merged_token_count
            
            # Skip next chunk since we merged it
            i += 2
        else:
            i += 1
        
        merged.append(current_chunk)
    
    return merged