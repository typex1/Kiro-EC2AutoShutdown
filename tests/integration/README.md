# Integration Tests

This directory contains integration tests for the EC2 Auto-Shutdown Lambda function. These tests work with real AWS services and require proper AWS credentials and permissions.

## Prerequisites

### AWS Credentials
Configure AWS credentials using one of these methods:
- AWS CLI: `aws configure`
- Environment variables: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- IAM role (when running on EC2 or Lambda)
- AWS credentials file

### IAM Permissions
The integration tests require the following IAM permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeRegions",
        "ec2:StopInstances"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

## Running Integration Tests

### Run All Integration Tests
```bash
pytest tests/integration/ -m integration
```

### Run Specific Test Classes
```bash
# Test EC2 service integration
pytest tests/integration/test_lambda_integration.py::TestEC2ServiceIntegration -v

# Test Lambda handler integration
pytest tests/integration/test_lambda_integration.py::TestLambdaHandlerIntegration -v

# Test end-to-end scenarios
pytest tests/integration/test_lambda_integration.py::TestEndToEndScenarios -v
```

### Skip Integration Tests
```bash
# Run only unit tests (skip integration)
pytest -m "not integration"

# Skip via environment variable
SKIP_INTEGRATION_TESTS=true pytest
```

## Environment Variables

### Required
- `AWS_REGION`: AWS region to run tests in (default: us-east-1)

### Optional
- `SKIP_INTEGRATION_TESTS`: Set to 'true' to skip integration tests
- `SHUTDOWN_TAG_KEY`: Override default tag key for testing
- `SHUTDOWN_TAG_VALUE`: Override default tag value for testing

## Test Coverage

The integration tests cover:

### EC2 Service Integration
- ✅ EC2 service initialization with real AWS credentials
- ✅ Instance discovery with various tag combinations
- ✅ Handling of nonexistent instances
- ✅ IAM permission verification
- ✅ Retry logic with network errors
- ✅ Error handling for invalid regions

### Lambda Handler Integration
- ✅ End-to-end Lambda handler execution
- ✅ Response format validation
- ✅ Error handling with invalid configurations
- ✅ Proper JSON response structure
- ✅ Status code handling for various scenarios

### End-to-End Scenarios
- ✅ Configuration loading from environment variables
- ✅ Logging integration in AWS environment
- ✅ AWS service connectivity verification
- ✅ Multiple tag combination testing
- ✅ Error recovery scenarios
- ✅ Invalid input handling

## Test Safety

The integration tests are designed to be safe:

- Uses unique test tag keys to avoid conflicts with real instances
- Only attempts to stop test instances (with specific test tags)
- Handles permission errors gracefully
- Cleans up test environment variables after execution
- Skips tests if AWS credentials are not available

## Troubleshooting

### Common Issues

1. **AWS Credentials Not Found**
   ```
   Solution: Configure AWS credentials using aws configure or environment variables
   ```

2. **Permission Denied Errors**
   ```
   Solution: Ensure IAM user/role has required EC2 and CloudWatch permissions
   ```

3. **Region Not Found**
   ```
   Solution: Set AWS_REGION environment variable to a valid AWS region
   ```

4. **Tests Taking Too Long**
   ```
   Solution: Set SKIP_INTEGRATION_TESTS=true to skip integration tests during development
   ```

### Debug Mode
Run tests with verbose output and no capture:
```bash
pytest tests/integration/ -v -s --tb=long -m integration
```

## CI/CD Integration

For CI/CD pipelines, consider:

1. **Separate Test Environment**: Use dedicated AWS account/region for testing
2. **IAM Roles**: Use IAM roles instead of access keys in CI/CD
3. **Test Data**: Create test EC2 instances with appropriate tags
4. **Cleanup**: Ensure test resources are cleaned up after tests
5. **Conditional Execution**: Skip integration tests in PR builds, run in main branch

Example CI configuration:
```yaml
# Only run integration tests on main branch
- name: Run Integration Tests
  if: github.ref == 'refs/heads/main'
  run: pytest tests/integration/ -m integration
  env:
    AWS_REGION: us-east-1
```