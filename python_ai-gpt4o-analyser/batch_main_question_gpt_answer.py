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
import asyncio
from typing import List, Dict, Any
import time

# Load environment variables from .env file
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Constants for rate limiting
MAX_BATCH_SIZE = 100  # Maximum number of requests in a batch according to OpenAI batch API
TOKENS_PER_MINUTE = 200000  # Rate limit of 200K tokens per minute
REQUESTS_PER_MINUTE = 500  # Rate limit of 500 requests per minute
TOTAL_TOKENS_PER_DAY = 2000000  # Rate limit of 2M tokens per day

# Global counters for rate limiting
tokens_used_in_minute = 0
requests_made_in_minute = 0
last_minute_reset = time.time()
total_tokens_used_today = 0
day_start = time.time()

def reset_rate_limits():
    """Reset rate limit counters if enough time has passed"""
    global tokens_used_in_minute, requests_made_in_minute, last_minute_reset
    global total_tokens_used_today, day_start
    
    current_time = time.time()
    
    # Reset minute-based counters
    if current_time - last_minute_reset >= 60:
        tokens_used_in_minute = 0
        requests_made_in_minute = 0
        last_minute_reset = current_time
        
    # Reset daily counter
    if current_time - day_start >= 86400:  # 24 hours
        total_tokens_used_today = 0
        day_start = current_time

def check_rate_limits(batch_token_estimate: int, batch_size: int) -> float:
    """
    Check rate limits and return delay needed (if any)
    Returns: Number of seconds to wait
    """
    reset_rate_limits()
    
    delay = 0
    
    # Check token rate limits
    if tokens_used_in_minute + batch_token_estimate > TOKENS_PER_MINUTE:
        delay = max(delay, 60 - (time.time() - last_minute_reset))
    
    # Check request rate limits
    if requests_made_in_minute + batch_size > REQUESTS_PER_MINUTE:
        delay = max(delay, 60 - (time.time() - last_minute_reset))
    
    # Check daily token limit
    if total_tokens_used_today + batch_token_estimate > TOTAL_TOKENS_PER_DAY:
        delay = max(delay, 86400 - (time.time() - day_start))
    
    return delay

def update_rate_limit_counters(total_tokens: int, num_requests: int):
    """Update the rate limit counters after processing"""
    global tokens_used_in_minute, requests_made_in_minute, total_tokens_used_today
    
    tokens_used_in_minute += total_tokens
    requests_made_in_minute += num_requests
    total_tokens_used_today += total_tokens

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
                            logging.info(f"Extracting text on page {i} of {num_pages}")
                            text_content.append(text)
                            logging.info("Success extracting text")
                            # print(f"\n--- Page {i} Content {'='*40}")
                            # print(text[:500] + "..." if len(text) > 500 else text)
                            # print(f"{'='*50}\n")
                    except Exception as e:
                        logging.error(f"Warning: PyPDF2 - Error extracting page {i}: {str(e)}")
                
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
    max_text_tokens = 126500  # Total ~128K tokens: 500 prompt + 126.5K document + 1K response
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

Personal Health Information (PHI) under HIPAA includes any individually identifiable health information that is:
- Transmitted or maintained in any form or medium
- Created or received by a healthcare provider, health plan, employer, or healthcare clearinghouse
- Relates to the past, present, or future physical or mental health or condition of an individual
- Relates to the provision of healthcare to an individual
- Relates to the past, present, or future payment for the provision of healthcare to an individual

Please analyze the document and return a JSON response with the following structure:

{{
    "DocumentID": "doc-x-xx",  // Use the provided doc_id if no specific ID found
    "InvolvesPHI": true/false,  // Whether the document involves PHI as defined by HIPAA
    "InvolvesCoveredEntity": true/false,  // Whether the document involves HIPAA-covered entities
    "Explanation": "Detailed explanation of your analysis, including specific references to the text that support your conclusions"
}}

Document ID from filename: {doc_id}

Please provide a clear, detailed explanation of your analysis, citing specific parts or examples of the text that support your conclusions about PHI and covered entities.

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

def call_gpt_api_batch(prompts: List[str]) -> List[str]:
    """
    Process multiple prompts in a batch using the OpenAI batch API.
    Returns a list of response texts.
    """
    if not prompts:
        return []
    
    # Estimate tokens for rate limiting (rough estimate: 4 chars = 1 token)
    total_chars = sum(len(prompt) for prompt in prompts)
    estimated_tokens = total_chars // 4
    
    # Check rate limits and wait if necessary
    delay = check_rate_limits(estimated_tokens, len(prompts))
    if delay > 0:
        logging.info(f"Rate limit approaching, waiting {delay:.1f} seconds...")
        time.sleep(delay)
    
    try:
        client = openai.OpenAI()
        
        # Prepare the batch request
        batch_request = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "user", "content": prompt}
                for prompt in prompts
            ],
            "temperature": 0.0
        }
        
        # Make a single batch API call
        batch_response = client.chat.completions.create(**batch_request)
        
        # Update rate limit counters
        update_rate_limit_counters(
            batch_response.usage.total_tokens,
            len(prompts)
        )
        
        # Log batch completion
        logging.info(f"Completed batch of {len(prompts)} documents")
        
        # Extract responses
        responses = [choice.message.content for choice in batch_response.choices]
        return responses
        
    except Exception as e:
        logging.error(f"Error in batch API call: {str(e)}")
        # Return empty responses for the failed batch
        return ["" for _ in prompts]

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
    Iterate over PDF and RTF files in a folder, extract text, call GPT in batches,
    parse results, and write a CSV.
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

    # Process files in batches
    batch_size = MAX_BATCH_SIZE
    for i in range(0, len(files), batch_size):
        batch_files = files[i:i + batch_size]
        batch_prompts = []
        batch_doc_ids = []
        
        # Prepare batch of documents
        for filename in batch_files:
            lower_filename = filename.lower()
            file_path = os.path.join(input_folder, filename)
            
            # Get document ID
            base_name = os.path.splitext(filename)[0]
            match = doc_pattern.search(base_name)
            doc_id = match.group(1).lower() if match else base_name.lower()
            batch_doc_ids.append(doc_id)
            
            logging.info(f"\n\n {"="*5} Document ID: {doc_id} {"="*5}")
            logging.info(f"\nProcessing file: {filename}")

            # Extract text based on file type
            if lower_filename.endswith(".pdf"):
                document_text = extract_text_from_pdf(file_path)
                logging.info(f"Extracted text length: {len(document_text)} characters")
            elif lower_filename.endswith(".rtf"):
                document_text = extract_text_from_rtf(file_path)
                logging.info(f"Extracted text length: {len(document_text)} characters")

            if not test_mode:
                # Add to batch for processing
                prompt = build_prompt(document_text, doc_id)
                batch_prompts.append(prompt)
            else:
                # In test mode, add placeholder row
                new_row = pd.DataFrame({
                    "DocumentID": [doc_id],
                    "InvolvesPHI": "Test Mode",
                    "InvolvesCoveredEntity": "Test Mode",
                    "Explanation": "Test Mode"
                })
                df = pd.concat([df, new_row], ignore_index=True)

        if not test_mode and batch_prompts:
            # Process batch with API
            batch_responses = call_gpt_api_batch(batch_prompts)
            
            # Process responses
            for doc_id, response_text in zip(batch_doc_ids, batch_responses):
                if response_text:  # Skip empty responses
                    parsed_data = parse_ai_response(doc_id, response_text)
                    new_row = pd.DataFrame({
                        "DocumentID": [parsed_data.get("DocumentID", "Unknown")],
                        "InvolvesPHI": [parsed_data.get("InvolvesPHI", "Unknown")],
                        "InvolvesCoveredEntity": [parsed_data.get("InvolvesCoveredEntity", "Unknown")],
                        "Explanation": [parsed_data.get("Explanation", "Unknown")]
                    })
                    df = pd.concat([df, new_row], ignore_index=True)
                    logging.info(f"COMPLETE: {doc_id}")

    # Save DataFrame to CSV
    df.to_csv(output_csv, index=False)
    logging.info(f"\nSaved results to {output_csv}")

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
