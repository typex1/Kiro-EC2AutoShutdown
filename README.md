# EC2 Auto-Shutdown Lambda Function

AWS Lambda function that automatically shuts down EC2 instances based on tags.

## Project Structure

```
├── src/                    # Source code
│   ├── lambda_function.py  # Main Lambda handler
│   ├── config.py          # Configuration management
│   ├── logger.py          # Logging utilities
│   └── ec2_service.py     # EC2 service interactions
├── tests/                 # Unit tests
│   ├── test_*.py         # Unit test files
│   └── integration/      # Integration tests
├── requirements.txt      # Python dependencies
└── pytest.ini          # Test configuration
```

## Development

1. Install dependencies: `pip install -r requirements.txt`
2. Run tests: `pytest`
3. Run specific test: `pytest tests/test_lambda_function.py`

## Deployment

To be documented in later implementation phases.