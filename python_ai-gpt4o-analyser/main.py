import os
import sys
import json
import re
import pandas as pd
import openai
import pdfplumber
from striprtf.striprtf import rtf_to_text
from dotenv import load_dotenv
import PyPDF2  # Add this import at the top

# Load environment variables from .env file
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

########################
# 1. Extract Text from PDF and RTF
########################

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file using multiple methods."""
    try:
        # First try PyPDF2
        text_content = []
        with open(pdf_path, 'rb') as file:
            print(f"\nProcessing PDF: {pdf_path}")
            
            # Try PyPDF2 first
            try:
                pdf_reader = PyPDF2.PdfReader(file)
                num_pages = len(pdf_reader.pages)
                print(f"Number of pages: {num_pages}")
                
                for i, page in enumerate(pdf_reader.pages, 1):
                    try:
                        text = page.extract_text() or ""
                        if not text.strip():
                            print(f"Warning: PyPDF2 - Page {i} appears to be empty or unreadable")
                        else:
                            text_content.append(text)
                            print(f"\n--- Page {i} Content {'='*40}")
                            print(text[:500] + "..." if len(text) > 500 else text)
                            print(f"{'='*50}\n")
                    except Exception as e:
                        print(f"Warning: PyPDF2 - Error extracting page {i}: {str(e)}")
                
                if not text_content:  # If PyPDF2 failed to extract any text
                    raise Exception("No text extracted with PyPDF2")
                    
            except Exception as e:
                print(f"PyPDF2 extraction failed: {str(e)}")
                print("Falling back to pdfplumber...")
                
                # Fall back to pdfplumber
                with pdfplumber.open(pdf_path) as pdf:
                    num_pages = len(pdf.pages)
                    print(f"Number of pages: {num_pages}")
                    
                    for i, page in enumerate(pdf.pages, 1):
                        try:
                            text = page.extract_text() or ""
                            if not text.strip():
                                print(f"Warning: pdfplumber - Page {i} appears to be empty or unreadable")
                            else:
                                text_content.append(text)
                                print(f"\n--- Page {i} Content {'='*40}")
                                print(text[:500] + "..." if len(text) > 500 else text)
                                print(f"{'='*50}\n")
                        except Exception as e:
                            print(f"Warning: pdfplumber - Error extracting page {i}: {str(e)}")
        
        full_text = "\n".join(text_content)
        if not full_text.strip():
            print("Warning: No text was extracted from the PDF using either method!")
            # You might want to add additional PDF extraction methods here
            
        return full_text
        
    except Exception as e:
        print(f"Error extracting text from PDF {pdf_path}: {str(e)}")
        return ""

def extract_text_from_rtf(rtf_path):
    """Extract text from an RTF file using striprtf."""
    with open(rtf_path, 'r', encoding='utf-8') as file:
        rtf_content = file.read()
    return rtf_to_text(rtf_content)

########################
# 2. Build Prompt with Detailed Instructions
########################

def build_prompt(document_text, doc_id):
    """
    This prompt enforces specific categories for each field.
    If GPT is uncertain, it can return "Unknown" or "Other" where appropriate.
    """
    # Calculate approximate tokens (rough estimate: 4 chars = 1 token)
    max_text_tokens = 20000  # Leave room for prompt and response
    max_text_chars = max_text_tokens * 4
    
    # Truncate document_text if too long
    if len(document_text) > max_text_chars:
        print(f"Warning: Document text too long ({len(document_text)} chars). Truncating to {max_text_chars} chars...")
        document_text = document_text[:max_text_chars] + "\n[Text truncated due to length...]"

    prompt = f"""
You are given the text of a legal document. 
Your task is to extract the following information and return it as valid JSON.
If you are not sure, respond with "Unknown" or "Other" where appropriate.

Important Context about HIPAA Coverage:
Only "covered entities" have to comply with the HIPAA Privacy Rule. Most notably, this includes:
(i) health insurance organizations
(ii) health care providers (such as doctors and hospitals)
(iii) health care clearinghouses (entities that process health information into a standardized format, such as billing services)
(iv) business associates of covered entities (which perform actions on health data on behalf of covered entities, such as data analytics)

Return these JSON fields exactly:

1. DocumentID
2. PartiesInvolved
3. KindOfPersonalData
4. DocumentType
5. DateOfDocumentOrCase

Below are the recognized categories for certain fields:

- DocumentID:
  Format is "doc-x-xx" (all lowercase, e.g. "doc-1-01"). 
  If you cannot find a suitable ID in the text, return the doc_id argument as fallback.

- PartiesInvolved (choose one; if multiple, pick the one that best fits or "Other"):
  Note: A "Covered Entity" refers to health insurance organizations, healthcare providers, healthcare clearinghouses, or their business associates.
  1) "Individual vs. Healthcare Provider (Covered Entity)"
  2) "Individual vs. Health Insurance Plan (Covered Entity)"
  3) "Government vs. Healthcare Entity (Covered Entity)"
  4) "Business Associate of Covered Entity (Covered Entity)"
  5) "Healthcare Provider vs. Healthcare Provider (Covered Entity)"
  6) "Neither Party is a Covered Entity"
  7) "Other"

- KindOfPersonalData (choose all that apply; return as a list):
  1) "Personal Health Information (including biometrics, DNA)"
  2) "Demographics"
  3) "Educational or Professional Licensing Data"
  4) "Financial Data"
  5) "Real Estate Information"
  6) "Credit Information"
  7) "Internet or Network Activity"
  8) "Geo-location or GPS Data"
  9) "Legal or Criminal Information"
  10) "Social Media or Online Content"
  11) "Not applicable"
  12) "Medical information not covered by HIPAA"
  13) "Other"

- DocumentType (choose all that apply; return as a list):
  1) "Court Rulings/Decisions"
  2) "Legal Briefs"
  3) "Depositions"
  4) "Expert Witness Reports"
  5) "Settlement Agreements"
  6) "Legal Notices"
  7) "Vitae"
  8) "Not known"
  9) "Other"

- DateOfDocumentOrCase (choose one):
  1) "2019"
  2) "2020"
  3) "2021"
  4) "2022"
  5) "2023"
  6) "2024"
  7) "Not known"
  8) "Other"

Document ID from filename: {doc_id}

Here is the document text:

\"\"\" 
{document_text}
\"\"\"

Please respond with valid JSON only. Example format:

{{
  "DocumentID": "doc-1-01",
  "PartiesInvolved": "Individual vs. Healthcare Provider (Covered Entity)",
  "KindOfPersonalData": ["Personal Health Information (including biometrics, DNA)", "Financial Data"],
  "DocumentType": ["Legal Briefs"],
  "DateOfDocumentOrCase": "2023"
}}
"""
    return prompt

########################
# 3. Call GPT-4 (or Another Model) API
########################

def call_gpt_api(prompt):
    """
    Calls the OpenAI GPT-4 API.
    Ensure OPENAI_API_KEY is set in your environment or handle it securely.
    """
    client = openai.OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.0
    )
    print(response)
    return response.choices[0].message.content

########################
# 4. Parse AI Response
########################

def parse_ai_response(response_text):
    """
    Safely parse the AI response (JSON) into a Python dictionary.
    If parsing fails, default to 'Unknown' for each field.
    """
    try:
        # Remove markdown code block if present
        if response_text.startswith('```json'):
            response_text = response_text.replace('```json', '', 1)
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        # Strip any remaining whitespace
        response_text = response_text.strip()
        
        # Parse JSON
        data = json.loads(response_text)
        
        # Ensure all required fields exist
        required_fields = [
            "DocumentID", "PartiesInvolved", "KindOfPersonalData",
            "DocumentType", "DateOfDocumentOrCase"
        ]
        
        for field in required_fields:
            if field not in data:
                data[field] = "Unknown"
                
        # Ensure lists are lists
        if isinstance(data["KindOfPersonalData"], str):
            data["KindOfPersonalData"] = [data["KindOfPersonalData"]]
        if isinstance(data["DocumentType"], str):
            data["DocumentType"] = [data["DocumentType"]]
            
        return data
        
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        print(f"Problematic response text: {response_text}")
        # Fallback if the response isn't valid JSON
        return {
            "DocumentID": "Unknown",
            "PartiesInvolved": "Unknown",
            "KindOfPersonalData": ["Unknown"],
            "DocumentType": ["Unknown"],
            "DateOfDocumentOrCase": "Unknown"
        }

########################
# 5. Process Files and Write to CSV
########################

def process_files_in_folder(input_folder, output_csv, test_mode=True):
    """
    Iterate over PDF and RTF files in a folder, extract text, call GPT,
    parse results, and write a CSV.
    
    Args:
        input_folder (str): Path to folder containing documents
        output_csv (str): Path for output CSV file
        test_mode (bool): If True, only extract and print text without calling AI
    """
    # Prepare a DataFrame to store results
    columns = [
        "DocumentID",
        "PartiesInvolved",
        "KindOfPersonalData",
        "DocumentType",
        "DateOfDocumentOrCase"
    ]
    df = pd.DataFrame(columns=columns)

    # Regex to detect 'doc-x-xx' if needed
    doc_pattern = re.compile(r"(doc-\d+-\d+)", re.IGNORECASE)

    for filename in os.listdir(input_folder):
        lower_filename = filename.lower()
        if lower_filename.endswith(".pdf") or lower_filename.endswith(".rtf"):
            file_path = os.path.join(input_folder, filename)
            
            # Get document ID
            base_name = os.path.splitext(filename)[0]
            match = doc_pattern.search(base_name)
            doc_id = match.group(1).lower() if match else base_name.lower()
            
            print(f"\nProcessing file: {filename}")
            print(f"Document ID: {doc_id}")

            # Extract text based on file type
            if lower_filename.endswith(".pdf"):
                document_text = extract_text_from_pdf(file_path)
                # Print text length for debugging
                print(f"Extracted text length: {len(document_text)} characters")
            elif lower_filename.endswith(".rtf"):
                document_text = extract_text_from_rtf(file_path)
                print(f"Extracted text length: {len(document_text)} characters")

            if test_mode:
                # In test mode, just add a placeholder row
                new_row = pd.DataFrame({
                    "DocumentID": [doc_id],
                    "PartiesInvolved": ["Test Mode"],
                    "KindOfPersonalData": ["Test Mode"],
                    "DocumentType": ["Test Mode"],
                    "DateOfDocumentOrCase": ["Test Mode"]
                })
            else:
                # Normal processing with AI
                prompt = build_prompt(document_text, doc_id)
                response_text = call_gpt_api(prompt)
                parsed_data = parse_ai_response(response_text)

                # Process the data as before
                kind_of_personal_data = parsed_data.get("KindOfPersonalData", [])
                if isinstance(kind_of_personal_data, list):
                    kind_of_personal_data = ", ".join(kind_of_personal_data)
                document_type = parsed_data.get("DocumentType", [])
                if isinstance(document_type, list):
                    document_type = ", ".join(document_type)

                new_row = pd.DataFrame({
                    "DocumentID": [parsed_data.get("DocumentID", "Unknown")],
                    "PartiesInvolved": [parsed_data.get("PartiesInvolved", "Unknown")],
                    "KindOfPersonalData": [kind_of_personal_data],
                    "DocumentType": [document_type],
                    "DateOfDocumentOrCase": [parsed_data.get("DateOfDocumentOrCase", "Unknown")]
                })

            df = pd.concat([df, new_row], ignore_index=True)

    # Save DataFrame to CSV
    df.to_csv(output_csv, index=False)
    print(f"\nSaved results to {output_csv}")

########################
# 6. Main Entry Point
########################

def main():
    if len(sys.argv) < 3:
        print("Usage: python main.py <input_folder> <output_csv> [test_mode]")
        sys.exit(1)

    input_folder = sys.argv[1]
    output_csv = sys.argv[2]
    test_mode = True if len(sys.argv) <= 3 else sys.argv[3].lower() == 'true'

    if not os.path.isdir(input_folder):
        print(f"Error: {input_folder} is not a directory.")
        sys.exit(1)

    process_files_in_folder(input_folder, output_csv, test_mode)

if __name__ == "__main__":
    main()
