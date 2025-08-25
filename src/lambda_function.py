"""
Main Lambda handler for EC2 Auto-Shutdown function.

This module orchestrates the shutdown process by integrating configuration,
logging, and EC2 service modules to automatically stop tagged EC2 instances.
"""

import json
import uuid
import boto3
import sys
import os
from typing import Dict, Any, List

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(__file__))

from config import config
from logger import get_logger
from ec2_service import EC2Service, ShutdownResult


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler function that orchestrates the EC2 shutdown process.
    
    Args:
        event: Lambda event object
        context: Lambda context object
        
    Returns:
        Dictionary containing status code and response body with statistics
    """
    # Generate correlation ID for request tracing
    correlation_id = str(uuid.uuid4())
    logger = get_logger("ec2-auto-shutdown", correlation_id)
    
    # Initialize variables for error handling
    results = []
    instances = []
    
    try:
        logger.info("Starting EC2 auto-shutdown process", 
                   extra={"tag_key": config.shutdown_tag_key, 
                         "tag_value": config.shutdown_tag_value})
        
        # Initialize EC2 service with error handling
        try:
            ec2_service = EC2Service(region_name=config.aws_region)
        except Exception as e:
            error_msg = f"Failed to initialize EC2 service: {str(e)}"
            logger.error(error_msg, extra={"error_type": type(e).__name__})
            return _create_error_response(error_msg)
        
        # Discover instances with shutdown tag
        try:
            instances = ec2_service.get_instances_with_tag(
                config.shutdown_tag_key, 
                config.shutdown_tag_value
            )
        except Exception as e:
            error_msg = f"Failed to discover instances: {str(e)}"
            logger.error(error_msg, extra={"error_type": type(e).__name__})
            return _create_error_response(error_msg)
        
        if not instances:
            logger.info("No instances found with shutdown tag")
            return _create_response(200, {
                "processedInstances": 0,
                "stoppedInstances": 0,
                "skippedInstances": 0,
                "errors": [],
                "summary": "No instances found with shutdown tag"
            })
        
        # Process each instance - continue even if individual instances fail
        for instance in instances:
            try:
                logger.info(f"Processing instance {instance.instance_id}", 
                           extra={"instance_id": instance.instance_id, 
                                 "current_state": instance.state})
                
                result = ec2_service.stop_instance(instance.instance_id)
                results.append(result)
                
                if result.success:
                    if result.previous_state in ['stopped', 'stopping']:
                        logger.info(f"Instance {instance.instance_id} was already {result.previous_state}")
                    else:
                        logger.info(f"Successfully stopped instance {instance.instance_id}")
                else:
                    logger.error(f"Failed to stop instance {instance.instance_id}: {result.error}")
                    
            except Exception as e:
                # Handle unexpected errors during individual instance processing
                error_msg = f"Unexpected error processing instance {instance.instance_id}: {str(e)}"
                logger.error(error_msg, extra={
                    "instance_id": instance.instance_id,
                    "error_type": type(e).__name__
                })
                # Create a failed result for this instance and continue
                results.append(ShutdownResult(
                    instance_id=instance.instance_id,
                    success=False,
                    error=error_msg,
                    previous_state=getattr(instance, 'state', 'unknown')
                ))
        
        # Generate summary statistics
        summary_stats = _generate_summary(results)
        
        # Send custom metrics to CloudWatch
        _send_custom_metrics(summary_stats, logger)
        
        logger.info("EC2 auto-shutdown process completed", 
                   extra=summary_stats)
        
        # Determine appropriate status code based on results
        status_code = 200
        if summary_stats['errors'] and summary_stats['stoppedInstances'] == 0:
            # All operations failed
            status_code = 207  # Multi-status for partial failures
        elif summary_stats['errors']:
            # Some operations failed
            status_code = 207  # Multi-status for partial failures
        
        return _create_response(status_code, {
            **summary_stats,
            "summary": f"Processed {summary_stats['processedInstances']} instances, "
                      f"stopped {summary_stats['stoppedInstances']}, "
                      f"skipped {summary_stats['skippedInstances']}, "
                      f"errors: {len(summary_stats['errors'])}"
        })
        
    except Exception as e:
        # Top-level error handler for any unexpected exceptions
        error_msg = f"Unexpected error in Lambda handler: {str(e)}"
        logger.error(error_msg, extra={
            "error_type": type(e).__name__,
            "instances_discovered": len(instances),
            "instances_processed": len(results)
        })
        
        return _create_error_response(error_msg)


def _generate_summary(results: List[ShutdownResult]) -> Dict[str, Any]:
    """
    Generate summary statistics from shutdown results.
    
    Args:
        results: List of ShutdownResult objects
        
    Returns:
        Dictionary containing summary statistics
    """
    processed_count = len(results)
    stopped_count = 0
    skipped_count = 0
    errors = []
    
    for result in results:
        if result.success:
            if result.previous_state in ['stopped', 'stopping']:
                skipped_count += 1
            else:
                stopped_count += 1
        else:
            errors.append({
                "instance_id": result.instance_id,
                "error": result.error
            })
    
    return {
        "processedInstances": processed_count,
        "stoppedInstances": stopped_count,
        "skippedInstances": skipped_count,
        "errors": errors
    }


def _create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a properly formatted Lambda response.
    
    Args:
        status_code: HTTP status code
        body: Response body dictionary
        
    Returns:
        Lambda response dictionary
    """
    return {
        "statusCode": status_code,
        "body": json.dumps(body, indent=2)
    }


def _send_custom_metrics(summary_stats: Dict[str, Any], logger) -> None:
    """
    Send custom metrics to CloudWatch for monitoring.
    
    Args:
        summary_stats: Summary statistics from shutdown process
        logger: Logger instance for error reporting
    """
    try:
        cloudwatch = boto3.client('cloudwatch')
        
        # Prepare metric data
        metric_data = [
            {
                'MetricName': 'InstancesProcessed',
                'Value': summary_stats['processedInstances'],
                'Unit': 'Count',
                'Dimensions': [
                    {
                        'Name': 'FunctionName',
                        'Value': 'ec2-auto-shutdown'
                    }
                ]
            },
            {
                'MetricName': 'InstancesStopped',
                'Value': summary_stats['stoppedInstances'],
                'Unit': 'Count',
                'Dimensions': [
                    {
                        'Name': 'FunctionName',
                        'Value': 'ec2-auto-shutdown'
                    }
                ]
            },
            {
                'MetricName': 'InstancesSkipped',
                'Value': summary_stats['skippedInstances'],
                'Unit': 'Count',
                'Dimensions': [
                    {
                        'Name': 'FunctionName',
                        'Value': 'ec2-auto-shutdown'
                    }
                ]
            },
            {
                'MetricName': 'ErrorCount',
                'Value': len(summary_stats['errors']),
                'Unit': 'Count',
                'Dimensions': [
                    {
                        'Name': 'FunctionName',
                        'Value': 'ec2-auto-shutdown'
                    }
                ]
            }
        ]
        
        # Send metrics to CloudWatch
        cloudwatch.put_metric_data(
            Namespace='EC2AutoShutdown',
            MetricData=metric_data
        )
        
        logger.info("Custom metrics sent to CloudWatch", extra={
            "metrics_sent": len(metric_data)
        })
        
    except Exception as e:
        # Don't fail the entire function if metrics fail
        logger.error(f"Failed to send custom metrics: {str(e)}", extra={
            "error_type": type(e).__name__
        })


def _create_error_response(error_message: str) -> Dict[str, Any]:
    """
    Create a standardized error response for Lambda failures.
    
    Args:
        error_message: Error message to include in response
        
    Returns:
        Lambda error response dictionary
    """
    return _create_response(500, {
        "processedInstances": 0,
        "stoppedInstances": 0,
        "skippedInstances": 0,
        "errors": [error_message],
        "summary": "Lambda function failed with unexpected error"
    })