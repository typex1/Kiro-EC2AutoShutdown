#!/usr/bin/env python3
"""
Integration test runner script for EC2 Auto-Shutdown Lambda function.

This script provides a convenient way to run integration tests with proper
setup and validation of prerequisites.
"""

import os
import sys
import subprocess
import boto3
from botocore.exceptions import NoCredentialsError, ClientError


def check_aws_credentials():
    """Check if AWS credentials are available and valid."""
    try:
        session = boto3.Session()
        credentials = session.get_credentials()
        if not credentials:
            return False, "No AWS credentials found"
        
        # Test credentials by making a simple API call
        sts = boto3.client('sts')
        response = sts.get_caller_identity()
        account_id = response.get('Account')
        user_arn = response.get('Arn')
        
        return True, f"AWS credentials valid - Account: {account_id}, User: {user_arn}"
        
    except NoCredentialsError:
        return False, "AWS credentials not configured"
    except ClientError as e:
        return False, f"AWS credentials invalid: {str(e)}"
    except Exception as e:
        return False, f"Error checking AWS credentials: {str(e)}"


def check_aws_permissions():
    """Check if required AWS permissions are available."""
    required_permissions = [
        ('ec2', 'describe_instances'),
        ('ec2', 'describe_regions'),
    ]
    
    permission_results = []
    
    for service_name, operation in required_permissions:
        try:
            if service_name == 'ec2':
                client = boto3.client('ec2')
                if operation == 'describe_instances':
                    client.describe_instances(MaxResults=5)
                elif operation == 'describe_regions':
                    client.describe_regions()
            
            permission_results.append((service_name, operation, True, "OK"))
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code in ['UnauthorizedOperation', 'AccessDenied']:
                permission_results.append((service_name, operation, False, f"Permission denied: {error_code}"))
            else:
                permission_results.append((service_name, operation, True, f"Permission OK (other error: {error_code})"))
        except Exception as e:
            permission_results.append((service_name, operation, False, f"Error: {str(e)}"))
    
    return permission_results


def setup_test_environment():
    """Set up environment variables for testing."""
    # Set default region if not specified
    if not os.environ.get('AWS_REGION'):
        os.environ['AWS_REGION'] = 'us-east-1'
        print(f"Set AWS_REGION to default: {os.environ['AWS_REGION']}")
    
    # Set test-specific environment variables if not already set
    test_env_vars = {
        'SHUTDOWN_TAG_KEY': f'IntegrationTest-{os.urandom(4).hex()}',
        'SHUTDOWN_TAG_VALUE': 'test-shutdown'
    }
    
    for key, default_value in test_env_vars.items():
        if not os.environ.get(key):
            os.environ[key] = default_value
            print(f"Set {key} to: {os.environ[key]}")


def run_integration_tests(test_args=None):
    """Run the integration tests with pytest."""
    cmd = [
        sys.executable, '-m', 'pytest',
        'tests/integration/',
        '-m', 'integration',
        '-v',
        '--tb=short'
    ]
    
    if test_args:
        cmd.extend(test_args)
    
    print(f"Running command: {' '.join(cmd)}")
    print("-" * 60)
    
    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\nTest execution interrupted by user")
        return 130
    except Exception as e:
        print(f"Error running tests: {str(e)}")
        return 1


def main():
    """Main function to run integration tests with setup and validation."""
    print("EC2 Auto-Shutdown Lambda - Integration Test Runner")
    print("=" * 60)
    
    # Check if integration tests should be skipped
    if os.environ.get('SKIP_INTEGRATION_TESTS', '').lower() == 'true':
        print("Integration tests skipped via SKIP_INTEGRATION_TESTS environment variable")
        return 0
    
    # Check AWS credentials
    print("1. Checking AWS credentials...")
    creds_valid, creds_message = check_aws_credentials()
    print(f"   {creds_message}")
    
    if not creds_valid:
        print("\nERROR: AWS credentials are required for integration tests")
        print("Please configure AWS credentials using one of these methods:")
        print("  - aws configure")
        print("  - Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables")
        print("  - Use IAM role (when running on EC2)")
        return 1
    
    # Check AWS permissions
    print("\n2. Checking AWS permissions...")
    permission_results = check_aws_permissions()
    
    has_required_permissions = True
    for service, operation, success, message in permission_results:
        status = "✓" if success else "✗"
        print(f"   {status} {service}:{operation} - {message}")
        if not success and "Permission denied" in message:
            has_required_permissions = False
    
    if not has_required_permissions:
        print("\nWARNING: Some required permissions are missing")
        print("Integration tests may fail or have limited functionality")
        print("Required IAM permissions:")
        print("  - ec2:DescribeInstances")
        print("  - ec2:DescribeRegions")
        print("  - ec2:StopInstances")
        print("  - logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents")
        
        response = input("\nContinue anyway? (y/N): ")
        if response.lower() != 'y':
            return 1
    
    # Set up test environment
    print("\n3. Setting up test environment...")
    setup_test_environment()
    
    # Run tests
    print("\n4. Running integration tests...")
    test_args = sys.argv[1:] if len(sys.argv) > 1 else None
    return_code = run_integration_tests(test_args)
    
    print("\n" + "=" * 60)
    if return_code == 0:
        print("✓ All integration tests passed!")
    else:
        print(f"✗ Integration tests failed with return code: {return_code}")
    
    return return_code


if __name__ == "__main__":
    sys.exit(main())