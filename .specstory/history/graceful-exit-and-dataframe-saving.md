## SpecStory

## Graceful Exit and DataFrame Saving (4/2/2025, 1:01:46 PM)

_**User**_

If I press control + C to stop the program, I still want to save whatever progress we had made in the df and still produce a CSV

---

_**Assistant**_

I understand you want to handle keyboard interrupts (Ctrl+C) gracefully by saving any progress made before the program exits. I'll modify the code to catch the KeyboardInterrupt exception and save the DataFrame before exiting.

Let me edit the file to add this functionality:


---

_****_

```diff
  
  Personal Health Information (PHI) under HIPAA includes any individually identifiable health information.
- The Safe Harbor de-identification method provides an exhaustive list of “identifiers of the individual or of relatives, employers, or household members of the individual” that need to be removed from datasets before they are shared. The identifiers that need to be removed are the following: 
+ The Safe Harbor de-identification method provides an exhaustive list of "identifiers of the individual or of relatives, employers, or household members of the individual" that need to be removed from datasets before they are shared. The identifiers that need to be removed are the following: 
  (1) names 
  (2) all geographic subdivisions smaller than a state, except for the initial three digits of the ZIP code (provided this ZIP code unit contains more than 20,000 people) 
  **Example**: If the document mentions HIPAA but only discusses financial data or non-health-related information, that would not qualify as involving PHI or covered entities, even if HIPAA is mentioned.
  
- The goal is to reason through the document with a **researcher’s mindset**, applying **critical thinking** to ensure an accurate, rational conclusion regarding the presence of PHI or covered entities.
+ The goal is to reason through the document with a **researcher's mindset**, applying **critical thinking** to ensure an accurate, rational conclusion regarding the presence of PHI or covered entities.
  
  Document ID from filename: {doc_id}
                     if f.lower().endswith(('.pdf', '.rtf'))])
  
-     for filename in files:
-         lower_filename = filename.lower()
-         file_path = os.path.join(input_folder, filename)
-         
-         # Get document ID
-         base_name = os.path.splitext(filename)[0]
-         match = doc_pattern.search(base_name)
-         doc_id = match.group(1).lower() if match else base_name.lower()
-         
-         logging.info(f"\n\n {"="*5} Document ID: {doc_id} {"="*5}")
-         logging.info(f"\nProcessing file: {filename}")
+     try:
+         for filename in files:
+             lower_filename = filename.lower()
+             file_path = os.path.join(input_folder, filename)
+             
+             # Get document ID
+             base_name = os.path.splitext(filename)[0]
+             match = doc_pattern.search(base_name)
+             doc_id = match.group(1).lower() if match else base_name.lower()
+             
+             logging.info(f"\n\n {"="*5} Document ID: {doc_id} {"="*5}")
+             logging.info(f"\nProcessing file: {filename}")
  
-         # Extract text based on file type
-         if lower_filename.endswith(".pdf"):
-             document_text = extract_text_from_pdf(file_path)
-             logging.info(f"Extracted text length: {len(document_text)} characters")
-         elif lower_filename.endswith(".rtf"):
-             document_text = extract_text_from_rtf(file_path)
-             logging.info(f"Extracted text length: {len(document_text)} characters")
+             # Extract text based on file type
+             if lower_filename.endswith(".pdf"):
+                 document_text = extract_text_from_pdf(file_path)
+                 logging.info(f"Extracted text length: {len(document_text)} characters")
+             elif lower_filename.endswith(".rtf"):
+                 document_text = extract_text_from_rtf(file_path)
+                 logging.info(f"Extracted text length: {len(document_text)} characters")
  
-         if test_mode:
-             # In test mode, just add a placeholder row
-             new_row = pd.DataFrame({
-                 "DocumentID": [doc_id],
-                 "InvolvesPHI": "Test Mode",
-                 "InvolvesCoveredEntity": "Test Mode",
-                 "Explanation": "Test Mode"
-             })
-         else:
-             # Normal processing with AI
-             prompt = build_prompt(document_text, doc_id)
-             response_text = call_gpt_api(prompt)
-             parsed_data = parse_ai_response(doc_id, response_text)
+             if test_mode:
+                 # In test mode, just add a placeholder row
+                 new_row = pd.DataFrame({
+                     "DocumentID": [doc_id],
+                     "InvolvesPHI": "Test Mode",
+                     "InvolvesCoveredEntity": "Test Mode",
+                     "Explanation": "Test Mode"
+                 })
+             else:
+                 # Normal processing with AI
+                 prompt = build_prompt(document_text, doc_id)
+                 response_text = call_gpt_api(prompt)
+                 parsed_data = parse_ai_response(doc_id, response_text)
  
-             new_row = pd.DataFrame({
-                 "DocumentID": [parsed_data.get("DocumentID", "Unknown")],
-                 "InvolvesPHI": [parsed_data.get("InvolvesPHI", "Unknown")],
-                 "InvolvesCoveredEntity": [parsed_data.get("InvolvesCoveredEntity", "Unknown")],
-                 "Explanation": [parsed_data.get("Explanation", "Unknown")]
-             })
-             logging.info(f"COMPLETE: {doc_id}")
+                 new_row = pd.DataFrame({
+                     "DocumentID": [parsed_data.get("DocumentID", "Unknown")],
+                     "InvolvesPHI": [parsed_data.get("InvolvesPHI", "Unknown")],
+                     "InvolvesCoveredEntity": [parsed_data.get("InvolvesCoveredEntity", "Unknown")],
+                     "Explanation": [parsed_data.get("Explanation", "Unknown")]
+                 })
+                 logging.info(f"COMPLETE: {doc_id}")
  
-         df = pd.concat([df, new_row], ignore_index=True)
+             df = pd.concat([df, new_row], ignore_index=True)
  
-     # Save DataFrame to CSV
-     df.to_csv(output_csv, index=False)
-     logging.info(f"\nSaved results to {output_csv}")
+     except KeyboardInterrupt:
+         logging.warning("\nReceived keyboard interrupt. Saving progress before exiting...")
+     finally:
+         # Save DataFrame to CSV
+         if not df.empty:
+             df.to_csv(output_csv, index=False)
+             logging.info(f"\nSaved results to {output_csv}")
+         else:
+             logging.warning("\nNo results to save - DataFrame is empty")
  
  ########################
```

---

_****_

I've modified the code to handle keyboard interrupts gracefully. Here are the key changes:

1. Wrapped the main processing loop in a `try-except-finally` block
2. Added specific handling for `KeyboardInterrupt` (Ctrl+C)
3. Added a `finally` block that will always execute, whether the program completes normally or is interrupted
4. Added a check to ensure we only try to save if the DataFrame is not empty
5. Added appropriate logging messages to inform the user about what's happening

Now when you press Ctrl+C:
1. The program will catch the interrupt
2. It will log a warning message that it received the interrupt
3. The `finally` block will execute, saving any progress made so far to the CSV file
4. If there's no progress to save (empty DataFrame), it will log a warning message

This ensures that you won't lose any work that was completed before the interruption. The CSV file will contain all the results from the files that were processed up until the point where you pressed Ctrl+C.

---



---

