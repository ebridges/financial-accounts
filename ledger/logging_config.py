# logging_config.py
"""
Centralized logging configuration for the ledger application.

Usage:
    from ledger.logging_config import configure_logging
    configure_logging()  # Uses INFO by default
    configure_logging(level='DEBUG')  # Or specify level

Environment variable:
    LEDGER_LOG_LEVEL - Set to DEBUG, INFO, WARNING, or ERROR
"""
import logging
import os

DEFAULT_FORMAT = '%(asctime)s %(levelname)-8s %(name)s:%(funcName)s:%(lineno)d - %(message)s'
DEFAULT_LEVEL = 'INFO'


def configure_logging(
    level: str | None = None,
    format_string: str = DEFAULT_FORMAT,
) -> None:
    """
    Configure logging for the ledger application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
               Falls back to LEDGER_LOG_LEVEL env var, then DEFAULT_LEVEL.
        format_string: Log message format.
    """
    # Priority: explicit arg > env var > default
    log_level = level or os.environ.get('LEDGER_LOG_LEVEL', DEFAULT_LEVEL)

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=numeric_level,
        format=format_string,
    )

    # Set level for our package loggers
    logging.getLogger('ledger').setLevel(numeric_level)
