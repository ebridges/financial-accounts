# normalize.py
"""
Utility functions for normalizing transaction data.
"""
import re


def normalize_payee(description: str) -> str:
    """
    Normalize a payee description for categorization matching.
    
    Normalization steps:
    - Uppercase
    - Collapse whitespace
    - Strip trailing transaction IDs, card numbers, dates
    - Remove common suffixes (city/state abbreviations often appended)
    
    Args:
        description: Raw payee/description string
        
    Returns:
        Normalized payee string
    """
    if not description:
        return ""
    
    payee = description.upper().strip()
    
    # Collapse multiple whitespace to single space
    payee = re.sub(r'\s+', ' ', payee)
    
    # Remove trailing transaction numbers (e.g., "PPD ID: 1234567890")
    payee = re.sub(r'\s+PPD ID:\s*\d+$', '', payee)
    
    # Remove trailing transaction# references (must be before card number strip)
    payee = re.sub(r'\s+TRANSACTION#:\s*\d+.*$', '', payee, flags=re.IGNORECASE)
    
    # Remove trailing reference numbers (generic alphanumeric)
    payee = re.sub(r'\s+#?\d{6,}$', '', payee)
    
    # Remove trailing card numbers (e.g., "XXXX1234" or "...1234")
    payee = re.sub(r'\s+(?:XXXX|\.\.\.)?\d{4}$', '', payee)
    
    # Remove trailing dates (e.g., "07/14" or "07/14/2024")
    payee = re.sub(r'\s+\d{2}/\d{2}(?:/\d{2,4})?$', '', payee)
    
    # Strip again after removals
    payee = payee.strip()
    
    return payee
