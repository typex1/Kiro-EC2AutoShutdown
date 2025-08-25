"""
Structured logging module for EC2 Auto-Shutdown Lambda function.

Provides JSON-formatted logging with correlation ID support for CloudWatch.
"""

import json
import logging
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, Optional


class StructuredLogger:
    """
    Structured logger that outputs JSON formatted logs for CloudWatch.
    
    Supports correlation IDs for request tracing and different log levels.
    """
    
    def __init__(self, name: str = "ec2-auto-shutdown", correlation_id: Optional[str] = None):
        """
        Initialize the structured logger.
        
        Args:
            name: Logger name
            correlation_id: Optional correlation ID for request tracing
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplicates
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # Create console handler with JSON formatter
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        
        # Set JSON formatter
        formatter = JsonFormatter()
        handler.setFormatter(formatter)
        
        self.logger.addHandler(handler)
        self.logger.propagate = False
        
        # Set correlation ID
        self.correlation_id = correlation_id or str(uuid.uuid4())
    
    def _log(self, level: str, message: str, **kwargs) -> None:
        """
        Internal method to log structured messages.
        
        Args:
            level: Log level (INFO, WARN, ERROR)
            message: Log message
            **kwargs: Additional fields to include in log
        """
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message,
            "correlation_id": self.correlation_id,
            **kwargs
        }
        
        # Use appropriate logging level
        if level == "INFO":
            self.logger.info(json.dumps(log_data))
        elif level == "WARN":
            self.logger.warning(json.dumps(log_data))
        elif level == "ERROR":
            self.logger.error(json.dumps(log_data))
    
    def info(self, message: str, **kwargs) -> None:
        """Log an info message."""
        self._log("INFO", message, **kwargs)
    
    def warn(self, message: str, **kwargs) -> None:
        """Log a warning message."""
        self._log("WARN", message, **kwargs)
    
    def error(self, message: str, **kwargs) -> None:
        """Log an error message."""
        self._log("ERROR", message, **kwargs)
    
    def set_correlation_id(self, correlation_id: str) -> None:
        """Update the correlation ID for this logger instance."""
        self.correlation_id = correlation_id


class JsonFormatter(logging.Formatter):
    """
    Custom formatter that outputs logs in JSON format.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record as JSON.
        
        Args:
            record: The log record to format
            
        Returns:
            JSON formatted log string
        """
        # The message should already be JSON from StructuredLogger._log
        return record.getMessage()


def get_logger(name: str = "ec2-auto-shutdown", correlation_id: Optional[str] = None) -> StructuredLogger:
    """
    Factory function to get a structured logger instance.
    
    Args:
        name: Logger name
        correlation_id: Optional correlation ID for request tracing
        
    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(name, correlation_id)