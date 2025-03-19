import re
import base64
import math
from typing import List, Dict, Any

class EncodingDetector:
    """
    Detects various types of encoding in text content extracted from PDFs.
    """
    
    def __init__(self):
        # Minimum length for encoded strings to reduce false positives
        self.min_length = 16
        
        # Compile regex patterns for better performance
        self.patterns = {
            'base64': re.compile(r'[A-Za-z0-9+/]{' + str(self.min_length) + r',}={0,3}'),
            'hex': re.compile(r'[0-9A-Fa-f]{' + str(self.min_length) + r',}'),
            'url': re.compile(r'(?:%[0-9A-Fa-f]{2}){3,}'),
            'unicode_escape': re.compile(r'(?:\\u[0-9A-Fa-f]{4}){2,}'),
            'binary': re.compile(r'[01]{' + str(self.min_length * 4) + r',}')
        }
    
    def calculate_entropy(self, text: str) -> float:
        """
        Calculate Shannon entropy of a string.
        Higher values (closer to 8) suggest encrypted or encoded content.
        """
        if not text:
            return 0
            
        # Count character frequencies
        char_count = {}
        for char in text:
            if char in char_count:
                char_count[char] += 1
            else:
                char_count[char] = 1
        
        # Calculate entropy
        length = len(text)
        entropy = 0
        for count in char_count.values():
            probability = count / length
            entropy -= probability * math.log2(probability)
            
        return entropy
    
    def is_readable_text(self, text: str) -> bool:
        """
        Check if a string appears to be readable text.
        """
        if not text:
            return False
            
        # Check if string contains both letters and common punctuation
        has_letters = any(c.isalpha() for c in text)
        has_common_chars = any(c in ' .,;:?!-()[]{}"\'' for c in text)
        printable_ratio = sum(c.isprintable() for c in text) / len(text)
        
        # Readable text typically has letters, some common punctuation,
        # and most characters are printable
        return has_letters and has_common_chars and printable_ratio > 0.95
    
    def detect_base64(self, text: str) -> List[Dict[str, Any]]:
        """
        Detect potential Base64 encoded strings.
        """
        findings = []
        
        for match in self.patterns['base64'].finditer(text):
            encoded = match.group(0)
            # Skip if it's too short after removing any padding
            if len(encoded.rstrip('=')) < self.min_length:
                continue
                
            # Try to decode and check if result is readable
            try:
                # Add padding if needed
                padding = 4 - (len(encoded) % 4) if len(encoded) % 4 else 0
                padded = encoded + ('=' * padding)
                
                decoded = base64.b64decode(padded)
                
                # Try to decode as UTF-8 text
                try:
                    decoded_text = decoded.decode('utf-8')
                    if self.is_readable_text(decoded_text):
                        findings.append({
                            "type": "base64",
                            "content": encoded,
                            "sample_decoded": decoded_text[:50] + ('...' if len(decoded_text) > 50 else ''),
                            "confidence": 0.9
                        })
                except UnicodeDecodeError:
                    # Not valid UTF-8, might be binary data
                    # Check entropy to see if it might be encrypted data
                    binary_entropy = self.calculate_entropy(''.join(format(byte, '08b') for byte in decoded))
                    if binary_entropy > 7.0:
                        findings.append({
                            "type": "base64_binary",
                            "content": encoded,
                            "entropy": binary_entropy,
                            "confidence": 0.7
                        })
            except:
                # Not valid Base64
                pass
                
        return findings
    
    def detect_hex(self, text: str) -> List[Dict[str, Any]]:
        """
        Detect potential hexadecimal encoded strings.
        """
        findings = []
        
        for match in self.patterns['hex'].finditer(text):
            encoded = match.group(0)
            
            # Skip if it's not a valid hex string (must have even length)
            if len(encoded) % 2 != 0:
                continue
                
            # Try to decode
            try:
                decoded = bytes.fromhex(encoded)
                
                # Try to decode as UTF-8 text
                try:
                    decoded_text = decoded.decode('utf-8')
                    if self.is_readable_text(decoded_text):
                        findings.append({
                            "type": "hexadecimal",
                            "content": encoded,
                            "sample_decoded": decoded_text[:50] + ('...' if len(decoded_text) > 50 else ''),
                            "confidence": 0.85
                        })
                except UnicodeDecodeError:
                    # Not valid UTF-8, might be binary data
                    binary_entropy = self.calculate_entropy(''.join(format(byte, '08b') for byte in decoded))
                    if binary_entropy > 7.0:
                        findings.append({
                            "type": "hex_binary",
                            "content": encoded,
                            "entropy": binary_entropy,
                            "confidence": 0.6
                        })
            except:
                # Not valid hex
                pass
                
        return findings
    
    def detect_url_encoding(self, text: str) -> List[Dict[str, Any]]:
        """
        Detect potential URL encoded strings.
        """
        findings = []
        
        for match in self.patterns['url'].finditer(text):
            encoded = match.group(0)
            
            # Try to decode
            try:
                # Replace % with %25 to handle literal % signs
                decoded = bytes.fromhex(encoded.replace('%', ''))
                
                try:
                    decoded_text = decoded.decode('utf-8')
                    if self.is_readable_text(decoded_text):
                        findings.append({
                            "type": "url_encoding",
                            "content": encoded,
                            "sample_decoded": decoded_text[:50] + ('...' if len(decoded_text) > 50 else ''),
                            "confidence": 0.8
                        })
                except UnicodeDecodeError:
                    pass
            except:
                pass
                
        return findings
    
    def detect_high_entropy(self, text: str, block_size: int = 100) -> List[Dict[str, Any]]:
        """
        Detect text blocks with unusually high entropy.
        """
        findings = []
        
        # Skip very short texts
        if len(text) < block_size / 2:
            return findings
            
        # Split text into blocks
        blocks = [text[i:i+block_size] for i in range(0, len(text), block_size)]
        
        for i, block in enumerate(blocks):
            # Skip short blocks
            if len(block) < block_size / 2:
                continue
                
            entropy = self.calculate_entropy(block)
            
            # Natural language typically has entropy between 3.5 and 5.0
            # Higher values suggest encryption or encoding
            if entropy > 7.0:
                findings.append({
                    "type": "high_entropy",
                    "block_index": i,
                    "content": block[:50] + ('...' if len(block) > 50 else ''),
                    "entropy": entropy,
                    "confidence": min(0.5 + (entropy - 7.0) / 2.0, 0.95)  # Scale confidence with entropy
                })
                
        return findings
    
    def detect_encodings(self, text: str) -> Dict[str, Any]:
        """
        Detect various types of encoding in text and determine if content is suspicious.
        """
        if not text or len(text) < self.min_length:
            return {
                'findings': [],
                'suspicious': False,
                'suspicion_score': 0.0,
                'suspicion_reasons': []
            }
            
        findings = []
        
        # Run all detection methods
        base64_findings = self.detect_base64(text)
        hex_findings = self.detect_hex(text)
        url_findings = self.detect_url_encoding(text)
        entropy_findings = self.detect_high_entropy(text)
        
        findings.extend(base64_findings)
        findings.extend(hex_findings)
        findings.extend(url_findings)
        findings.extend(entropy_findings)
        
        # Calculate suspicion score
        suspicion_score = 0
        suspicion_reasons = []
        
        # Check density of encoded patterns
        total_patterns = len(findings)
        text_length = len(text)
        pattern_density = total_patterns / (text_length / 1000)  # patterns per 1000 characters
        
        if pattern_density > 0.5:  # More than 1 pattern per 2000 characters
            suspicion_score += pattern_density
            suspicion_reasons.append(f"High pattern density: {pattern_density:.2f} patterns per 1000 chars")
        
        # Check high confidence findings
        high_confidence_patterns = sum(1 for f in findings if f.get('confidence', 0) > 0.8)
        if high_confidence_patterns >= 3:
            suspicion_score += high_confidence_patterns * 0.5
            suspicion_reasons.append(f"Multiple high-confidence patterns: {high_confidence_patterns}")
        
        # Check high entropy blocks
        high_entropy_blocks = sum(1 for f in entropy_findings if f.get('entropy', 0) > 7.5)
        if high_entropy_blocks > 0:
            suspicion_score += high_entropy_blocks
            suspicion_reasons.append(f"High entropy blocks found: {high_entropy_blocks}")
        
        # Check for base64 patterns (often used for scripts/executables)
        base64_patterns = len(base64_findings)
        if base64_patterns > 2:
            suspicion_score += base64_patterns * 0.7
            suspicion_reasons.append(f"Multiple Base64 patterns: {base64_patterns}")
        
        # Sort findings by confidence
        findings.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        
        # Add suspicion assessment to results
        result = {
            'findings': findings,
            'suspicious': suspicion_score > 5.0,  # Threshold for flagging as suspicious
            'suspicion_score': round(suspicion_score, 2),
            'suspicion_reasons': suspicion_reasons if suspicion_score > 5.0 else []
        }
        
        return result 