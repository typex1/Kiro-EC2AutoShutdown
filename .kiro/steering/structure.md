# Project Structure

## Directory Organization

```
├── src/                    # Source code (Lambda deployment package)
│   ├── lambda_function.py  # Main Lambda handler - entry point
│   ├── config.py          # Configuration management with env vars
│   ├── logger.py          # Structured logging utilities
│   └── ec2_service.py     # EC2 service interactions and business logic
├── tests/                 # Test suite
│   ├── test_*.py         # Unit tests (mirror src/ structure)
│   └── integration/      # Integration tests with AWS services
├── .kiro/                # Kiro AI assistant configuration
│   └── steering/         # Project guidance documents
├── .aws-sam/             # SAM build artifacts (generated)
└── deployment files     # Infrastructure and deployment scripts
```

## Code Organization Patterns

### Module Responsibilities
- **lambda_function.py** - Orchestration, error handling, response formatting
- **config.py** - Environment variable management and validation
- **logger.py** - Centralized logging with correlation IDs
- **ec2_service.py** - AWS EC2 API interactions and business logic

### Import Conventions
- Use relative imports within the src/ package
- Add current directory to sys.path for Lambda compatibility
- Import order: standard library, third-party, local modules

### Error Handling
- Comprehensive try-catch blocks with specific error types
- Graceful degradation - continue processing other instances on individual failures
- Structured error responses with consistent format

### Testing Structure
- Unit tests mirror src/ directory structure
- Integration tests in separate subdirectory
- Use pytest markers: `@pytest.mark.integration` and `@pytest.mark.unit`
- Mock AWS services using moto library for unit tests

### Configuration Files
- **template.yaml** - SAM template with infrastructure definition
- **requirements.txt** - Python dependencies with version constraints
- **pytest.ini** - Test configuration and markers
- **parameters.json** - Deployment parameter overrides
