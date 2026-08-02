"""
PDF and DOCX Parser Service
============================

Purpose: Extract raw text from uploaded earnings transcript files (PDF and DOCX formats).

This service handles the first step in the RAG pipeline:
  Upload earnings transcript → Extract text

Architecture Flow:
  1. Receive uploaded file (PDF or DOCX)
  2. Extract text content using appropriate library
  3. Return raw text with metadata (page numbers, paragraphs)
  4. Pass text to chunker service for splitting

Tech Stack:
  - PyPDF2 or pdfplumber: For PDF text extraction
  - python-docx: For DOCX text extraction

TODO List:
  - [ ] Implement extract_text_from_pdf() function
      - Handle multi-page PDFs
      - Preserve page numbers for citation tracking
      - Handle encrypted PDFs gracefully
      - Extract text while maintaining paragraph structure
  - [ ] Implement extract_text_from_docx() function
      - Extract paragraphs and maintain structure
      - Handle tables if present in transcripts
  - [ ] Add error handling for corrupted files
  - [ ] Add file validation (check file extension, size limits)
  - [ ] Add logging for debugging extraction issues
  - [ ] Return structured output with metadata:
      {
          "text": "extracted text...",
          "pages": 10,
          "paragraphs": 45,
          "source": "Amazon_Q1_2026.pdf"
      }
  - [ ] Add unit tests for both PDF and DOCX extraction
  - [ ] Handle edge cases:
      - Scanned PDFs (may need OCR in future)
      - Password-protected files
      - Empty files
      - Very large files (>100 pages)

Example Usage:
    from services.parser import extract_text
    
    result = extract_text("uploads/Amazon_Q1_2026.pdf")
    print(result["text"])  # Raw transcript text
    print(result["pages"])  # Number of pages
"""

import re
from typing import Dict, Any
import os

from pdfplumber import PDF
from docx import Documents


def extract_text(file_path: str) -> Dict[str, Any]:
    """
    Extract text from uploaded file (PDF or DOCX).
    
    Args:
        file_path: Path to the uploaded file
        
    Returns:
        Dictionary containing:
            - text: Extracted raw text
            - pages: Number of pages (for PDFs)
            - paragraphs: Number of paragraphs
            - source: Original filename
            - file_type: 'pdf' or 'docx'
            
    Raises:
        ValueError: If file format is not supported
        FileNotFoundError: If file doesn't exist
    """

    # edge case to handle non-existent files
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    

    # determine file type with [1] (ex: .pdf, .docx) and convert to lowercase for consistency
    file_extension = os.path.splitext(file_path)[1].lower()
    
    # determine which extraction function based on file type
    if file_extension == '.pdf':
        return extract_text_from_pdf(file_path)
    elif file_extension == '.docx':
        return extract_text_from_docx(file_path)
    else:
        raise ValueError(f"Unsupported file format (pdf/docx only): {file_extension}")


def extract_text_from_pdf(file_path: str) -> Dict[str, Any]:
    # Extract text from PDF file using pdfplumber
    text_content = []
    page_count = 0
    
    with pdfplumber.open(file_path) as pdf:
        page_count = len(pdf.pages)
        
        # loop through each page number and extract text
        for page_num, page in enumerate(pdf.pages, start=1):
            # Extract text from each page
            text = page.extract_text()
            
            if text:
                # Add page marker for citation tracking
                text_content.append(f"[Page {page_num}]\n{text}")
    
    full_text = "\n\n".join(text_content)
    
    return {
        'text': full_text,
        'pages': page_count,
        'paragraphs': len(text_content),
        'source': os.path.basename(file_path),
        'file_type': 'pdf'
    }
            
        
    

def extract_text_from_docx(file_path: str) -> Dict[str, Any]:
    # Extract text from DOCX file using python-docx
    doc = Document(file_path)
    paragraphs = []
    
    for para in doc.paragraphs:
        if para.text.strip(): # Skip empty paragraphs
            paragraphs.append(para.text) # append non-empty paragraphs to the list

    full_text = "\n\n".join(paragraphs)
    
    return {
        'text': full_text,
        'pages': 0, # DOCX doesn't have fixed pages
        'paragraphs': len(paragraphs),
        'source': os.path.basename(file_path),
        'file_type': 'docx'
    }

# Utility functions

def validate_file(file_path: str) -> bool:
    # Validate uploaded file before processing
    # Checks if file exist, file extension is supported, file size is reasonable, and file is not corrupted
    if not os.path.exists(file_path):
        return False
    
    file_extension = os.path.splitext(file_path)[1].lower()
    if file_extension not in ['.pdf', '.docx']:
        return False
    
    file_size = os.path.getsize(file_path)
    if file_size > 50 * 1024 * 1024: # 50MB limit
        return False
    
    # future check if file is corrupted can be added here
    return True


def clean_text(text: str) -> str:
    # Clean extracted text removing whitespace, special characters, header/footer repetitions
    cleaned_text = ' '.join(char for char in text if char.isalnum()) 
    
    return cleaned_text