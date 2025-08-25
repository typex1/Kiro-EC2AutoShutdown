"""
Unit tests for the main Lambda handler function.

Tests the orchestration logic, error handling, and response formatting.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.lambda_function import lambda_handler, _generate_summary, _create_response
from src.ec2_service import InstanceInfo, ShutdownResult


class TestLambdaHandler:
    """Test cases for the main Lambda handler function."""
    
    @patch('src.lambda_function.EC2Service')
    @patch('src.lambda_function.get_logger')
    @patch('src.lambda_function.config')
    def test_lambda_handler_success_with_instances(self, mock_config, mock_get_logger, mock_ec2_service_class):
        """Test successful execution with instances to stop."""
        # Setup mocks
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_config.shutdown_tag_key = "AutoShutdown"
        mock_config.shutdown_tag_value = "yes"
        mock_config.aws_region = "us-east-1"
        
        mock_ec2_service = Mock()
        mock_ec2_service_class.return_value = mock_ec2_service
        
        # Mock instances
        instances = [
            InstanceInfo("i-123", "running", {"AutoShutdown": "yes"}),
            InstanceInfo("i-456", "stopped", {"AutoShutdown": "yes"})
        ]
        mock_ec2_service.get_instances_with_tag.return_value = instances
        
        # Mock shutdown results
        results = [
            ShutdownResult("i-123", True, previous_state="running"),
            ShutdownResult("i-456", True, previous_state="stopped")
        ]
        mock_ec2_service.stop_instance.side_effect = results
        
        # Execute
        event = {}
        context = Mock()
        response = lambda_handler(event, context)
        
        # Verify
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["processedInstances"] == 2
        assert body["stoppedInstances"] == 1
        assert body["skippedInstances"] == 1
        assert len(body["errors"]) == 0
        
        # Verify service calls
        mock_ec2_service.get_instances_with_tag.assert_called_once_with("AutoShutdown", "yes")
        assert mock_ec2_service.stop_instance.call_count == 2
        
        # Verify logging
        mock_logger.info.assert_called()
        mock_logger.error.assert_not_called()
    
    @patch('src.lambda_function.EC2Service')
    @patch('src.lambda_function.get_logger')
    @patch('src.lambda_function.config')
    def test_lambda_handler_no_instances_found(self, mock_config, mock_get_logger, mock_ec2_service_class):
        """Test execution when no instances are found with the shutdown tag."""
        # Setup mocks
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_config.shutdown_tag_key = "AutoShutdown"
        mock_config.shutdown_tag_value = "yes"
        mock_config.aws_region = "us-east-1"
        
        mock_ec2_service = Mock()
        mock_ec2_service_class.return_value = mock_ec2_service
        mock_ec2_service.get_instances_with_tag.return_value = []
        
        # Execute
        event = {}
        context = Mock()
        response = lambda_handler(event, context)
        
        # Verify
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["processedInstances"] == 0
        assert body["stoppedInstances"] == 0
        assert body["skippedInstances"] == 0
        assert len(body["errors"]) == 0
        assert "No instances found" in body["summary"]
        
        # Verify service calls
        mock_ec2_service.get_instances_with_tag.assert_called_once_with("AutoShutdown", "yes")
        mock_ec2_service.stop_instance.assert_not_called()
    
    @patch('src.lambda_function.EC2Service')
    @patch('src.lambda_function.get_logger')
    @patch('src.lambda_function.config')
    def test_lambda_handler_with_errors(self, mock_config, mock_get_logger, mock_ec2_service_class):
        """Test execution with some instances failing to stop."""
        # Setup mocks
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_config.shutdown_tag_key = "AutoShutdown"
        mock_config.shutdown_tag_value = "yes"
        mock_config.aws_region = "us-east-1"
        
        mock_ec2_service = Mock()
        mock_ec2_service_class.return_value = mock_ec2_service
        
        # Mock instances
        instances = [
            InstanceInfo("i-123", "running", {"AutoShutdown": "yes"}),
            InstanceInfo("i-456", "running", {"AutoShutdown": "yes"})
        ]
        mock_ec2_service.get_instances_with_tag.return_value = instances
        
        # Mock shutdown results with one error
        results = [
            ShutdownResult("i-123", True, previous_state="running"),
            ShutdownResult("i-456", False, error="Permission denied", previous_state="running")
        ]
        mock_ec2_service.stop_instance.side_effect = results
        
        # Execute
        event = {}
        context = Mock()
        response = lambda_handler(event, context)
        
        # Verify
        assert response["statusCode"] == 207  # Multi-status for partial failures
        body = json.loads(response["body"])
        assert body["processedInstances"] == 2
        assert body["stoppedInstances"] == 1
        assert body["skippedInstances"] == 0
        assert len(body["errors"]) == 1
        assert body["errors"][0]["instance_id"] == "i-456"
        assert "Permission denied" in body["errors"][0]["error"]
        
        # Verify logging includes error
        mock_logger.error.assert_called()
    
    @patch('src.lambda_function.EC2Service')
    @patch('src.lambda_function.get_logger')
    @patch('src.lambda_function.config')
    def test_lambda_handler_unexpected_exception(self, mock_config, mock_get_logger, mock_ec2_service_class):
        """Test handling of unexpected exceptions in the Lambda handler."""
        # Setup mocks
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_config.shutdown_tag_key = "AutoShutdown"
        mock_config.shutdown_tag_value = "yes"
        mock_config.aws_region = "us-east-1"
        
        # Make EC2Service initialization raise an exception
        mock_ec2_service_class.side_effect = Exception("Unexpected error")
        
        # Execute
        event = {}
        context = Mock()
        response = lambda_handler(event, context)
        
        # Verify error response
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["processedInstances"] == 0
        assert body["stoppedInstances"] == 0
        assert body["skippedInstances"] == 0
        assert len(body["errors"]) == 1
        assert "Failed to initialize EC2 service" in body["errors"][0]
        assert "Unexpected error" in body["errors"][0]
        assert "Lambda function failed" in body["summary"]
        
        # Verify error logging
        mock_logger.error.assert_called()
    
    @patch('src.lambda_function.EC2Service')
    @patch('src.lambda_function.get_logger')
    @patch('src.lambda_function.config')
    def test_lambda_handler_partial_failure_continues_processing(self, mock_config, mock_get_logger, mock_ec2_service_class):
        """Test that partial failures don't stop the entire process."""
        # Setup mocks
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_config.shutdown_tag_key = "AutoShutdown"
        mock_config.shutdown_tag_value = "yes"
        mock_config.aws_region = "us-east-1"
        
        mock_ec2_service = Mock()
        mock_ec2_service_class.return_value = mock_ec2_service
        
        # Mock instances
        instances = [
            InstanceInfo("i-123", "running", {"AutoShutdown": "yes"}),
            InstanceInfo("i-456", "running", {"AutoShutdown": "yes"}),
            InstanceInfo("i-789", "running", {"AutoShutdown": "yes"})
        ]
        mock_ec2_service.get_instances_with_tag.return_value = instances
        
        # Mock shutdown results with middle one failing
        results = [
            ShutdownResult("i-123", True, previous_state="running"),
            ShutdownResult("i-456", False, error="Network error", previous_state="running"),
            ShutdownResult("i-789", True, previous_state="running")
        ]
        mock_ec2_service.stop_instance.side_effect = results
        
        # Execute
        event = {}
        context = Mock()
        response = lambda_handler(event, context)
        
        # Verify all instances were processed despite middle failure
        assert response["statusCode"] == 207  # Multi-status for partial failures
        body = json.loads(response["body"])
        assert body["processedInstances"] == 3
        assert body["stoppedInstances"] == 2
        assert body["skippedInstances"] == 0
        assert len(body["errors"]) == 1
        
        # Verify all stop_instance calls were made
        assert mock_ec2_service.stop_instance.call_count == 3
    
    @patch('src.lambda_function.EC2Service')
    @patch('src.lambda_function.get_logger')
    @patch('src.lambda_function.config')
    def test_lambda_handler_ec2_service_initialization_failure(self, mock_config, mock_get_logger, mock_ec2_service_class):
        """Test handling of EC2 service initialization failure."""
        # Setup mocks
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_config.shutdown_tag_key = "AutoShutdown"
        mock_config.shutdown_tag_value = "yes"
        mock_config.aws_region = "us-east-1"
        
        # Make EC2Service initialization raise a specific exception
        mock_ec2_service_class.side_effect = Exception("AWS credentials not found")
        
        # Execute
        event = {}
        context = Mock()
        response = lambda_handler(event, context)
        
        # Verify error response
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["processedInstances"] == 0
        assert body["stoppedInstances"] == 0
        assert body["skippedInstances"] == 0
        assert len(body["errors"]) == 1
        assert "Failed to initialize EC2 service" in body["errors"][0]
        assert "AWS credentials not found" in body["errors"][0]
        
        # Verify error logging
        mock_logger.error.assert_called()
    
    @patch('src.lambda_function.EC2Service')
    @patch('src.lambda_function.get_logger')
    @patch('src.lambda_function.config')
    def test_lambda_handler_instance_discovery_failure(self, mock_config, mock_get_logger, mock_ec2_service_class):
        """Test handling of instance discovery failure."""
        # Setup mocks
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_config.shutdown_tag_key = "AutoShutdown"
        mock_config.shutdown_tag_value = "yes"
        mock_config.aws_region = "us-east-1"
        
        mock_ec2_service = Mock()
        mock_ec2_service_class.return_value = mock_ec2_service
        
        # Make get_instances_with_tag raise an exception
        mock_ec2_service.get_instances_with_tag.side_effect = Exception("API rate limit exceeded")
        
        # Execute
        event = {}
        context = Mock()
        response = lambda_handler(event, context)
        
        # Verify error response
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["processedInstances"] == 0
        assert body["stoppedInstances"] == 0
        assert body["skippedInstances"] == 0
        assert len(body["errors"]) == 1
        assert "Failed to discover instances" in body["errors"][0]
        assert "API rate limit exceeded" in body["errors"][0]
        
        # Verify error logging
        mock_logger.error.assert_called()
    
    @patch('src.lambda_function.EC2Service')
    @patch('src.lambda_function.get_logger')
    @patch('src.lambda_function.config')
    def test_lambda_handler_individual_instance_processing_exception(self, mock_config, mock_get_logger, mock_ec2_service_class):
        """Test handling of exceptions during individual instance processing."""
        # Setup mocks
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_config.shutdown_tag_key = "AutoShutdown"
        mock_config.shutdown_tag_value = "yes"
        mock_config.aws_region = "us-east-1"
        
        mock_ec2_service = Mock()
        mock_ec2_service_class.return_value = mock_ec2_service
        
        # Mock instances
        instances = [
            InstanceInfo("i-123", "running", {"AutoShutdown": "yes"}),
            InstanceInfo("i-456", "running", {"AutoShutdown": "yes"}),
            InstanceInfo("i-789", "running", {"AutoShutdown": "yes"})
        ]
        mock_ec2_service.get_instances_with_tag.return_value = instances
        
        # Mock stop_instance to raise exception for middle instance
        def stop_instance_side_effect(instance_id):
            if instance_id == "i-456":
                raise Exception("Unexpected network error")
            elif instance_id == "i-123":
                return ShutdownResult("i-123", True, previous_state="running")
            else:
                return ShutdownResult("i-789", True, previous_state="running")
        
        mock_ec2_service.stop_instance.side_effect = stop_instance_side_effect
        
        # Execute
        event = {}
        context = Mock()
        response = lambda_handler(event, context)
        
        # Verify processing continued despite exception
        assert response["statusCode"] == 207  # Multi-status for partial failures
        body = json.loads(response["body"])
        assert body["processedInstances"] == 3
        assert body["stoppedInstances"] == 2
        assert body["skippedInstances"] == 0
        assert len(body["errors"]) == 1
        assert body["errors"][0]["instance_id"] == "i-456"
        assert "Unexpected error processing instance" in body["errors"][0]["error"]
        
        # Verify all instances were attempted
        assert mock_ec2_service.stop_instance.call_count == 3
    
    @patch('src.lambda_function.EC2Service')
    @patch('src.lambda_function.get_logger')
    @patch('src.lambda_function.config')
    def test_lambda_handler_all_instances_fail(self, mock_config, mock_get_logger, mock_ec2_service_class):
        """Test handling when all instances fail to stop."""
        # Setup mocks
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_config.shutdown_tag_key = "AutoShutdown"
        mock_config.shutdown_tag_value = "yes"
        mock_config.aws_region = "us-east-1"
        
        mock_ec2_service = Mock()
        mock_ec2_service_class.return_value = mock_ec2_service
        
        # Mock instances
        instances = [
            InstanceInfo("i-123", "running", {"AutoShutdown": "yes"}),
            InstanceInfo("i-456", "running", {"AutoShutdown": "yes"})
        ]
        mock_ec2_service.get_instances_with_tag.return_value = instances
        
        # Mock all shutdown results as failures
        results = [
            ShutdownResult("i-123", False, error="Permission denied", previous_state="running"),
            ShutdownResult("i-456", False, error="Instance not found", previous_state="running")
        ]
        mock_ec2_service.stop_instance.side_effect = results
        
        # Execute
        event = {}
        context = Mock()
        response = lambda_handler(event, context)
        
        # Verify multi-status response when all fail
        assert response["statusCode"] == 207  # Multi-status for all failures
        body = json.loads(response["body"])
        assert body["processedInstances"] == 2
        assert body["stoppedInstances"] == 0
        assert body["skippedInstances"] == 0
        assert len(body["errors"]) == 2
        
        # Verify error logging
        assert mock_logger.error.call_count >= 2


class TestGenerateSummary:
    """Test cases for the _generate_summary helper function."""
    
    def test_generate_summary_all_successful(self):
        """Test summary generation with all successful results."""
        results = [
            ShutdownResult("i-123", True, previous_state="running"),
            ShutdownResult("i-456", True, previous_state="running")
        ]
        
        summary = _generate_summary(results)
        
        assert summary["processedInstances"] == 2
        assert summary["stoppedInstances"] == 2
        assert summary["skippedInstances"] == 0
        assert len(summary["errors"]) == 0
    
    def test_generate_summary_with_skipped_instances(self):
        """Test summary generation with already stopped instances."""
        results = [
            ShutdownResult("i-123", True, previous_state="running"),
            ShutdownResult("i-456", True, previous_state="stopped"),
            ShutdownResult("i-789", True, previous_state="stopping")
        ]
        
        summary = _generate_summary(results)
        
        assert summary["processedInstances"] == 3
        assert summary["stoppedInstances"] == 1
        assert summary["skippedInstances"] == 2
        assert len(summary["errors"]) == 0
    
    def test_generate_summary_with_errors(self):
        """Test summary generation with failed operations."""
        results = [
            ShutdownResult("i-123", True, previous_state="running"),
            ShutdownResult("i-456", False, error="Permission denied"),
            ShutdownResult("i-789", False, error="Instance not found")
        ]
        
        summary = _generate_summary(results)
        
        assert summary["processedInstances"] == 3
        assert summary["stoppedInstances"] == 1
        assert summary["skippedInstances"] == 0
        assert len(summary["errors"]) == 2
        assert summary["errors"][0]["instance_id"] == "i-456"
        assert summary["errors"][1]["instance_id"] == "i-789"
    
    def test_generate_summary_empty_results(self):
        """Test summary generation with empty results list."""
        results = []
        
        summary = _generate_summary(results)
        
        assert summary["processedInstances"] == 0
        assert summary["stoppedInstances"] == 0
        assert summary["skippedInstances"] == 0
        assert len(summary["errors"]) == 0


class TestCreateResponse:
    """Test cases for the _create_response helper function."""
    
    def test_create_response_success(self):
        """Test creating a successful response."""
        body = {
            "processedInstances": 2,
            "stoppedInstances": 1,
            "summary": "Test summary"
        }
        
        response = _create_response(200, body)
        
        assert response["statusCode"] == 200
        parsed_body = json.loads(response["body"])
        assert parsed_body == body
    
    def test_create_response_error(self):
        """Test creating an error response."""
        body = {
            "errors": ["Test error"],
            "summary": "Error occurred"
        }
        
        response = _create_response(500, body)
        
        assert response["statusCode"] == 500
        parsed_body = json.loads(response["body"])
        assert parsed_body == body
    
    def test_create_response_json_formatting(self):
        """Test that response body is properly formatted JSON."""
        body = {"test": "value"}
        
        response = _create_response(200, body)
        
        # Should be valid JSON
        parsed = json.loads(response["body"])
        assert parsed == body
        
        # Should be formatted with indentation
        assert "  " in response["body"]  # Check for indentation


class TestCreateErrorResponse:
    """Test cases for the _create_error_response helper function."""
    
    def test_create_error_response_format(self):
        """Test that error response has correct format."""
        from src.lambda_function import _create_error_response
        
        error_message = "Test error message"
        response = _create_error_response(error_message)
        
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        
        # Verify standard error response structure
        assert body["processedInstances"] == 0
        assert body["stoppedInstances"] == 0
        assert body["skippedInstances"] == 0
        assert len(body["errors"]) == 1
        assert body["errors"][0] == error_message
        assert "Lambda function failed" in body["summary"]
    
    def test_create_error_response_json_formatting(self):
        """Test that error response body is properly formatted JSON."""
        from src.lambda_function import _create_error_response
        
        response = _create_error_response("Test error")
        
        # Should be valid JSON
        parsed = json.loads(response["body"])
        assert isinstance(parsed, dict)
        
        # Should be formatted with indentation
        assert "  " in response["body"]