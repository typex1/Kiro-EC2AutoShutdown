"""
Helper functions and imports for integration tests.
"""

import sys
import os

# Add the project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def get_lambda_handler():
    """Import and return the lambda handler function."""
    from src.lambda_function import lambda_handler
    return lambda_handler


def get_ec2_service():
    """Import and return the EC2Service class."""
    from src.ec2_service import EC2Service, InstanceInfo, ShutdownResult
    return EC2Service, InstanceInfo, ShutdownResult


def get_config():
    """Import and return the Config class."""
    from src.config import Config
    return Config


def get_logger():
    """Import and return the logger function."""
    from src.logger import get_logger
    return get_logger


def reload_config():
    """Reload the config module to pick up environment variable changes."""
    import importlib
    import src.config
    importlib.reload(src.config)
    return src.config.config