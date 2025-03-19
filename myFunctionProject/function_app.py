import azure.functions as func
import logging
import json
import os
import base64
from typing import List
import asyncio
import aiohttp
import io
from pdf_processor import PdfProcessor

app = func.FunctionApp()

@app.function_name(name="OrchestratorFunction")
@app.route(route="orchestrator")
async def orchestrator_function(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('PDF Processing Orchestrator triggered')
    
    try:
        # Check content type to determine how to handle the request
        content_type = req.headers.get('content-type', '')
        pdf_data = None
        chunk_size = 5  # Default chunk size
        
        if 'multipart/form-data' in content_type:
            # Handle multipart form data (direct PDF upload)
            logging.info('Processing multipart form data')
            
            # Get the PDF file from the request
            files = req.files.get('pdf_file')
            if not files:
                return func.HttpResponse(
                    "No PDF file found in the request. Please upload a file with name 'pdf_file'",
                    status_code=400
                )
                
            # Read the file content
            pdf_bytes = files.read()
            
            # Convert to base64 for internal processing
            pdf_data = base64.b64encode(pdf_bytes).decode('utf-8')
            
            # Get chunk size from form data if provided
            form = req.form
            if form and 'chunk_size' in form:
                try:
                    chunk_size = int(form['chunk_size'])
                except (ValueError, TypeError):
                    # If invalid, use default
                    chunk_size = 5
        else:
            # Handle JSON payload (base64 encoded PDF)
            logging.info('Processing JSON payload')
            try:
                req_body = req.get_json()
                pdf_data = req_body.get('pdf_data')
                chunk_size = req_body.get('chunk_size', 5)
            except ValueError:
                return func.HttpResponse(
                    "Invalid JSON payload",
                    status_code=400
                )
        
        if not pdf_data:
            return func.HttpResponse(
                "Please provide a PDF file or PDF data in base64 format",
                status_code=400
            )
        
        # Initialize processor to get total pages
        processor = PdfProcessor()
        total_pages = processor.process_pdf_chunk(pdf_data, (0, 1))['total_pages']
        
        # Calculate chunks
        chunks = [(i, min(i + chunk_size, total_pages)) 
                 for i in range(0, total_pages, chunk_size)]
        
        # Process chunks in parallel
        async with aiohttp.ClientSession() as session:
            tasks = []
            for start, end in chunks:
                task = asyncio.create_task(
                    process_chunk(session, pdf_data, (start, end))
                )
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
        
        # Combine results
        combined_results = combine_results(results)
        
        # Log overall document analysis
        if combined_results['document_analysis']['overall_suspicious']:
            logging.warning("Document flagged as suspicious:")
            logging.warning(f"Suspicious pages: {combined_results['document_analysis']['suspicious_pages']}")
            logging.warning(f"Average suspicion score: {combined_results['document_analysis']['average_suspicion_score']}")
            logging.warning(f"Max suspicion score: {combined_results['document_analysis']['max_suspicion_score']}")
            logging.warning(f"Reasons: {', '.join(combined_results['document_analysis']['all_suspicion_reasons'])}")
        
        return func.HttpResponse(
            json.dumps(combined_results),
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Error in orchestrator: {str(e)}")
        return func.HttpResponse(
            f"Error processing request: {str(e)}",
            status_code=500
        )

@app.function_name(name="ProcessorFunction")
@app.route(route="process-chunk")
async def processor_function(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('PDF Chunk Processor triggered')
    
    try:
        # Check content type to determine how to handle the request
        content_type = req.headers.get('content-type', '')
        pdf_data = None
        page_range = None
        
        if 'multipart/form-data' in content_type:
            # Handle multipart form data (direct PDF upload)
            logging.info('Processing multipart form data')
            
            # Get the PDF file from the request
            files = req.files.get('pdf_file')
            if not files:
                return func.HttpResponse(
                    "No PDF file found in the request. Please upload a file with name 'pdf_file'",
                    status_code=400
                )
                
            # Read the file content
            pdf_bytes = files.read()
            
            # Convert to base64 for internal processing
            pdf_data = base64.b64encode(pdf_bytes).decode('utf-8')
            
            # Get page range from form data
            form = req.form
            if form and 'page_range' in form:
                try:
                    # Parse page range as tuple (start, end)
                    page_range_str = form['page_range']
                    page_range = eval(page_range_str)  # Safe since we expect a tuple
                except:
                    return func.HttpResponse(
                        "Invalid page range format. Expected tuple (start, end)",
                        status_code=400
                    )
        else:
            # Handle JSON payload (base64 encoded PDF)
            logging.info('Processing JSON payload')
            try:
                req_body = req.get_json()
                pdf_data = req_body.get('pdf_data')
                page_range = req_body.get('page_range')
            except ValueError:
                return func.HttpResponse(
                    "Invalid JSON payload",
                    status_code=400
                )
        
        if not pdf_data or not page_range:
            return func.HttpResponse(
                "Please provide a PDF file (or PDF data) and page range",
                status_code=400
            )
        
        processor = PdfProcessor()
        result = processor.process_pdf_chunk(pdf_data, page_range)
        
        # Log suspicious content detection
        if any(page.get('suspicious', False) for page in result['extracted_content']):
            logging.warning(f"Suspicious content detected in chunk {page_range}")
            for page in result['extracted_content']:
                if page.get('suspicious'):
                    logging.warning(f"Page {page['page_number']}: Score {page['suspicion_score']}, "
                                 f"Reasons: {', '.join(page['suspicion_reasons'])}")
        
        return func.HttpResponse(
            json.dumps(result),
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Error in processor: {str(e)}")
        return func.HttpResponse(
            f"Error processing chunk: {str(e)}",
            status_code=500
        )

async def process_chunk(session: aiohttp.ClientSession, pdf_data: str, 
                       page_range: tuple) -> dict:
    """Process a chunk of pages using the processor function"""
    processor_url = os.environ['PROCESSOR_FUNCTION_URL']
    
    # Use JSON format for internal communication between functions
    async with session.post(
        processor_url,
        json={'pdf_data': pdf_data, 'page_range': page_range}
    ) as response:
        return await response.json()

def combine_results(results: List[dict]) -> dict:
    """Combine results from multiple chunks"""
    combined = {
        'total_pages': 0,
        'processed_pages': 0,
        'extracted_content': [],
        'document_metadata': {},
        'document_analysis': {
            'suspicious_pages': 0,
            'average_suspicion_score': 0.0,
            'overall_suspicious': False,
            'all_suspicion_reasons': set(),
            'max_suspicion_score': 0.0
        }
    }
    
    total_suspicion_score = 0.0
    
    for result in results:
        combined['total_pages'] = max(combined['total_pages'], 
                                    result['total_pages'])
        combined['processed_pages'] += result['processed_pages']
        combined['extracted_content'].extend(result['extracted_content'])
        
        # Merge metadata (take most complete)
        if len(result.get('document_metadata', {})) > len(combined['document_metadata']):
            combined['document_metadata'] = result['document_metadata']
        
        # Process suspicion metrics for each page
        for page in result['extracted_content']:
            if page.get('suspicious', False):
                combined['document_analysis']['suspicious_pages'] += 1
            
            score = page.get('suspicion_score', 0.0)
            total_suspicion_score += score
            combined['document_analysis']['max_suspicion_score'] = max(
                combined['document_analysis']['max_suspicion_score'],
                score
            )
            
            if page.get('suspicion_reasons'):
                combined['document_analysis']['all_suspicion_reasons'].update(
                    page['suspicion_reasons']
                )
    
    # Sort content by page number
    combined['extracted_content'].sort(key=lambda x: x['page_number'])
    
    # Calculate final metrics
    if combined['processed_pages'] > 0:
        combined['document_analysis']['average_suspicion_score'] = round(
            total_suspicion_score / combined['processed_pages'],
            2
        )
        
        # Consider document suspicious if:
        # - More than 20% of pages are suspicious OR
        # - Average suspicion score > 3.0 OR
        # - Max suspicion score > 7.0
        suspicious_page_ratio = (combined['document_analysis']['suspicious_pages'] / 
                               combined['processed_pages'])
        
        combined['document_analysis']['overall_suspicious'] = (
            suspicious_page_ratio > 0.2 or
            combined['document_analysis']['average_suspicion_score'] > 3.0 or
            combined['document_analysis']['max_suspicion_score'] > 7.0
        )
    
    # Convert set to list for JSON serialization
    combined['document_analysis']['all_suspicion_reasons'] = list(
        combined['document_analysis']['all_suspicion_reasons']
    )
    
    return combined 