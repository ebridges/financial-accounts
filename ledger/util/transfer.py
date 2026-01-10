# transfer.py
"""Utilities for handling inter-account transfers."""
import re


def extract_transfer_reference(description: str) -> str | None:
    """
    Extract transaction# from Chase checking transfer descriptions.

    Chase checking-to-checking transfers embed a unique transaction number
    that appears in both accounts' QIF files:
    - "Online Transfer to CHK ...1605 transaction#: 11104475445 02/08"
    - "Online Transfer from CHK ...1381 transaction#: 11104475445"

    Returns the transaction number (e.g., "11104475445") or None if not found.
    """
    if not description:
        return None
    match = re.search(r'transaction#:\s*(\d+)', description, re.IGNORECASE)
    return match.group(1) if match else None
