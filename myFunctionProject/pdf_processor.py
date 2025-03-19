import io
import base64
import re
from typing import Dict, List, Optional, Tuple
import fitz  # PyMuPDF
import os
import json
from encoding_detector import EncodingDetector

class PdfProcessor:
    def __init__(self):
        self.debug_mode = False  # Debug mode flag
        # Initialize the encoding detector
        self.encoding_detector = EncodingDetector()
        
    def extract_tables(self, page: fitz.Page) -> List[Dict]:
        """
        Extract tables from a page using PyMuPDF's table detection capabilities
        """
        tables = []
        
        # Extract text blocks with their bounding boxes
        blocks = page.get_text("dict")["blocks"]
        
        # First, try to detect tables using PyMuPDF's built-in table detection
        # Look for grid-like structures of text blocks
        table_candidates = []
        
        # Group text blocks by their vertical position (y-coordinate)
        rows = {}
        for block in blocks:
            if block["type"] == 0:  # Text block
                for line in block["lines"]:
                    y_pos = round(line["bbox"][1], 0)  # Round y-coordinate for grouping
                    if y_pos not in rows:
                        rows[y_pos] = []
                    
                    for span in line["spans"]:
                        text = span["text"].strip()
                        if text:
                            rows[y_pos].append({
                                "text": text,
                                "bbox": span["bbox"]
                            })
        
        # Sort rows by y-coordinate
        sorted_rows = sorted(rows.items())
        
        # Find consecutive rows with similar structure (potential tables)
        current_table = []
        min_cols = 3  # Minimum columns to consider as a table
        
        for _, row_spans in sorted_rows:
            # Skip rows with too few cells
            if len(row_spans) < min_cols:
                # If we were building a table and now found a non-table row
                if len(current_table) >= 3:  # Minimum 3 rows for a table
                    # Process the completed table
                    table_data = []
                    for table_row in current_table:
                        # Sort spans by x-coordinate
                        sorted_spans = sorted(table_row, key=lambda span: span["bbox"][0])
                        table_data.append([span["text"] for span in sorted_spans])
                    
                    tables.append({
                        "type": "table",
                        "data": table_data
                    })
                
                current_table = []
                continue
            
            # Add this row to the current table
            current_table.append(row_spans)
        
        # Check if we have a pending table at the end
        if len(current_table) >= 3:
            table_data = []
            for table_row in current_table:
                sorted_spans = sorted(table_row, key=lambda span: span["bbox"][0])
                table_data.append([span["text"] for span in sorted_spans])
            
            tables.append({
                "type": "table",
                "data": table_data
            })
        
        return tables
        
    def extract_visual_elements(self, page: fitz.Page, text: str) -> List[Dict]:
        """Extract visual elements (charts, graphs, images) from a page"""
        visual_elements = []
        
        # 1. Extract images using PyMuPDF
        image_list = page.get_images(full=True)
        
        for img_idx, img_info in enumerate(image_list):
            xref = img_info[0]  # Image reference number
            
            # Get the image rectangle
            image_rect = None
            for img_rect in page.get_image_rects(xref):
                image_rect = img_rect
                break
            
            if image_rect:
                # Get text near the image to identify if it's a chart/graph
                nearby_text = ""
                
                # Get text within and around the image rectangle
                expanded_rect = fitz.Rect(
                    image_rect.x0 - 50, 
                    image_rect.y0 - 50,
                    image_rect.x1 + 50, 
                    image_rect.y1 + 50
                )
                nearby_text = page.get_text("text", clip=expanded_rect)
                
                # Determine if this might be a chart/graph based on nearby text
                is_chart = False
                chart_keywords = ["chart", "graph", "figure", "plot", "diagram", "bar", "pie", "line graph"]
                
                for keyword in chart_keywords:
                    if keyword in nearby_text.lower():
                        is_chart = True
                        break
                
                element_type = "chart_or_graph" if is_chart else "image"
                
                visual_elements.append({
                    "type": element_type,
                    "bounding_box": [image_rect.x0, image_rect.y0, image_rect.x1, image_rect.y1],
                    "nearby_text": nearby_text[:200] + ('...' if len(nearby_text) > 200 else '')
                })
        
        # 2. Also look for text patterns that suggest charts/graphs (as a fallback)
        chart_patterns = [
            r'figure\s+\d+\s*:?', r'fig\.\s*\d+\s*:?', r'chart\s+\d+\s*:?', r'graph\s+\d+\s*:?',
            r'plot\s+\d+\s*:?', r'diagram\s+\d+\s*:?', r'figure\s*:', r'chart\s*:'
        ]
        
        # Find potential chart references in the text
        for pattern in chart_patterns:
            matches = re.finditer(pattern, text.lower())
            for match in matches:
                # Check if this reference is already covered by an image
                reference_already_covered = False
                for element in visual_elements:
                    if match.group(0) in element.get("nearby_text", "").lower():
                        reference_already_covered = True
                        break
                
                if not reference_already_covered:
                    # Get the context around the match
                    start_idx = max(0, match.start() - 50)
                    end_idx = min(len(text), match.end() + 100)
                    context = text[start_idx:end_idx]
                    
                    # Create a visual element entry
                    visual_element = {
                        "type": "potential_chart_or_graph",
                        "bounding_box": None,  # No coordinates for text-based detection
                        "nearby_text": context,
                        "reference": match.group(0)
                    }
                    
                    visual_elements.append(visual_element)
                    
                    if self.debug_mode:
                        print(f"DEBUG: Found chart reference: {match.group(0)}")
                        print(f"DEBUG: Context: {context}")
        
        return visual_elements

    def process_pdf_chunk(self, pdf_data: str, page_range: Optional[Tuple[int, int]] = None) -> Dict:
        """
        Process a chunk of PDF using PyMuPDF
        """
        pdf_bytes = base64.b64decode(pdf_data)
        pdf_file = io.BytesIO(pdf_bytes)
        
        # Use PyMuPDF to open the document
        doc = fitz.open(stream=pdf_file, filetype="pdf")
        total_pages = len(doc)
        
        if page_range is None:
            start_page, end_page = 0, total_pages
        else:
            start_page, end_page = max(0, page_range[0]), min(total_pages, page_range[1])
        
        results = []
        
        # Process each page
        for page_num in range(start_page, end_page):
            if self.debug_mode:
                print(f"DEBUG: Processing page {page_num+1}")
            
            if page_num < total_pages:
                page = doc[page_num]
                
                # Extract text with better layout preservation
                text = page.get_text()
                
                if self.debug_mode:
                    print(f"DEBUG: Extracted {len(text)} characters of text")
                
                # Extract tables using PyMuPDF's capabilities
                tables = self.extract_tables(page)
                
                # Extract visual elements (charts, graphs, images)
                visual_elements = self.extract_visual_elements(page, text)
                
                # Use the encoding detector to find encoded sections
                encoding_results = self.encoding_detector.detect_encodings(text)
                
                # Check for unusual formatting
                formatting_flags = []
                
                # Check for rotated text
                rotation = page.rotation
                if rotation != 0:
                    formatting_flags.append(f"rotated_{rotation}_degrees")
                
                results.append({
                    'page_number': page_num,
                    'text': text,
                    'tables': tables,
                    'visual_elements': visual_elements,
                    'encoded_sections': encoding_results['findings'],
                    'suspicious': encoding_results['suspicious'],
                    'suspicion_score': encoding_results['suspicion_score'],
                    'suspicion_reasons': encoding_results['suspicion_reasons'],
                    'formatting_flags': formatting_flags,
                    'rotation': rotation
                })
        
        # Extract document metadata
        metadata = self._extract_document_metadata(doc)
        
        # Close the document
        doc.close()
        
        return {
            'total_pages': total_pages,
            'processed_pages': end_page - start_page,
            'extracted_content': results,
            'document_metadata': metadata
        }

    def _extract_document_metadata(self, doc: fitz.Document) -> Dict:
        """Extract document metadata"""
        metadata = {}
        for key, value in doc.metadata.items():
            if key and value:
                metadata[key] = value
        return metadata 