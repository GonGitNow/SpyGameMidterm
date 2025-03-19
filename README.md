# PDF Suspicious Content Detector

An Azure Functions-based application that processes PDF documents to detect potentially suspicious encoded content.

## Features

- PDF text extraction using PyMuPDF
- Table detection and extraction
- Visual element detection (charts, graphs, images)
- Encoded content detection (Base64, Hex, URL encoding)
- Suspicious pattern identification
- Document-level analysis of suspicious content
- Parallel processing of large documents

## Architecture

This application consists of two Azure Functions:

1. **OrchestratorFunction** - Handles the initial request, splits the document into chunks, and coordinates parallel processing
2. **ProcessorFunction** - Processes individual chunks of the PDF document

The system can handle PDFs uploaded directly (multipart/form-data) or as base64-encoded strings in a JSON payload.

## Detection Capabilities

The system can detect various types of suspicious patterns:
- High entropy text blocks (potentially encrypted content)
- Base64 encoded content
- Hexadecimal encoded content
- URL encoded content
- Unusually high density of encoded patterns

## Response Format

The API returns a JSON response with detailed information about:
- Extracted text content
- Detected tables
- Visual elements (images, charts, graphs)
- Encoded sections with suspicious pattern analysis
- Document-level suspicion analysis

## Usage

Send a POST request to the orchestrator endpoint with a PDF file:

```
POST https://pdfunc.azurewebsites.net/api/orchestrator
```

The response includes comprehensive analysis of the document, including any detected suspicious content.

## Development

### Prerequisites
- Python 3.11+
- Azure Functions Core Tools v4
- Azure subscription

### Local Setup
1. Clone this repository
2. Create a virtual environment: `python -m venv .venv`
3. Activate the virtual environment
4. Install dependencies: `pip install -r requirements.txt`
5. Run locally: `func start`

## Testing

Use the included `test_direct_upload.py` script to test uploading a PDF file to the function app. 