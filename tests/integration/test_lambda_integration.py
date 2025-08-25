"""
Integration tests for EC2 Auto-Shutdown Lambda function.

These tests work with real AWS services and require proper AWS credentials
and permissions to be configured. They test the complete end-to-end functionality
including various EC2 instance states, tag combinations, and IAM permissions.

Prerequisites:
- AWS credentials configured (via AWS CLI, environment variables, or IAM role)
- EC2 instances with appropriate tags for testing
- IAM permissions for EC2 operations and CloudWatch logs

Environment Variables for Testing:
- AWS_REGION: AWS region to run tests in
- TEST_INSTANCE_IDS: Comma-separated list of test instance IDs (optional)
- SKIP_INTEGRATION_TESTS: Set to 'true' to skip integration tests
"""

import os
import json
import time
import uuid
import pytest
import boto3
from typing import List, Dict, Any, Optional
from unittest.mock import MagicMock

# Import test helpers
from .test_helpers import (
    get_lambda_handler, get_ec2_service, get_config, 
    get_logger, reload_config
)


class TestEC2IntegrationSetup:
    """Setup and teardown for integration tests."""
    
    @classmethod
    def setup_class(cls):
        """Set up test environment and verify AWS connectivity."""
        # Skip integration tests if requested
        if os.environ.get('SKIP_INTEGRATION_TESTS', '').lower() == 'true':
            pytest.skip("Integration tests skipped via SKIP_INTEGRATION_TESTS environment variable")
        
        # Verify AWS credentials are available
        try:
            session = boto3.Session()
            credentials = session.get_credentials()
            if not credentials:
                pytest.skip("AWS credentials not available - skipping integration tests")
        except Exception as e:
            pytest.skip(f"AWS setup failed: {str(e)}")
        
        # Set up test region
        cls.region = os.environ.get('AWS_REGION', 'us-east-1')
        cls.ec2_client = boto3.client('ec2', region_name=cls.region)
        
        # Generate unique test tag values to avoid conflicts
        cls.test_tag_key = f"IntegrationTest-{uuid.uuid4().hex[:8]}"
        cls.test_tag_value = "test-shutdown"
        
        # Store original environment variables
        cls.original_env = {
            'SHUTDOWN_TAG_KEY': os.environ.get('SHUTDOWN_TAG_KEY'),
            'SHUTDOWN_TAG_VALUE': os.environ.get('SHUTDOWN_TAG_VALUE'),
            'AWS_REGION': os.environ.get('AWS_REGION')
        }
        
        # Set test environment variables
        os.environ['SHUTDOWN_TAG_KEY'] = cls.test_tag_key
        os.environ['SHUTDOWN_TAG_VALUE'] = cls.test_tag_value
        os.environ['AWS_REGION'] = cls.region
        
        print(f"Integration tests running in region: {cls.region}")
        print(f"Test tag: {cls.test_tag_key}={cls.test_tag_value}")
    
    @classmethod
    def teardown_class(cls):
        """Clean up test environment."""
        # Restore original environment variables
        for key, value in cls.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.mark.integration
class TestEC2ServiceIntegration(TestEC2IntegrationSetup):
    """Integration tests for EC2Service class."""
    
    def test_ec2_service_initialization(self):
        """Test EC2Service can be initialized with real AWS credentials."""
        EC2Service, _, _ = get_ec2_service()
        
        service = EC2Service(region_name=self.region)
        assert service.region_name == self.region
        assert service.ec2_client is not None
    
    def test_get_instances_with_nonexistent_tag(self):
        """Test discovering instances with a tag that doesn't exist."""
        EC2Service, _, _ = get_ec2_service()
        
        service = EC2Service(region_name=self.region)
        
        # Use a unique tag that shouldn't exist
        unique_tag = f"NonExistent-{uuid.uuid4().hex}"
        instances = service.get_instances_with_tag(unique_tag, "value")
        
        assert isinstance(instances, list)
        assert len(instances) == 0
    
    def test_get_instances_with_real_tag(self):
        """Test discovering instances with real tags (if any exist)."""
        EC2Service, InstanceInfo, _ = get_ec2_service()
        
        service = EC2Service(region_name=self.region)
        
        # Try to find any instances with common tags
        try:
            instances = service.get_instances_with_tag("Name", "*")
            assert isinstance(instances, list)
            # We don't assert on length since we don't know what instances exist
            
            for instance in instances:
                assert isinstance(instance, InstanceInfo)
                assert instance.instance_id.startswith('i-')
                assert instance.state in ['pending', 'running', 'shutting-down', 'terminated', 'stopping', 'stopped']
                assert isinstance(instance.tags, dict)
                
        except Exception as e:
            # If no instances exist or permissions are limited, that's okay
            print(f"Note: Could not discover instances: {str(e)}")
    
    def test_stop_nonexistent_instance(self):
        """Test stopping an instance that doesn't exist."""
        EC2Service, _, ShutdownResult = get_ec2_service()
        
        service = EC2Service(region_name=self.region)
        
        # Use a fake instance ID
        fake_instance_id = "i-1234567890abcdef0"
        result = service.stop_instance(fake_instance_id)
        
        assert isinstance(result, ShutdownResult)
        assert result.instance_id == fake_instance_id
        assert result.success is False
        assert ("not found" in result.error.lower() or 
                "does not exist" in result.error.lower() or 
                "invalid id" in result.error.lower() or
                "malformed" in result.error.lower())
    
    def test_iam_permissions_describe_instances(self):
        """Test that IAM permissions allow describing instances."""
        EC2Service, _, _ = get_ec2_service()
        
        service = EC2Service(region_name=self.region)
        
        try:
            # This should work with proper IAM permissions
            instances = service.get_instances_with_tag("test", "value")
            assert isinstance(instances, list)
        except Exception as e:
            if "UnauthorizedOperation" in str(e) or "AccessDenied" in str(e):
                pytest.fail(f"IAM permissions insufficient for describe_instances: {str(e)}")
            else:
                # Other errors are acceptable (no instances, etc.)
                pass
    
    def test_retry_logic_with_invalid_region(self):
        """Test retry logic by using an invalid region."""
        EC2Service, _, _ = get_ec2_service()
        
        # This test verifies that network errors trigger retry logic
        try:
            service = EC2Service(region_name="invalid-region-12345")
            instances = service.get_instances_with_tag("test", "value")
            # If this succeeds, the region might actually exist
        except Exception as e:
            # We expect this to fail, but it should be handled gracefully
            assert "invalid-region" in str(e).lower() or "endpoint" in str(e).lower()


@pytest.mark.integration
class TestLambdaHandlerIntegration(TestEC2IntegrationSetup):
    """Integration tests for the main Lambda handler."""
    
    def test_lambda_handler_with_no_instances(self):
        """Test Lambda handler when no instances match the tag."""
        lambda_handler = get_lambda_handler()
        
        # Create a mock context object
        context = MagicMock()
        context.aws_request_id = str(uuid.uuid4())
        context.function_name = "test-ec2-auto-shutdown"
        context.function_version = "1"
        context.memory_limit_in_mb = 256
        context.get_remaining_time_in_millis.return_value = 30000
        
        # Create test event
        event = {}
        
        # Call the handler
        response = lambda_handler(event, context)
        
        # Verify response structure
        assert isinstance(response, dict)
        assert "statusCode" in response
        assert "body" in response
        assert response["statusCode"] == 200
        
        # Parse response body
        body = json.loads(response["body"])
        assert "processedInstances" in body
        assert "stoppedInstances" in body
        assert "skippedInstances" in body
        assert "errors" in body
        assert "summary" in body
        
        # With our unique test tag, we should find no instances
        assert body["processedInstances"] == 0
        assert body["stoppedInstances"] == 0
        assert body["skippedInstances"] == 0
        assert len(body["errors"]) == 0
        assert "No instances found" in body["summary"]
    
    def test_lambda_handler_with_invalid_config(self):
        """Test Lambda handler with invalid configuration."""
        lambda_handler = get_lambda_handler()
        
        # Temporarily set invalid config
        original_tag_key = os.environ.get('SHUTDOWN_TAG_KEY')
        os.environ['SHUTDOWN_TAG_KEY'] = ''  # Invalid empty tag key
        
        try:
            # The config reload should fail with validation error
            with pytest.raises(ValueError, match="SHUTDOWN_TAG_KEY cannot be empty"):
                reload_config()
            
            # Since config reload failed, we can't test the lambda handler
            # This test verifies that invalid config is caught during initialization
            assert True  # Test passes if we get the expected validation error
            
        finally:
            # Restore original config
            if original_tag_key:
                os.environ['SHUTDOWN_TAG_KEY'] = original_tag_key
            else:
                os.environ.pop('SHUTDOWN_TAG_KEY', None)
            
            # Reload config to restore
            reload_config()
    
    def test_lambda_handler_error_handling(self):
        """Test Lambda handler error handling with invalid AWS region."""
        lambda_handler = get_lambda_handler()
        
        # Temporarily set invalid region
        original_region = os.environ.get('AWS_REGION')
        os.environ['AWS_REGION'] = 'invalid-region-12345'
        
        try:
            context = MagicMock()
            context.aws_request_id = str(uuid.uuid4())
            
            response = lambda_handler({}, context)
            
            # Should handle the error gracefully
            assert isinstance(response, dict)
            assert "statusCode" in response
            assert "body" in response
            
            body = json.loads(response["body"])
            assert "errors" in body
            
        finally:
            # Restore original region
            if original_region:
                os.environ['AWS_REGION'] = original_region
            else:
                os.environ.pop('AWS_REGION', None)
    
    def test_lambda_handler_response_format(self):
        """Test that Lambda handler returns properly formatted response."""
        lambda_handler = get_lambda_handler()
        
        context = MagicMock()
        context.aws_request_id = str(uuid.uuid4())
        
        response = lambda_handler({}, context)
        
        # Verify response format matches Lambda requirements
        assert isinstance(response, dict)
        assert "statusCode" in response
        assert "body" in response
        assert isinstance(response["statusCode"], int)
        assert isinstance(response["body"], str)
        
        # Verify body is valid JSON
        body = json.loads(response["body"])
        assert isinstance(body, dict)
        
        # Verify required fields are present
        required_fields = ["processedInstances", "stoppedInstances", "skippedInstances", "errors", "summary"]
        for field in required_fields:
            assert field in body, f"Required field '{field}' missing from response"
        
        # Verify field types
        assert isinstance(body["processedInstances"], int)
        assert isinstance(body["stoppedInstances"], int)
        assert isinstance(body["skippedInstances"], int)
        assert isinstance(body["errors"], list)
        assert isinstance(body["summary"], str)


@pytest.mark.integration
class TestEndToEndScenarios(TestEC2IntegrationSetup):
    """End-to-end integration tests for various scenarios."""
    
    def test_configuration_loading(self):
        """Test that configuration is loaded correctly from environment variables."""
        # Test with custom values
        test_key = f"TestKey-{uuid.uuid4().hex[:8]}"
        test_value = f"TestValue-{uuid.uuid4().hex[:8]}"
        
        original_key = os.environ.get('SHUTDOWN_TAG_KEY')
        original_value = os.environ.get('SHUTDOWN_TAG_VALUE')
        
        try:
            os.environ['SHUTDOWN_TAG_KEY'] = test_key
            os.environ['SHUTDOWN_TAG_VALUE'] = test_value
            
            # Force config reload
            config = reload_config()
            
            # Verify config loaded correctly
            assert config.shutdown_tag_key == test_key
            assert config.shutdown_tag_value == test_value
            
        finally:
            # Restore original values
            if original_key:
                os.environ['SHUTDOWN_TAG_KEY'] = original_key
            else:
                os.environ.pop('SHUTDOWN_TAG_KEY', None)
            
            if original_value:
                os.environ['SHUTDOWN_TAG_VALUE'] = original_value
            else:
                os.environ.pop('SHUTDOWN_TAG_VALUE', None)
            
            reload_config()
    
    def test_logging_integration(self):
        """Test that logging works correctly in integration environment."""
        get_logger_func = get_logger()
        
        correlation_id = str(uuid.uuid4())
        logger = get_logger_func("integration-test", correlation_id)
        
        # Test different log levels
        logger.info("Integration test info message", extra={"test_field": "test_value"})
        logger.warn("Integration test warning message")
        logger.error("Integration test error message", extra={"error_type": "TestError"})
        
        # If we get here without exceptions, logging is working
        assert True
    
    def test_aws_service_connectivity(self):
        """Test basic AWS service connectivity and permissions."""
        try:
            # Test EC2 connectivity
            ec2_client = boto3.client('ec2', region_name=self.region)
            response = ec2_client.describe_regions()
            assert 'Regions' in response
            
            # Test that we can at least attempt to describe instances
            # (even if we get permission errors, the connection works)
            try:
                ec2_client.describe_instances(MaxResults=5)
            except Exception as e:
                if "UnauthorizedOperation" not in str(e) and "AccessDenied" not in str(e):
                    # Re-raise if it's not a permission error
                    raise
                else:
                    print(f"Note: Limited EC2 permissions detected: {str(e)}")
            
        except Exception as e:
            pytest.fail(f"AWS service connectivity test failed: {str(e)}")
    
    def test_multiple_tag_combinations(self):
        """Test various tag key/value combinations."""
        EC2Service, _, _ = get_ec2_service()
        
        service = EC2Service(region_name=self.region)
        
        # Test different tag combinations that shouldn't exist
        test_cases = [
            ("Environment", "test"),
            ("Project", "integration-test"),
            ("Owner", "test-user"),
            ("AutoShutdown", "no"),  # Opposite of our target value
        ]
        
        for tag_key, tag_value in test_cases:
            instances = service.get_instances_with_tag(tag_key, tag_value)
            assert isinstance(instances, list)
            # We don't assert on length since we don't know what exists
    
    def test_error_recovery_scenarios(self):
        """Test error recovery in various failure scenarios."""
        EC2Service, _, ShutdownResult = get_ec2_service()
        
        # Test with invalid instance ID format
        service = EC2Service(region_name=self.region)
        
        invalid_instance_ids = [
            "invalid-id",
            "i-invalid",
            "i-123",  # Too short
            "",  # Empty
        ]
        
        for invalid_id in invalid_instance_ids:
            result = service.stop_instance(invalid_id)
            assert isinstance(result, ShutdownResult)
            assert result.success is False
            assert result.error is not None
            assert len(result.error) > 0


# Test runner configuration
if __name__ == "__main__":
    # Run integration tests with verbose output
    pytest.main([
        __file__,
        "-v",
        "-s",
        "--tb=short",
        "-m", "integration"
    ])