import requests
import os
import json
import time

def test_direct_pdf_upload(pdf_path, function_url, function_key):
    """Test the direct PDF upload functionality of the Azure Function."""
    # Construct the full URL with the function key
    url = f"{function_url}?code={function_key}"
    
    # Prepare the multipart/form-data request
    files = {
        'pdf_file': open(pdf_path, 'rb')
    }
    
    data = {
        'chunk_size': '5'  # Set the chunk size
    }
    
    print(f"Uploading PDF: {pdf_path}")
    start_time = time.time()
    
    # Send the request
    response = requests.post(url, files=files, data=data)
    
    # Calculate processing time
    processing_time = time.time() - start_time
    
    # Check if the request was successful
    if response.status_code == 200:
        result = response.json()
        
        # Print a summary of the results
        print(f"Successfully processed PDF in {processing_time:.2f} seconds")
        print(f"Total pages: {result['total_pages']}")
        print(f"Processed pages: {result['processed_pages']}")
        
        # Check for tables
        total_tables = sum(len(page.get('tables', [])) for page in result['extracted_content'])
        print(f"Total tables detected: {total_tables}")
        
        # Check for visual elements
        total_visual_elements = sum(len(page.get('visual_elements', [])) for page in result['extracted_content'])
        print(f"Total visual elements detected: {total_visual_elements}")
        
        # Check for encoded sections
        total_encoded_sections = sum(len(page.get('encoded_sections', [])) for page in result['extracted_content'])
        print(f"Total encoded sections detected: {total_encoded_sections}")
        
        # Save the result to a JSON file
        output_file = os.path.join('test_results', f"{os.path.basename(pdf_path).replace('.pdf', '')}_direct_upload_results.json")
        
        # Create the test_results directory if it doesn't exist
        os.makedirs('test_results', exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"Results saved to {output_file}")
        return True
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
        return False

if __name__ == "__main__":
    # Function app details
    function_url = "https://pdfunc.azurewebsites.net/api/orchestrator"
    function_key = ""
    
    # Test with each PDF in the test_pdfs directory
    test_files = [f for f in os.listdir('test_pdfs') if f.endswith('.pdf')]
    
    print(f"Found {len(test_files)} test PDF files")
    
    #for test_file in test_files:
     #   pdf_path = os.path.join('test_pdfs', test_file)
     #   print("\n" + "="*50)
     #   success = test_direct_pdf_upload(pdf_path, function_url, function_key)
     #   print("="*50)
        
      #  if not success:
      #      print(f"Failed to process {test_file}")
      #      break 
    test_direct_pdf_upload('REALPDF/spy_test_20MB.pdf', function_url, function_key)
