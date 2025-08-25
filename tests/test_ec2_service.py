"""
Unit tests for EC2 service module.
"""
import pytest
import boto3
from unittest.mock import Mock, patch, MagicMock, ANY
from botocore.exceptions import ClientError, BotoCoreError
from botocore.config import Config

from src.ec2_service import EC2Service, InstanceInfo, ShutdownResult


class TestEC2Service:
    """Test cases for EC2Service class."""
    
    def test_init_with_region(self):
        """Test EC2Service initialization with specific region."""
        with patch('boto3.client') as mock_client:
            service = EC2Service(region_name='us-west-2')
            
            mock_client.assert_called_once_with(
                'ec2',
                region_name='us-west-2',
                config=ANY
            )
            assert service.region_name == 'us-west-2'
    
    def test_init_without_region(self):
        """Test EC2Service initialization without region (uses default)."""
        with patch('boto3.client') as mock_client, \
             patch('boto3.Session') as mock_session:
            
            mock_session.return_value.region_name = 'us-east-1'
            service = EC2Service()
            
            mock_client.assert_called_once_with(
                'ec2',
                region_name=None,
                config=ANY
            )
            assert service.region_name == 'us-east-1'
    
    def test_retry_config_setup(self):
        """Test that retry configuration is properly set up."""
        with patch('boto3.client') as mock_client:
            EC2Service(region_name='us-west-2')
            
            # Verify the config passed to boto3.client has retry settings
            call_args = mock_client.call_args
            config = call_args[1]['config']
            assert config.retries['max_attempts'] == 5
            assert config.retries['mode'] == 'adaptive'
    
    def test_retry_with_linear_backoff_success(self):
        """Test linear backoff retry succeeds on first attempt."""
        service = EC2Service()
        mock_func = Mock(return_value='success')
        
        result = service._retry_with_linear_backoff(mock_func, 'arg1', kwarg1='value1')
        
        assert result == 'success'
        mock_func.assert_called_once_with('arg1', kwarg1='value1')
    
    def test_retry_with_linear_backoff_network_error_retry_success(self):
        """Test linear backoff retry succeeds after network error."""
        service = EC2Service()
        mock_func = Mock(side_effect=[BotoCoreError(), 'success'])
        
        with patch('time.sleep') as mock_sleep:
            result = service._retry_with_linear_backoff(mock_func, max_retries=3, delay=1.0)
        
        assert result == 'success'
        assert mock_func.call_count == 2
        mock_sleep.assert_called_once_with(1.0)
    
    def test_retry_with_linear_backoff_connection_error_retry_success(self):
        """Test linear backoff retry succeeds after connection error."""
        service = EC2Service()
        # Use a standard Python ConnectionError instead of botocore's
        mock_func = Mock(side_effect=[ConnectionError("Network error"), 'success'])
        
        with patch('time.sleep') as mock_sleep:
            result = service._retry_with_linear_backoff(mock_func, max_retries=3, delay=2.0)
        
        assert result == 'success'
        assert mock_func.call_count == 2
        mock_sleep.assert_called_once_with(2.0)
    
    def test_retry_with_linear_backoff_max_retries_exceeded(self):
        """Test linear backoff retry fails after max retries."""
        service = EC2Service()
        error = BotoCoreError()
        mock_func = Mock(side_effect=error)
        
        with patch('time.sleep') as mock_sleep:
            with pytest.raises(BotoCoreError):
                service._retry_with_linear_backoff(mock_func, max_retries=2, delay=1.0)
        
        assert mock_func.call_count == 3  # Initial + 2 retries
        assert mock_sleep.call_count == 2
    
    def test_retry_with_linear_backoff_client_error_no_retry(self):
        """Test that ClientError is not retried."""
        service = EC2Service()
        error = ClientError(
            error_response={'Error': {'Code': 'UnauthorizedOperation'}},
            operation_name='DescribeInstances'
        )
        mock_func = Mock(side_effect=error)
        
        with pytest.raises(ClientError):
            service._retry_with_linear_backoff(mock_func, max_retries=3)
        
        mock_func.assert_called_once()  # No retries for ClientError
    
    def test_get_instances_with_tag_success(self):
        """Test successful instance discovery with tags."""
        service = EC2Service()
        
        # Mock the paginator and response
        mock_paginator = Mock()
        mock_page_iterator = Mock()
        mock_paginator.paginate.return_value = mock_page_iterator
        
        # Mock response data
        mock_response = [
            {
                'Reservations': [
                    {
                        'Instances': [
                            {
                                'InstanceId': 'i-1234567890abcdef0',
                                'State': {'Name': 'running'},
                                'Tags': [
                                    {'Key': 'AutoShutdown', 'Value': 'yes'},
                                    {'Key': 'Environment', 'Value': 'dev'}
                                ]
                            },
                            {
                                'InstanceId': 'i-0987654321fedcba0',
                                'State': {'Name': 'stopped'},
                                'Tags': [
                                    {'Key': 'AutoShutdown', 'Value': 'yes'},
                                    {'Key': 'Environment', 'Value': 'test'}
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
        
        with patch.object(service.ec2_client, 'get_paginator', return_value=mock_paginator), \
             patch.object(service, '_retry_with_linear_backoff') as mock_retry:
            
            # Mock the retry function to return our test data
            mock_retry.return_value = [
                InstanceInfo(
                    instance_id='i-1234567890abcdef0',
                    state='running',
                    tags={'AutoShutdown': 'yes', 'Environment': 'dev'}
                ),
                InstanceInfo(
                    instance_id='i-0987654321fedcba0',
                    state='stopped',
                    tags={'AutoShutdown': 'yes', 'Environment': 'test'}
                )
            ]
            
            result = service.get_instances_with_tag('AutoShutdown', 'yes')
            
            # Verify results
            assert len(result) == 2
            assert result[0].instance_id == 'i-1234567890abcdef0'
            assert result[0].state == 'running'
            assert result[0].tags['AutoShutdown'] == 'yes'
            assert result[1].instance_id == 'i-0987654321fedcba0'
            assert result[1].state == 'stopped'
            
            # Verify paginator was called with correct filters
            mock_paginator.paginate.assert_called_once_with(
                Filters=[{'Name': 'tag:AutoShutdown', 'Values': ['yes']}]
            )
    
    def test_get_instances_with_tag_no_instances(self):
        """Test instance discovery when no instances match the tag."""
        service = EC2Service()
        
        mock_paginator = Mock()
        mock_page_iterator = Mock()
        mock_paginator.paginate.return_value = mock_page_iterator
        
        with patch.object(service.ec2_client, 'get_paginator', return_value=mock_paginator), \
             patch.object(service, '_retry_with_linear_backoff', return_value=[]):
            
            result = service.get_instances_with_tag('AutoShutdown', 'yes')
            
            assert result == []
            mock_paginator.paginate.assert_called_once_with(
                Filters=[{'Name': 'tag:AutoShutdown', 'Values': ['yes']}]
            )
    
    def test_get_instances_with_tag_client_error(self):
        """Test instance discovery handles ClientError."""
        service = EC2Service()
        
        mock_paginator = Mock()
        mock_page_iterator = Mock()
        mock_paginator.paginate.return_value = mock_page_iterator
        
        client_error = ClientError(
            error_response={'Error': {'Code': 'UnauthorizedOperation', 'Message': 'Access denied'}},
            operation_name='DescribeInstances'
        )
        
        with patch.object(service.ec2_client, 'get_paginator', return_value=mock_paginator), \
             patch.object(service, '_retry_with_linear_backoff', side_effect=client_error):
            
            with pytest.raises(ClientError) as exc_info:
                service.get_instances_with_tag('AutoShutdown', 'yes')
            
            assert exc_info.value.response['Error']['Code'] == 'UnauthorizedOperation'
    
    def test_get_instances_with_tag_network_error_retry(self):
        """Test instance discovery retries on network errors."""
        service = EC2Service()
        
        mock_paginator = Mock()
        mock_page_iterator = Mock()
        mock_paginator.paginate.return_value = mock_page_iterator
        
        with patch.object(service.ec2_client, 'get_paginator', return_value=mock_paginator), \
             patch.object(service, '_retry_with_linear_backoff', side_effect=BotoCoreError()) as mock_retry:
            
            with pytest.raises(BotoCoreError):
                service.get_instances_with_tag('AutoShutdown', 'yes')
            
            # Verify retry was attempted
            mock_retry.assert_called_once()
    
    def test_stop_instance_success(self):
        """Test successful instance shutdown."""
        service = EC2Service()
        
        # Mock describe_instances response
        describe_response = {
            'Reservations': [
                {
                    'Instances': [
                        {
                            'InstanceId': 'i-1234567890abcdef0',
                            'State': {'Name': 'running'}
                        }
                    ]
                }
            ]
        }
        
        with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
            mock_retry.side_effect = [describe_response, None]  # describe then stop
            
            result = service.stop_instance('i-1234567890abcdef0')
            
            assert result.success is True
            assert result.instance_id == 'i-1234567890abcdef0'
            assert result.previous_state == 'running'
            assert result.error is None
            
            # Verify both describe and stop were called
            assert mock_retry.call_count == 2
            mock_retry.assert_any_call(
                service.ec2_client.describe_instances,
                InstanceIds=['i-1234567890abcdef0']
            )
            mock_retry.assert_any_call(
                service.ec2_client.stop_instances,
                InstanceIds=['i-1234567890abcdef0']
            )
    
    def test_stop_instance_already_stopped(self):
        """Test stopping an instance that's already stopped."""
        service = EC2Service()
        
        # Mock describe_instances response for stopped instance
        describe_response = {
            'Reservations': [
                {
                    'Instances': [
                        {
                            'InstanceId': 'i-1234567890abcdef0',
                            'State': {'Name': 'stopped'}
                        }
                    ]
                }
            ]
        }
        
        with patch.object(service, '_retry_with_linear_backoff', return_value=describe_response):
            result = service.stop_instance('i-1234567890abcdef0')
            
            assert result.success is True
            assert result.instance_id == 'i-1234567890abcdef0'
            assert result.previous_state == 'stopped'
            assert result.error is None
    
    def test_stop_instance_already_stopping(self):
        """Test stopping an instance that's already stopping."""
        service = EC2Service()
        
        # Mock describe_instances response for stopping instance
        describe_response = {
            'Reservations': [
                {
                    'Instances': [
                        {
                            'InstanceId': 'i-1234567890abcdef0',
                            'State': {'Name': 'stopping'}
                        }
                    ]
                }
            ]
        }
        
        with patch.object(service, '_retry_with_linear_backoff', return_value=describe_response):
            result = service.stop_instance('i-1234567890abcdef0')
            
            assert result.success is True
            assert result.instance_id == 'i-1234567890abcdef0'
            assert result.previous_state == 'stopping'
            assert result.error is None
    
    def test_stop_instance_not_found(self):
        """Test stopping a non-existent instance."""
        service = EC2Service()
        
        # Mock describe_instances response for non-existent instance
        describe_response = {'Reservations': []}
        
        with patch.object(service, '_retry_with_linear_backoff', return_value=describe_response):
            result = service.stop_instance('i-nonexistent')
            
            assert result.success is False
            assert result.instance_id == 'i-nonexistent'
            assert 'not found' in result.error
    
    def test_stop_instance_permission_error(self):
        """Test stopping instance with permission error."""
        service = EC2Service()
        
        # Mock describe_instances to succeed, stop_instances to fail with permission error
        describe_response = {
            'Reservations': [
                {
                    'Instances': [
                        {
                            'InstanceId': 'i-1234567890abcdef0',
                            'State': {'Name': 'running'}
                        }
                    ]
                }
            ]
        }
        
        permission_error = ClientError(
            error_response={'Error': {'Code': 'UnauthorizedOperation', 'Message': 'Access denied'}},
            operation_name='StopInstances'
        )
        
        with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
            mock_retry.side_effect = [describe_response, permission_error]
            
            result = service.stop_instance('i-1234567890abcdef0')
            
            assert result.success is False
            assert result.instance_id == 'i-1234567890abcdef0'
            assert 'UnauthorizedOperation' in result.error
    
    def test_stop_instance_client_error(self):
        """Test stopping instance with other client error."""
        service = EC2Service()
        
        # Mock describe_instances to succeed, stop_instances to fail with other error
        describe_response = {
            'Reservations': [
                {
                    'Instances': [
                        {
                            'InstanceId': 'i-1234567890abcdef0',
                            'State': {'Name': 'running'}
                        }
                    ]
                }
            ]
        }
        
        client_error = ClientError(
            error_response={'Error': {'Code': 'InvalidInstanceID.NotFound', 'Message': 'Instance not found'}},
            operation_name='StopInstances'
        )
        
        with patch.object(service, '_retry_with_linear_backoff') as mock_retry:
            mock_retry.side_effect = [describe_response, client_error]
            
            result = service.stop_instance('i-1234567890abcdef0')
            
            assert result.success is False
            assert result.instance_id == 'i-1234567890abcdef0'
            assert 'InvalidInstanceID.NotFound' in result.error
    
    def test_stop_instance_network_error(self):
        """Test stopping instance with network error."""
        service = EC2Service()
        
        network_error = BotoCoreError()
        
        with patch.object(service, '_retry_with_linear_backoff', side_effect=network_error):
            result = service.stop_instance('i-1234567890abcdef0')
            
            assert result.success is False
            assert result.instance_id == 'i-1234567890abcdef0'
            assert 'Unexpected error' in result.error