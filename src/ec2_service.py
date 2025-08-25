"""
EC2 service module for managing EC2 instances with retry logic.
"""
import boto3
import time
from typing import List, Dict, Any, Optional
from botocore.exceptions import ClientError, BotoCoreError
from botocore.config import Config
from dataclasses import dataclass
import sys
import os

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(__file__))

from logger import get_logger

logger = get_logger(__name__)


@dataclass
class InstanceInfo:
    """Information about an EC2 instance."""
    instance_id: str
    state: str
    tags: Dict[str, str]


@dataclass
class ShutdownResult:
    """Result of an instance shutdown operation."""
    instance_id: str
    success: bool
    error: Optional[str] = None
    previous_state: str = ""


class EC2Service:
    """EC2 service wrapper with retry logic and error handling."""
    
    def __init__(self, region_name: Optional[str] = None):
        """
        Initialize EC2 service with retry configuration.
        
        Args:
            region_name: AWS region name. If None, uses default region.
        """
        # Configure retry strategy for throttling (exponential backoff)
        retry_config = Config(
            retries={
                'max_attempts': 5,
                'mode': 'adaptive'  # Uses exponential backoff with jitter
            }
        )
        
        self.ec2_client = boto3.client(
            'ec2',
            region_name=region_name,
            config=retry_config
        )
        self.region_name = region_name or boto3.Session().region_name
        logger.info(f"Initialized EC2 service for region: {self.region_name}")
    
    def _retry_with_linear_backoff(self, func, *args, max_retries: int = 3, delay: float = 2.0, **kwargs):
        """
        Retry function with linear backoff for network errors.
        
        Args:
            func: Function to retry
            max_retries: Maximum number of retry attempts
            delay: Delay between retries in seconds
            *args, **kwargs: Arguments to pass to the function
            
        Returns:
            Function result
            
        Raises:
            Last exception if all retries fail
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except (BotoCoreError, ConnectionError) as e:
                last_exception = e
                if attempt < max_retries:
                    logger.warn(f"Network error on attempt {attempt + 1}, retrying in {delay}s: {str(e)}")
                    time.sleep(delay)
                else:
                    logger.error(f"All retry attempts failed: {str(e)}")
                    raise last_exception
            except ClientError as e:
                # Don't retry client errors (permissions, throttling handled by boto3 config)
                raise e
        
        raise last_exception
    
    def get_instances_with_tag(self, tag_key: str, tag_value: str) -> List[InstanceInfo]:
        """
        Discover EC2 instances with specific tag key/value.
        
        Args:
            tag_key: The tag key to filter by
            tag_value: The tag value to filter by
            
        Returns:
            List of InstanceInfo objects matching the tag criteria
            
        Raises:
            ClientError: If AWS API call fails
            BotoCoreError: If network/connection issues occur
        """
        logger.info(f"Discovering instances with tag {tag_key}={tag_value}")
        
        instances = []
        paginator = self.ec2_client.get_paginator('describe_instances')
        
        # Filter instances by tag
        filters = [
            {
                'Name': f'tag:{tag_key}',
                'Values': [tag_value]
            }
        ]
        
        try:
            # Use retry logic for the paginated API calls
            def _describe_instances_page(page_iterator):
                results = []
                for page in page_iterator:
                    for reservation in page.get('Reservations', []):
                        for instance in reservation.get('Instances', []):
                            # Extract tags into a dictionary
                            tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                            
                            instance_info = InstanceInfo(
                                instance_id=instance['InstanceId'],
                                state=instance['State']['Name'],
                                tags=tags
                            )
                            results.append(instance_info)
                            logger.info(f"Found instance {instance['InstanceId']} in state {instance['State']['Name']}")
                
                return results
            
            page_iterator = paginator.paginate(Filters=filters)
            instances = self._retry_with_linear_backoff(_describe_instances_page, page_iterator)
            
            logger.info(f"Discovered {len(instances)} instances with tag {tag_key}={tag_value}")
            return instances
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"AWS API error discovering instances: {error_code} - {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error discovering instances: {str(e)}")
            raise
    
    def stop_instance(self, instance_id: str) -> ShutdownResult:
        """
        Stop a single EC2 instance.
        
        Args:
            instance_id: The ID of the instance to stop
            
        Returns:
            ShutdownResult with operation details
        """
        logger.info(f"Attempting to stop instance {instance_id}")
        
        try:
            # First, get the current state of the instance
            response = self._retry_with_linear_backoff(
                self.ec2_client.describe_instances,
                InstanceIds=[instance_id]
            )
            
            if not response['Reservations']:
                error_msg = f"Instance {instance_id} not found"
                logger.error(error_msg)
                return ShutdownResult(
                    instance_id=instance_id,
                    success=False,
                    error=error_msg
                )
            
            instance = response['Reservations'][0]['Instances'][0]
            current_state = instance['State']['Name']
            
            # Skip if already stopped
            if current_state in ['stopped', 'stopping']:
                logger.info(f"Instance {instance_id} is already {current_state}, skipping")
                return ShutdownResult(
                    instance_id=instance_id,
                    success=True,
                    previous_state=current_state
                )
            
            # Stop the instance
            self._retry_with_linear_backoff(
                self.ec2_client.stop_instances,
                InstanceIds=[instance_id]
            )
            
            logger.info(f"Successfully initiated stop for instance {instance_id} (was {current_state})")
            return ShutdownResult(
                instance_id=instance_id,
                success=True,
                previous_state=current_state
            )
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = f"AWS API error stopping instance {instance_id}: {error_code} - {str(e)}"
            
            # Handle permission errors gracefully
            if error_code in ['UnauthorizedOperation', 'AccessDenied']:
                logger.warn(f"Permission denied stopping instance {instance_id}: {str(e)}")
            else:
                logger.error(error_msg)
            
            return ShutdownResult(
                instance_id=instance_id,
                success=False,
                error=error_msg
            )
            
        except Exception as e:
            error_msg = f"Unexpected error stopping instance {instance_id}: {str(e)}"
            logger.error(error_msg)
            return ShutdownResult(
                instance_id=instance_id,
                success=False,
                error=error_msg
            )