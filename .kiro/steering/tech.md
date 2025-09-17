# Technology Stack

## Runtime & Framework
- **Python 3.9** - Lambda runtime
- **AWS SAM** - Serverless Application Model for deployment
- **CloudFormation** - Infrastructure as Code

## Key Libraries
- `boto3` - AWS SDK for Python (>=1.26.0)
- `botocore` - Low-level AWS service access (>=1.29.0)
- `pytest` - Testing framework (>=7.0.0)
- `pytest-mock` - Mock utilities for testing (>=3.10.0)
- `moto` - AWS service mocking for tests (>=4.2.0)

## AWS Services
- **Lambda** - Serverless compute
- **EC2** - Instance management
- **CloudWatch** - Logging, metrics, and alarms
- **EventBridge** - Scheduled execution
- **IAM** - Permissions management

## Common Commands

### Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Run specific test file
pytest tests/test_lambda_function.py

# Run unit tests only (exclude integration)
pytest -m "not integration"

# Run integration tests
pytest tests/integration/
```

### Deployment
```bash
# Deploy using SAM (requires SAM_DEPLOYMENT_BUCKET env var)
./deploy.sh

# Build SAM application
sam build

# Deploy with custom parameters
sam deploy --parameter-overrides ShutdownTagKey=MyTag ShutdownTagValue=stop
```

### Monitoring
```bash
# View CloudWatch logs
aws logs tail /aws/lambda/ec2-auto-shutdown --follow

# Check stack status
aws cloudformation describe-stacks --stack-name ec2-auto-shutdown
```
