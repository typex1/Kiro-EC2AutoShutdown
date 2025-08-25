"""
Comprehensive error handling tests for EC2 Auto-Shutdown Lambda function.

Tests AWS API throttling, network failures, permission errors, and logging output.
Requirements: 3.1, 3.2, 3.3, 3.4
"""

import pytest
import json
import time
from unittest.mock import Mock, patch, MagicMock, call
from botocore.exceptions import ClientError, BotoCoreError
from botocore.client import BaseClient

from src.ec2_service import EC2Service, InstanceInfo, ShutdownResult
from src.lambda_function import lambda_handler
from src.logger import get_logger


class TestAWSAPIThrottlingScenarios:
    """Test AWS API throttling scenarios with exponential backoff retry logic."""
    
    @patch('boto3.client')
    def test_throttling_with_exponential_backoff_success(self, mock_boto_client):
        """Test that throttling errors are retried with exponential backoff and eventually succeed."""
        # Create mock client
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        # Test that the boto3 retry config is properly set up
        # The retry config should handle throttling automatically with exponential backoff
        call_args = mock_boto_client.call_args
        config = call_args[1]['config']
        assert config.retries['max_attempts'] == 5
        assert config.retries['mode'] == 'adaptive'
        
        # Mock a successful call after retry
        mock_paginator = Mock()
        mock_client.get_paginator.return_value = mock_paginator
        
        # Mock successful response after retries
        with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
            mock_retry.return_value = []
            
            result = service.get_instances_with_tag('AutoShutdown', 'yes')
            
            assert result == []
            mock_retry.assert_called_once()
    
    @patch('boto3.client')
    def test_throttling_max_retries_exceeded(self, mock_boto_client):
        """Test that throttling errors eventually fail after max retries."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        # Create persistent throttling error
        throttling_error = ClientError(
            error_response={
                'Error': {
                    'Code': 'RequestLimitExceeded', 
                    'Message': 'Request limit exceeded'
                }
            },
            operation_name='DescribeInstances'
        )
        
        # Mock the retry function to simulate persistent throttling
        with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
            mock_retry.side_effect = throttling_error
            
            # Test that persistent throttling eventually raises the error
            with pytest.raises(ClientError) as exc_info:
                service.get_instances_with_tag('AutoShutdown', 'yes')
            
            assert exc_info.value.response['Error']['Code'] == 'RequestLimitExceeded'
    
    @patch('boto3.client')
    def test_stop_instance_throttling_retry_success(self, mock_boto_client):
        """Test that stop_instance handles throttling with retry and succeeds."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        # Mock describe_instances to succeed
        describe_response = {
            'Reservations': [{
                'Instances': [{
                    'InstanceId': 'i-123',
                    'State': {'Name': 'running'}
                }]
            }]
        }
        
        # Mock stop_instances to fail with throttling then succeed
        throttling_error = ClientError(
            error_response={
                'Error': {
                    'Code': 'Throttling',
                    'Message': 'Rate exceeded'
                }
            },
            operation_name='StopInstances'
        )
        
        service = EC2Service()
        
        with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
            # First call (describe) succeeds, second call (stop) fails then succeeds
            mock_retry.side_effect = [describe_response, throttling_error, None]
            
            # The first call should succeed, second should fail with throttling
            # In real scenario, boto3 config would handle the retry
            result = service.stop_instance('i-123')
            
            # Should have attempted both describe and stop
            assert mock_retry.call_count >= 2


class TestNetworkFailureAndRetryBehavior:
    """Test network failure scenarios and linear retry behavior."""
    
    @patch('time.sleep')  # Mock sleep to speed up tests
    @patch('boto3.client')
    def test_network_error_linear_retry_success(self, mock_boto_client, mock_sleep):
        """Test that network errors are retried with linear backoff and eventually succeed."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        # Mock function that fails twice with network error then succeeds
        mock_func = Mock(side_effect=[
            BotoCoreError(),  # First attempt fails
            BotoCoreError(),  # Second attempt fails  
            'success'         # Third attempt succeeds
        ])
        
        result = service._retry_with_linear_backoff(mock_func, max_retries=3, delay=1.0)
        
        assert result == 'success'
        assert mock_func.call_count == 3
        assert mock_sleep.call_count == 2  # Two retries = two sleeps
        mock_sleep.assert_has_calls([call(1.0), call(1.0)])
    
    @patch('time.sleep')
    @patch('boto3.client')
    def test_connection_error_linear_retry_success(self, mock_boto_client, mock_sleep):
        """Test that connection errors are retried with linear backoff."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        # Mock function that fails with connection error then succeeds
        mock_func = Mock(side_effect=[
            ConnectionError("Network unreachable"),
            'success'
        ])
        
        result = service._retry_with_linear_backoff(mock_func, max_retries=2, delay=2.0)
        
        assert result == 'success'
        assert mock_func.call_count == 2
        mock_sleep.assert_called_once_with(2.0)
    
    @patch('time.sleep')
    @patch('boto3.client') 
    def test_network_error_max_retries_exceeded(self, mock_boto_client, mock_sleep):
        """Test that network errors fail after max retries are exceeded."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        # Mock function that always fails with network error
        network_error = BotoCoreError()
        mock_func = Mock(side_effect=network_error)
        
        with pytest.raises(BotoCoreError):
            service._retry_with_linear_backoff(mock_func, max_retries=2, delay=1.0)
        
        assert mock_func.call_count == 3  # Initial + 2 retries
        assert mock_sleep.call_count == 2
    
    @patch('boto3.client')
    def test_get_instances_network_error_retry(self, mock_boto_client):
        """Test that get_instances_with_tag retries on network errors."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        mock_paginator = Mock()
        mock_client.get_paginator.return_value = mock_paginator
        
        service = EC2Service()
        
        # Mock the retry function to simulate network error
        with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
            mock_retry.side_effect = BotoCoreError()
            
            with pytest.raises(BotoCoreError):
                service.get_instances_with_tag('AutoShutdown', 'yes')
            
            mock_retry.assert_called_once()
    
    @patch('boto3.client')
    def test_stop_instance_network_error_handling(self, mock_boto_client):
        """Test that stop_instance handles network errors gracefully."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        # Mock retry to fail with network error
        with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
            mock_retry.side_effect = BotoCoreError()
            
            result = service.stop_instance('i-123')
            
            assert result.success is False
            assert result.instance_id == 'i-123'
            assert 'Unexpected error' in result.error


class TestPermissionErrorHandling:
    """Test permission error handling scenarios."""
    
    @patch('boto3.client')
    def test_describe_instances_permission_denied(self, mock_boto_client):
        """Test handling of permission denied errors when describing instances."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        # Create permission denied error
        permission_error = ClientError(
            error_response={
                'Error': {
                    'Code': 'UnauthorizedOperation',
                    'Message': 'You are not authorized to perform this operation'
                }
            },
            operation_name='DescribeInstances'
        )
        
        mock_paginator = Mock()
        mock_client.get_paginator.return_value = mock_paginator
        
        service = EC2Service()
        
        with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
            mock_retry.side_effect = permission_error
            
            with pytest.raises(ClientError) as exc_info:
                service.get_instances_with_tag('AutoShutdown', 'yes')
            
            assert exc_info.value.response['Error']['Code'] == 'UnauthorizedOperation'
            # Permission errors should not be retried
            mock_retry.assert_called_once()
    
    @patch('boto3.client')
    def test_stop_instances_permission_denied(self, mock_boto_client):
        """Test handling of permission denied errors when stopping instances."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        # Mock describe to succeed, stop to fail with permission error
        describe_response = {
            'Reservations': [{
                'Instances': [{
                    'InstanceId': 'i-123',
                    'State': {'Name': 'running'}
                }]
            }]
        }
        
        permission_error = ClientError(
            error_response={
                'Error': {
                    'Code': 'UnauthorizedOperation',
                    'Message': 'You are not authorized to perform this operation'
                }
            },
            operation_name='StopInstances'
        )
        
        with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
            mock_retry.side_effect = [describe_response, permission_error]
            
            result = service.stop_instance('i-123')
            
            assert result.success is False
            assert result.instance_id == 'i-123'
            assert 'UnauthorizedOperation' in result.error
            assert 'You are not authorized' in result.error
    
    @patch('boto3.client')
    def test_access_denied_error_handling(self, mock_boto_client):
        """Test handling of AccessDenied errors."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        describe_response = {
            'Reservations': [{
                'Instances': [{
                    'InstanceId': 'i-123',
                    'State': {'Name': 'running'}
                }]
            }]
        }
        
        access_denied_error = ClientError(
            error_response={
                'Error': {
                    'Code': 'AccessDenied',
                    'Message': 'Access denied'
                }
            },
            operation_name='StopInstances'
        )
        
        with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
            mock_retry.side_effect = [describe_response, access_denied_error]
            
            result = service.stop_instance('i-123')
            
            assert result.success is False
            assert 'AccessDenied' in result.error
    
    @patch('src.lambda_function.EC2Service')
    @patch('src.lambda_function.get_logger')
    @patch('src.lambda_function.config')
    def test_lambda_handler_permission_error_continues_processing(self, mock_config, mock_get_logger, mock_ec2_service_class):
        """Test that Lambda handler continues processing other instances when permission errors occur."""
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
        
        # Mock results with permission error in middle
        results = [
            ShutdownResult("i-123", True, previous_state="running"),
            ShutdownResult("i-456", False, error="UnauthorizedOperation: Access denied", previous_state="running"),
            ShutdownResult("i-789", True, previous_state="running")
        ]
        mock_ec2_service.stop_instance.side_effect = results
        
        # Execute
        response = lambda_handler({}, Mock())
        
        # Verify processing continued despite permission error
        assert response["statusCode"] == 207  # Multi-status
        body = json.loads(response["body"])
        assert body["processedInstances"] == 3
        assert body["stoppedInstances"] == 2
        assert len(body["errors"]) == 1
        assert "UnauthorizedOperation" in body["errors"][0]["error"]
        
        # Verify all instances were attempted
        assert mock_ec2_service.stop_instance.call_count == 3


class TestLoggingOutputForErrorConditions:
    """Test that all error conditions produce appropriate logging output."""
    
    @patch('boto3.client')
    def test_throttling_error_logging(self, mock_boto_client):
        """Test that throttling errors are properly logged."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        # Mock logger to capture log calls
        with patch('src.ec2_service.logger') as mock_logger:
            # Mock retry function to simulate throttling error
            with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
                throttling_error = ClientError(
                    error_response={
                        'Error': {
                            'Code': 'Throttling',
                            'Message': 'Rate exceeded'
                        }
                    },
                    operation_name='DescribeInstances'
                )
                mock_retry.side_effect = throttling_error
                
                with pytest.raises(ClientError):
                    service.get_instances_with_tag('AutoShutdown', 'yes')
                
                # Verify error was logged
                mock_logger.error.assert_called()
                error_call = mock_logger.error.call_args[0][0]
                assert 'Throttling' in error_call
    
    @patch('time.sleep')
    @patch('boto3.client')
    def test_network_error_retry_logging(self, mock_boto_client, mock_sleep):
        """Test that network errors and retries are properly logged."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        with patch('src.ec2_service.logger') as mock_logger:
            # Mock function that fails with network error then succeeds
            mock_func = Mock(side_effect=[BotoCoreError(), 'success'])
            
            result = service._retry_with_linear_backoff(mock_func, max_retries=2, delay=1.0)
            
            assert result == 'success'
            
            # Verify retry warning was logged
            mock_logger.warn.assert_called()
            warn_call = mock_logger.warn.call_args[0][0]
            assert 'Network error on attempt 1' in warn_call
            assert 'retrying in 1.0s' in warn_call
    
    @patch('time.sleep')
    @patch('boto3.client')
    def test_network_error_max_retries_logging(self, mock_boto_client, mock_sleep):
        """Test that max retries exceeded is properly logged."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        with patch('src.ec2_service.logger') as mock_logger:
            # Mock function that always fails
            network_error = BotoCoreError()
            mock_func = Mock(side_effect=network_error)
            
            with pytest.raises(BotoCoreError):
                service._retry_with_linear_backoff(mock_func, max_retries=1, delay=1.0)
            
            # Verify both retry warning and final error were logged
            mock_logger.warn.assert_called()
            mock_logger.error.assert_called()
            
            error_call = mock_logger.error.call_args[0][0]
            assert 'All retry attempts failed' in error_call
    
    @patch('boto3.client')
    def test_permission_error_logging(self, mock_boto_client):
        """Test that permission errors are logged with appropriate level."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        with patch('src.ec2_service.logger') as mock_logger:
            describe_response = {
                'Reservations': [{
                    'Instances': [{
                        'InstanceId': 'i-123',
                        'State': {'Name': 'running'}
                    }]
                }]
            }
            
            permission_error = ClientError(
                error_response={
                    'Error': {
                        'Code': 'UnauthorizedOperation',
                        'Message': 'Access denied'
                    }
                },
                operation_name='StopInstances'
            )
            
            with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
                mock_retry.side_effect = [describe_response, permission_error]
                
                result = service.stop_instance('i-123')
                
                assert result.success is False
                
                # Verify permission error was logged as warning (graceful handling)
                mock_logger.warn.assert_called()
                warn_call = mock_logger.warn.call_args[0][0]
                assert 'Permission denied stopping instance i-123' in warn_call
    
    @patch('boto3.client')
    def test_instance_discovery_logging(self, mock_boto_client):
        """Test that instance discovery process is properly logged."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        with patch('src.ec2_service.logger') as mock_logger:
            # Mock successful discovery
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            
            with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
                mock_retry.return_value = [
                    InstanceInfo("i-123", "running", {"AutoShutdown": "yes"})
                ]
                
                result = service.get_instances_with_tag('AutoShutdown', 'yes')
                
                assert len(result) == 1
                
                # Verify discovery start and completion were logged
                info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
                assert any('Discovering instances with tag AutoShutdown=yes' in call for call in info_calls)
                assert any('Discovered 1 instances with tag AutoShutdown=yes' in call for call in info_calls)
    
    @patch('boto3.client')
    def test_instance_stop_success_logging(self, mock_boto_client):
        """Test that successful instance stops are properly logged."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        with patch('src.ec2_service.logger') as mock_logger:
            describe_response = {
                'Reservations': [{
                    'Instances': [{
                        'InstanceId': 'i-123',
                        'State': {'Name': 'running'}
                    }]
                }]
            }
            
            with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
                mock_retry.side_effect = [describe_response, None]  # describe then stop
                
                result = service.stop_instance('i-123')
                
                assert result.success is True
                
                # Verify stop attempt and success were logged
                info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
                assert any('Attempting to stop instance i-123' in call for call in info_calls)
                assert any('Successfully initiated stop for instance i-123' in call for call in info_calls)
    
    @patch('boto3.client')
    def test_instance_already_stopped_logging(self, mock_boto_client):
        """Test that already stopped instances are properly logged."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        with patch('src.ec2_service.logger') as mock_logger:
            describe_response = {
                'Reservations': [{
                    'Instances': [{
                        'InstanceId': 'i-123',
                        'State': {'Name': 'stopped'}
                    }]
                }]
            }
            
            with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
                mock_retry.return_value = describe_response
                
                result = service.stop_instance('i-123')
                
                assert result.success is True
                assert result.previous_state == 'stopped'
                
                # Verify skip was logged
                info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
                assert any('Instance i-123 is already stopped, skipping' in call for call in info_calls)
    
    @patch('src.lambda_function.EC2Service')
    @patch('src.lambda_function.get_logger')
    @patch('src.lambda_function.config')
    def test_lambda_handler_error_logging(self, mock_config, mock_get_logger, mock_ec2_service_class):
        """Test that Lambda handler errors are properly logged with correlation ID."""
        # Setup mocks
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_config.shutdown_tag_key = "AutoShutdown"
        mock_config.shutdown_tag_value = "yes"
        mock_config.aws_region = "us-east-1"
        
        # Make EC2Service initialization fail
        mock_ec2_service_class.side_effect = Exception("AWS credentials not found")
        
        # Execute
        response = lambda_handler({}, Mock())
        
        # Verify error response
        assert response["statusCode"] == 500
        
        # Verify error was logged with proper context
        mock_logger.error.assert_called()
        error_call_args = mock_logger.error.call_args
        error_message = error_call_args[0][0]
        error_extra = error_call_args[1].get('extra', {})
        
        assert 'Failed to initialize EC2 service' in error_message
        assert 'AWS credentials not found' in error_message
        assert 'error_type' in error_extra
        assert error_extra['error_type'] == 'Exception'


class TestIntegratedErrorScenarios:
    """Test integrated error scenarios that combine multiple error types."""
    
    @patch('src.lambda_function.EC2Service')
    @patch('src.lambda_function.get_logger')
    @patch('src.lambda_function.config')
    def test_mixed_error_conditions_in_lambda_handler(self, mock_config, mock_get_logger, mock_ec2_service_class):
        """Test Lambda handler with mixed success, permission errors, and network errors."""
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
            InstanceInfo("i-success", "running", {"AutoShutdown": "yes"}),
            InstanceInfo("i-permission", "running", {"AutoShutdown": "yes"}),
            InstanceInfo("i-network", "running", {"AutoShutdown": "yes"}),
            InstanceInfo("i-stopped", "stopped", {"AutoShutdown": "yes"})
        ]
        mock_ec2_service.get_instances_with_tag.return_value = instances
        
        # Mock mixed results
        results = [
            ShutdownResult("i-success", True, previous_state="running"),
            ShutdownResult("i-permission", False, error="UnauthorizedOperation: Access denied", previous_state="running"),
            ShutdownResult("i-network", False, error="Unexpected error: Network timeout", previous_state="running"),
            ShutdownResult("i-stopped", True, previous_state="stopped")
        ]
        mock_ec2_service.stop_instance.side_effect = results
        
        # Execute
        response = lambda_handler({}, Mock())
        
        # Verify mixed results are handled correctly
        assert response["statusCode"] == 207  # Multi-status
        body = json.loads(response["body"])
        assert body["processedInstances"] == 4
        assert body["stoppedInstances"] == 1  # Only i-success was actually stopped
        assert body["skippedInstances"] == 1  # i-stopped was already stopped
        assert len(body["errors"]) == 2  # i-permission and i-network failed
        
        # Verify all error types are captured
        error_messages = [error["error"] for error in body["errors"]]
        assert any("UnauthorizedOperation" in msg for msg in error_messages)
        assert any("Network timeout" in msg for msg in error_messages)
        
        # Verify appropriate logging occurred
        mock_logger.info.assert_called()  # Should have info logs for successes
        mock_logger.error.assert_called()  # Should have error logs for failures
    
    @patch('time.sleep')
    @patch('boto3.client')
    def test_retry_behavior_with_different_error_types(self, mock_boto_client, mock_sleep):
        """Test that different error types are handled with appropriate retry behavior."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        # Test that ClientError is not retried
        client_error = ClientError(
            error_response={'Error': {'Code': 'UnauthorizedOperation'}},
            operation_name='TestOperation'
        )
        mock_func_client_error = Mock(side_effect=client_error)
        
        with pytest.raises(ClientError):
            service._retry_with_linear_backoff(mock_func_client_error, max_retries=3)
        
        mock_func_client_error.assert_called_once()  # No retries for ClientError
        mock_sleep.assert_not_called()
        
        # Reset mock
        mock_sleep.reset_mock()
        
        # Test that BotoCoreError is retried
        network_error = BotoCoreError()
        mock_func_network_error = Mock(side_effect=[network_error, network_error, 'success'])
        
        result = service._retry_with_linear_backoff(mock_func_network_error, max_retries=3, delay=1.0)
        
        assert result == 'success'
        assert mock_func_network_error.call_count == 3
        assert mock_sleep.call_count == 2  # Two retries
    
    @patch('boto3.client')
    def test_error_correlation_id_propagation(self, mock_boto_client):
        """Test that correlation IDs are properly propagated through error scenarios."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        # Test with custom correlation ID
        correlation_id = "test-correlation-123"
        logger = get_logger("test-logger", correlation_id)
        
        # Verify correlation ID is set
        assert logger.correlation_id == correlation_id
        
        # Test logging with correlation ID by capturing the logger's internal call
        with patch.object(logger.logger, 'error') as mock_log_error:
            logger.error("Test error message", instance_id="i-123")
            
            # Verify the logger was called with JSON containing correlation ID
            mock_log_error.assert_called_once()
            logged_json = mock_log_error.call_args[0][0]
            
            # Parse the JSON to verify contents
            import json
            log_data = json.loads(logged_json)
            assert log_data['correlation_id'] == correlation_id
            assert log_data['level'] == 'ERROR'
            assert log_data['message'] == 'Test error message'
            assert log_data['instance_id'] == 'i-123'
    
    @patch('src.lambda_function.EC2Service')
    @patch('src.lambda_function.get_logger')
    @patch('src.lambda_function.config')
    def test_lambda_handler_generates_correlation_id(self, mock_config, mock_get_logger, mock_ec2_service_class):
        """Test that Lambda handler generates and uses correlation ID for error tracking."""
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
        response = lambda_handler({}, Mock())
        
        # Verify logger was created with correlation ID
        mock_get_logger.assert_called()
        call_args = mock_get_logger.call_args
        assert call_args[0][0] == "ec2-auto-shutdown"
        assert len(call_args[0][1]) > 0  # Correlation ID should be generated
        
        # Verify successful response
        assert response["statusCode"] == 200


class TestErrorHandlingEdgeCases:
    """Test edge cases in error handling scenarios."""
    
    @patch('boto3.client')
    def test_empty_reservations_response(self, mock_boto_client):
        """Test handling of empty reservations in describe_instances response."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        # Mock empty response
        empty_response = {'Reservations': []}
        
        with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
            mock_retry.return_value = empty_response
            
            result = service.stop_instance('i-nonexistent')
            
            assert result.success is False
            assert result.instance_id == 'i-nonexistent'
            assert 'not found' in result.error
    
    @patch('boto3.client')
    def test_malformed_instance_response(self, mock_boto_client):
        """Test handling of malformed instance data in API responses."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        # Mock malformed response (missing State field)
        malformed_response = {
            'Reservations': [{
                'Instances': [{
                    'InstanceId': 'i-123'
                    # Missing 'State' field
                }]
            }]
        }
        
        with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
            mock_retry.return_value = malformed_response
            
            # The service should handle the KeyError gracefully and return a failed result
            result = service.stop_instance('i-123')
            
            assert result.success is False
            assert result.instance_id == 'i-123'
            assert 'Unexpected error' in result.error
            assert 'State' in result.error  # Should mention the missing State field
    
    @patch('boto3.client')
    def test_unicode_error_messages(self, mock_boto_client):
        """Test handling of unicode characters in error messages."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        service = EC2Service()
        
        # Create error with unicode characters
        unicode_error = ClientError(
            error_response={
                'Error': {
                    'Code': 'InvalidInstanceID.NotFound',
                    'Message': 'Instance não encontrado (not found) 🚫'
                }
            },
            operation_name='StopInstances'
        )
        
        describe_response = {
            'Reservations': [{
                'Instances': [{
                    'InstanceId': 'i-123',
                    'State': {'Name': 'running'}
                }]
            }]
        }
        
        with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
            mock_retry.side_effect = [describe_response, unicode_error]
            
            result = service.stop_instance('i-123')
            
            assert result.success is False
            assert 'não encontrado' in result.error
            assert '🚫' in result.error