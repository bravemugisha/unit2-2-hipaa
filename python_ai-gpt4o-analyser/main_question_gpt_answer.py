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
import logging
import datetime

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
            logging.info(f"\nProcessing PDF: {pdf_path}")
            
            # Try PyPDF2 first
            try:
                pdf_reader = PyPDF2.PdfReader(file)
                num_pages = len(pdf_reader.pages)
                logging.info(f"Number of pages: {num_pages}")
                
                for i, page in enumerate(pdf_reader.pages, 1):
                    try:
                        text = page.extract_text() or ""
                        if not text.strip():
                            logging.warning(f"Warning: PyPDF2 - Page {i} appears to be empty or unreadable")
                        else:
                            # logging.info(f"Extracting text on page {i} of {num_pages}") #replaced by line 50
                            text_content.append(text)
                            # logging.info("Success extracting text") #replaced by line 50
                            # print(f"\n--- Page {i} Content {'='*40}")
                            # print(text[:500] + "..." if len(text) > 500 else text)
                            # print(f"{'='*50}\n")
                    except Exception as e:
                        logging.error(f"Warning: PyPDF2 - Error extracting page {i}: {str(e)}")
                logging.info("PDF Text Extraction Complete")
                
                if not text_content:  # If PyPDF2 failed to extract any text
                    raise Exception("No text extracted with PyPDF2")
                    
            except Exception as e:
                logging.error(f"PyPDF2 extraction failed: {str(e)}")
                logging.info("Falling back to pdfplumber...")
                
                # Fall back to pdfplumber
                with pdfplumber.open(pdf_path) as pdf:
                    num_pages = len(pdf.pages)
                    logging.info(f"Number of pages: {num_pages}")
                    
                    for i, page in enumerate(pdf.pages, 1):
                        try:
                            text = page.extract_text() or ""
                            if not text.strip():
                                logging.warning(f"Warning: pdfplumber - Page {i} appears to be empty or unreadable")
                            else:
                                text_content.append(text)
                                logging.info(f"\n--- Page {i} Content {'='*40}")
                                logging.info(text[:500] + "..." if len(text) > 500 else text)
                                logging.info(f"{'='*50}\n")
                        except Exception as e:
                            logging.error(f"Warning: pdfplumber - Error extracting page {i}: {str(e)}")
        
        full_text = "\n".join(text_content)
        if not full_text.strip():
            logging.warning("Warning: No text was extracted from the PDF using either method!")
            
        return full_text
        
    except Exception as e:
        logging.error(f"Error extracting text from PDF {pdf_path}: {str(e)}")
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
    This prompt focuses on two key questions about HIPAA applicability:
    1. Does the document involve PHI?
    2. Does the document involve covered entities?
    """
    # Calculate tokens (rough estimate: 4 chars = 1 token)
    # GPT-4o-mini has 128k context window
    # Base prompt is ~500 tokens, leave room for response (~1000 tokens)
    max_text_tokens = 80000  # Total ~128K tokens: 500 prompt + 126.5K document + 1K response
    max_text_chars = max_text_tokens * 4  # ~506,000 characters

    logging.info(f"TOTAL INPUT TOKENS: {len(document_text) * 4}")
    
    # Truncate document_text if too long
    if len(document_text) > max_text_chars:
        logging.warning(f"Warning: Document text too long ({len(document_text)} chars). Truncating to {max_text_chars} chars...")
        document_text = document_text[:max_text_chars] + "\n[Text truncated due to length...]"

    # Add rate limit warning if document is large
    if len(document_text) > 100000:  # If document is large
        logging.warning("Warning: Large document. Consider rate limits:")
        logging.warning(f"Estimated tokens: {len(document_text) // 4}")
        logging.warning("Rate limits: 200K tokens/minute, 2M tokens/day")

    prompt = f"""
You are given the text of a legal document. Your task is to analyze whether this document involves HIPAA-covered entities and/or Personal Health Information (PHI) as defined by HIPAA.

Important Context about HIPAA Coverage:
Only "covered entities" have to comply with the HIPAA Privacy Rule. Most notably, this includes:
(i) health insurance organizations
(ii) health care providers (such as doctors and hospitals)
(iii) health care clearinghouses (entities that process health information into a standardized format, such as billing services)
(iv) business associates of covered entities (which perform actions on health data on behalf of covered entities, such as data analytics)

Personal Health Information (PHI) under HIPAA includes any individually identifiable health information.
The Safe Harbor de-identification method provides an exhaustive list of "identifiers of the individual or of relatives, employers, or household members of the individual" that need to be removed from datasets before they are shared. The identifiers that need to be removed are the following: 
(1) names 
(2) all geographic subdivisions smaller than a state, except for the initial three digits of the ZIP code (provided this ZIP code unit contains more than 20,000 people) 
(3) all dates, except years (This includes dates of birth, but also other dates directly linked to an individual such as hospital admission dates. Years indicating that an individual is over 89 also need to be removed) 
(4) telephone numbers
(5) vehicle identifiers 
(6) fax numbers 
(7) device identifiers and serial numbers
(8) email addresses 
(9) URLs
(10) social security numbers
(11) IP addresses
(12) medical record numbers 
(13) biometric identifiers 
(14) health plan beneficiary numbers 
(15) full-face photographs and any comparable images 
(16) account numbers 
(17) certificate / license numbers 
(18) any other unique identifying number, characteristic or code. 
The Safe Harbor method also has a requirement that "the covered entity does not have actual knowledge that the information could be used alone or in combination with other informaion to identify an individual who is a subject of the information. 

Please analyze the document and return a JSON response with the following structure:

{{
    "DocumentID": "doc-x-xx",  // Use the provided doc_id if no specific ID found
    "InvolvesPHI": true/false,  // Whether the document involves PHI as defined by HIPAA
    "InvolvesCoveredEntity": true/false,  // Whether the document involves HIPAA-covered entities
    "Explanation": "Detailed explanation of your analysis, including specific references to the text that support your conclusions"
}}

## Important: 

The mere mention of **HIPAA** in a document is not enough to automatically conclude that it involves **PHI** or **covered entities**. This is because references to HIPAA may only be claims and may not accurately reflect the involvement of PHI or covered entities. 

Your task is to **objectively and factually** analyze the document and answer the following two questions:
1. **Does the document involve PHI?**
2. **Does the document involve covered entities?**

**Key Instruction for Analysis**: 
- When reviewing the document, critically assess whether the **actual content** and context indicate the involvement of PHI or covered entities. Do not rely on simple statements or claims that HIPAA is involved, especially when the context involves unrelated data (like financial information). 
- Only confirm the presence of PHI if there is clear evidence that **individually identifiable health information** is involved as defined by HIPAA. Similarly, only confirm the involvement of **covered entities** if the document refers to health organizations or individuals (like healthcare providers or insurance companies) that are subject to HIPAA requirements due to their handling of health data.

**Example**: If the document mentions HIPAA but only discusses financial data or non-health-related information, that would not qualify as involving PHI or covered entities, even if HIPAA is mentioned.

The goal is to reason through the document with a **researcher's mindset**, applying **critical thinking** to ensure an accurate, rational conclusion regarding the presence of PHI or covered entities.

Document ID from filename: {doc_id}

Please provide a clear, detailed explanation of your analysis, citing specific parts of the text that support your conclusions about PHI and covered entities.

Here is the document text:

\"\"\" 
{document_text}
\"\"\"
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
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.0
    )
    logging.info(response)
    return response.choices[0].message.content

########################
# 4. Parse AI Response
########################

def parse_ai_response(doc_id, response_text):
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
        
        # Strip any repdf_to_form_gpt_analysising whitespace
        response_text = response_text.strip()
        
        # Parse JSON
        data = json.loads(response_text)
        
        # Ensure all required fields exist
        required_fields = [
            "DocumentID", "InvolvesPHI", "InvolvesCoveredEntity", "Explanation"
        ]
        
        for field in required_fields:
            if field not in data:
                data[field] = "Unknown"

        logging.info(f"Data for {doc_id}: \n {data} \n")        
        return data
        
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing JSON: {e}")
        logging.error(f"Problematic response text: {response_text}")
        # Fallback if the response isn't valid JSON
        return {
            "DocumentID": "Unknown",
            "InvolvesPHI": "Unknown",
            "InvolvesCoveredEntity": "Unknown",
            "Explanation": "Unknown"
        }

########################
# 5. Process Files and Write to CSV
########################

def setup_logging(input_folder, output_csv, test_mode):
    """Configure logging to both file and console with timestamped files"""
    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    # Create timestamp for log file name
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Create descriptive log filename
    base_input_folder = os.path.basename(input_folder)
    log_filename = f"{timestamp}_analysis_{base_input_folder}"
    if test_mode:
        log_filename += "_test"
    log_filename += ".log"
    
    log_file = os.path.join(logs_dir, log_filename)

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()  # This will still print to console
        ]
    )

    # Log the command line arguments at the start
    cmd_line = f"Command: python {os.path.basename(__file__)} {input_folder} {output_csv} {test_mode}"
    logging.info("="*50)
    logging.info("SCRIPT EXECUTION STARTED")
    logging.info(cmd_line)
    logging.info("="*50)

def process_files_in_folder(input_folder, output_csv, test_mode=False):
    """
    Iterate over PDF and RTF files in a folder, extract text, call GPT,
    parse results, and write a CSV.
    
    Args:
        input_folder (str): Path to folder containing documents
        output_csv (str): Path for output CSV file
        test_mode (bool): If True, only extract and print text without calling AI
    """
    # Set up logging with the input parameters
    setup_logging(input_folder, output_csv, test_mode)
    
    logging.info(f"Starting to process files in {input_folder}")
    # Prepare a DataFrame to store results
    columns = [
        "DocumentID",
        "InvolvesPHI",
        "InvolvesCoveredEntity",
        "Explanation"
    ]
    df = pd.DataFrame(columns=columns)

    # Regex to detect 'doc-x-xx' if needed
    doc_pattern = re.compile(r"(doc-\d+-\d+)", re.IGNORECASE)

    # Get sorted list of files
    files = sorted([f for f in os.listdir(input_folder) 
                   if f.lower().endswith(('.pdf', '.rtf'))])

    try:
        for filename in files:
            lower_filename = filename.lower()
            file_path = os.path.join(input_folder, filename)
            
            # Get document ID
            base_name = os.path.splitext(filename)[0]
            match = doc_pattern.search(base_name)
            doc_id = match.group(1).lower() if match else base_name.lower()
            
            logging.info(f"\n\n {"="*5} Document ID: {doc_id} {"="*5}")
            logging.info(f"\nProcessing file: {filename}")

            # Extract text based on file type
            if lower_filename.endswith(".pdf"):
                document_text = extract_text_from_pdf(file_path)
                logging.info(f"Extracted text length: {len(document_text)} characters")
            elif lower_filename.endswith(".rtf"):
                document_text = extract_text_from_rtf(file_path)
                logging.info(f"Extracted text length: {len(document_text)} characters")

            if test_mode:
                # In test mode, just add a placeholder row
                new_row = pd.DataFrame({
                    "DocumentID": [doc_id],
                    "InvolvesPHI": "Test Mode",
                    "InvolvesCoveredEntity": "Test Mode",
                    "Explanation": "Test Mode"
                })
            else:
                # Normal processing with AI
                prompt = build_prompt(document_text, doc_id)
                response_text = call_gpt_api(prompt)
                parsed_data = parse_ai_response(doc_id, response_text)

                new_row = pd.DataFrame({
                    "DocumentID": [parsed_data.get("DocumentID", "Unknown")],
                    "InvolvesPHI": [parsed_data.get("InvolvesPHI", "Unknown")],
                    "InvolvesCoveredEntity": [parsed_data.get("InvolvesCoveredEntity", "Unknown")],
                    "Explanation": [parsed_data.get("Explanation", "Unknown")]
                })
                logging.info(f"COMPLETE: {doc_id}")

            df = pd.concat([df, new_row], ignore_index=True)

    except KeyboardInterrupt:
        logging.warning("\nReceived keyboard interrupt. Saving progress before exiting...")
    finally:
        # Save DataFrame to CSV
        if not df.empty:
            df.to_csv(output_csv, index=False)
            logging.info(f"\nSaved results to {output_csv}")
        else:
            logging.warning("\nNo results to save - DataFrame is empty")

########################
# 6. pdf_to_form_gpt_analysis Entry Point
########################

def main():
    if len(sys.argv) < 3:
        logging.error("Usage: python3 main_question_gpt_answer.py <input_folder> <output_csv> [test_mode]")
        sys.exit(1)

    input_folder = sys.argv[1]
    output_csv = sys.argv[2]
    test_mode = False if len(sys.argv) <= 3 else sys.argv[3].lower() == 'true'

    if not os.path.isdir(input_folder):
        logging.error(f"Error: {input_folder} is not a directory.")
        sys.exit(1)

    process_files_in_folder(input_folder, output_csv, test_mode)

if __name__ == "__main__":
    main()
