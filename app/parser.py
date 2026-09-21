# Extract raw text from uploaded PDF and DOCX
import pdfplumber # For extracting data from PDF files
import docx # For extracting data from DOCX files
import os # For file path manipulation

# Determine which file type is being uploaded and call appropriate function
def extract_text_from_file(file_path: str) -> str:
    # edge case if file doesn"t exist
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file {file_path} does not exist.")
    
    # determine file type by getting the .pdf or .docx using os.path.split
    # [1] is the file type and lower() for consistency
    file_extension = os.path.splitext(file_path)[1].lower()
    
    if file_extension == ".pdf":
        return extract_pdf_text(file_path)
    elif file_extension == ".docx":
        return extract_docx_text(file_path)
    else:
        raise ValueError(f"Unsupported file format (pdf/docx only): {file_extension}")
    

def extract_pdf_text(file_path:str) -> str:
    # Extract text from PDF file
    text_content = []
    page_count = 0
    
    # open the pdf to read and close automatically when finishes
    with pdfplumber.open(file_path) as pdf:
        page_count = len(pdf.pages)
        
        # loop through each page number and extract text
        for page_num, page in enumerate(pdf.pages, start=1):
            # Extract text from page
            text = page.extract_text()
            
            # if there is text, append for citation
            if text:
                text_content.append(text)
    
    # combined all text so can return when finish going through the full pdf
    full_text = "\n\n".join(text_content)
    
    # Return the extracted text, number of pages, number of paragraphs, file name, and file type
    return {
        "text": full_text,
        "pages": page_count,
        "paragraphs": len(text_content),
        "file_name": os.path.basename(file_path),
        "file_type": "pdf"
    }
            

def extract_docx_text(file_path:str) -> str:
    # Extract text from DOCX file
    text_content = []
    
    # open the docx file and read its paragraphs
    doc = docx.Document(file_path)
    
    # loop through each paragraph and extract text
    for page in doc.paragraphs:
        # Extract text from paragraph
        text = page.text
        
        # if there is text, append for citation
        if text:
            text_content.append(text)
    
    # combined all text so can return when finish going through the full docx
    full_text = "\n\n".join(text_content)
    
    # Return the extracted text, number of pages, number of paragraphs, file name, and file type
    return {
        "text": full_text,
        "pages": None,
        "paragraphs": len(text_content),
        "file_name": os.path.basename(file_path),
        "file_type": "docx"
    }