"""
Unit tests for the structured logging module.
"""

import json
import logging
import uuid
from io import StringIO
from unittest.mock import patch
import pytest

from src.logger import StructuredLogger, JsonFormatter, get_logger


class TestStructuredLogger:
    """Test cases for StructuredLogger class."""
    
    def test_logger_initialization(self):
        """Test logger initialization with default values."""
        logger = StructuredLogger()
        
        assert logger.logger.name == "ec2-auto-shutdown"
        assert logger.logger.level == logging.INFO
        assert logger.correlation_id is not None
        assert len(logger.correlation_id) > 0
    
    def test_logger_initialization_with_custom_values(self):
        """Test logger initialization with custom name and correlation ID."""
        custom_name = "test-logger"
        custom_correlation_id = "test-correlation-123"
        
        logger = StructuredLogger(custom_name, custom_correlation_id)
        
        assert logger.logger.name == custom_name
        assert logger.correlation_id == custom_correlation_id
    
    @patch('sys.stdout', new_callable=StringIO)
    def test_info_logging(self, mock_stdout):
        """Test INFO level logging with JSON output."""
        logger = StructuredLogger(correlation_id="test-123")
        
        with patch('src.logger.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value.isoformat.return_value = "2023-01-01T12:00:00"
            
            logger.info("Test info message", instance_id="i-123456", action="start")
        
        output = mock_stdout.getvalue().strip()
        log_data = json.loads(output)
        
        assert log_data["level"] == "INFO"
        assert log_data["message"] == "Test info message"
        assert log_data["correlation_id"] == "test-123"
        assert log_data["timestamp"] == "2023-01-01T12:00:00Z"
        assert log_data["instance_id"] == "i-123456"
        assert log_data["action"] == "start"
    
    @patch('sys.stdout', new_callable=StringIO)
    def test_warn_logging(self, mock_stdout):
        """Test WARN level logging with JSON output."""
        logger = StructuredLogger(correlation_id="test-456")
        
        with patch('src.logger.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value.isoformat.return_value = "2023-01-01T12:00:00"
            
            logger.warn("Test warning message", error_code="THROTTLE")
        
        output = mock_stdout.getvalue().strip()
        log_data = json.loads(output)
        
        assert log_data["level"] == "WARN"
        assert log_data["message"] == "Test warning message"
        assert log_data["correlation_id"] == "test-456"
        assert log_data["error_code"] == "THROTTLE"
    
    @patch('sys.stdout', new_callable=StringIO)
    def test_error_logging(self, mock_stdout):
        """Test ERROR level logging with JSON output."""
        logger = StructuredLogger(correlation_id="test-789")
        
        with patch('src.logger.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value.isoformat.return_value = "2023-01-01T12:00:00"
            
            logger.error("Test error message", exception="PermissionDenied", instance_id="i-789")
        
        output = mock_stdout.getvalue().strip()
        log_data = json.loads(output)
        
        assert log_data["level"] == "ERROR"
        assert log_data["message"] == "Test error message"
        assert log_data["correlation_id"] == "test-789"
        assert log_data["exception"] == "PermissionDenied"
        assert log_data["instance_id"] == "i-789"
    
    def test_set_correlation_id(self):
        """Test updating correlation ID."""
        logger = StructuredLogger()
        original_id = logger.correlation_id
        
        new_id = "new-correlation-id"
        logger.set_correlation_id(new_id)
        
        assert logger.correlation_id == new_id
        assert logger.correlation_id != original_id
    
    @patch('sys.stdout', new_callable=StringIO)
    def test_correlation_id_in_all_logs(self, mock_stdout):
        """Test that correlation ID is included in all log levels."""
        correlation_id = "consistent-id-123"
        logger = StructuredLogger(correlation_id=correlation_id)
        
        with patch('src.logger.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value.isoformat.return_value = "2023-01-01T12:00:00"
            
            logger.info("Info message")
            logger.warn("Warning message")
            logger.error("Error message")
        
        output_lines = mock_stdout.getvalue().strip().split('\n')
        
        for line in output_lines:
            log_data = json.loads(line)
            assert log_data["correlation_id"] == correlation_id
    
    @patch('sys.stdout', new_callable=StringIO)
    def test_json_structure_consistency(self, mock_stdout):
        """Test that all logs have consistent JSON structure."""
        logger = StructuredLogger(correlation_id="structure-test")
        
        with patch('src.logger.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value.isoformat.return_value = "2023-01-01T12:00:00"
            
            logger.info("Test message", custom_field="value")
        
        output = mock_stdout.getvalue().strip()
        log_data = json.loads(output)
        
        # Check required fields are present
        required_fields = ["timestamp", "level", "message", "correlation_id"]
        for field in required_fields:
            assert field in log_data
        
        # Check timestamp format
        assert log_data["timestamp"].endswith("Z")
        assert "T" in log_data["timestamp"]
        
        # Check custom fields are preserved
        assert log_data["custom_field"] == "value"
    
    def test_logger_handler_configuration(self):
        """Test that logger is properly configured with handlers."""
        logger = StructuredLogger()
        
        # Should have exactly one handler
        assert len(logger.logger.handlers) == 1
        
        # Handler should be StreamHandler
        handler = logger.logger.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        
        # Handler should have JsonFormatter
        assert isinstance(handler.formatter, JsonFormatter)
        
        # Logger should not propagate to avoid duplicate logs
        assert not logger.logger.propagate


class TestJsonFormatter:
    """Test cases for JsonFormatter class."""
    
    def test_format_method(self):
        """Test that formatter returns the message as-is (already JSON)."""
        formatter = JsonFormatter()
        
        # Create a mock log record
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg='{"test": "message"}',
            args=(),
            exc_info=None
        )
        
        formatted = formatter.format(record)
        assert formatted == '{"test": "message"}'


class TestGetLogger:
    """Test cases for get_logger factory function."""
    
    def test_get_logger_default(self):
        """Test get_logger with default parameters."""
        logger = get_logger()
        
        assert isinstance(logger, StructuredLogger)
        assert logger.logger.name == "ec2-auto-shutdown"
        assert logger.correlation_id is not None
    
    def test_get_logger_with_parameters(self):
        """Test get_logger with custom parameters."""
        name = "custom-logger"
        correlation_id = "custom-correlation"
        
        logger = get_logger(name, correlation_id)
        
        assert isinstance(logger, StructuredLogger)
        assert logger.logger.name == name
        assert logger.correlation_id == correlation_id
    
    def test_multiple_logger_instances(self):
        """Test that multiple logger instances have different correlation IDs by default."""
        logger1 = get_logger()
        logger2 = get_logger()
        
        assert logger1.correlation_id != logger2.correlation_id


class TestLoggingIntegration:
    """Integration tests for logging functionality."""
    
    @patch('sys.stdout', new_callable=StringIO)
    def test_logging_workflow_simulation(self, mock_stdout):
        """Test a complete logging workflow similar to Lambda function usage."""
        # Simulate Lambda function start
        logger = get_logger("ec2-auto-shutdown", "lambda-request-123")
        
        with patch('src.logger.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value.isoformat.return_value = "2023-01-01T12:00:00"
            
            # Log function start
            logger.info("Starting EC2 auto-shutdown process", region="us-east-1")
            
            # Log instance discovery
            logger.info("Found instance for shutdown", instance_id="i-123456", state="running")
            
            # Log successful shutdown
            logger.info("Successfully stopped instance", instance_id="i-123456", previous_state="running")
            
            # Log process completion
            logger.info("EC2 auto-shutdown process completed", 
                       processed_instances=1, stopped_instances=1)
        
        output_lines = mock_stdout.getvalue().strip().split('\n')
        assert len(output_lines) == 4
        
        # Verify all logs have same correlation ID
        correlation_ids = []
        for line in output_lines:
            log_data = json.loads(line)
            correlation_ids.append(log_data["correlation_id"])
        
        assert all(cid == "lambda-request-123" for cid in correlation_ids)
        
        # Verify log content
        log1 = json.loads(output_lines[0])
        assert "Starting EC2 auto-shutdown process" in log1["message"]
        assert log1["region"] == "us-east-1"
        
        log2 = json.loads(output_lines[1])
        assert "Found instance for shutdown" in log2["message"]
        assert log2["instance_id"] == "i-123456"