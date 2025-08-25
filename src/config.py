"""
Configuration management module for EC2 Auto-Shutdown Lambda.

This module handles reading environment variables with defaults and validates
configuration values according to requirements 4.1, 4.2, and 4.3.
"""

import os
from typing import Optional


class Config:
    """Configuration class that manages environment variables with defaults."""
    
    def __init__(self):
        """Initialize configuration by reading environment variables."""
        self._shutdown_tag_key = self._get_env_var('SHUTDOWN_TAG_KEY', 'AutoShutdown')
        self._shutdown_tag_value = self._get_env_var('SHUTDOWN_TAG_VALUE', 'yes')
        self._aws_region = self._get_env_var('AWS_REGION', None)
        
        # Validate configuration
        self._validate_config()
    
    @property
    def shutdown_tag_key(self) -> str:
        """Get the tag key used to identify instances for shutdown."""
        return self._shutdown_tag_key
    
    @property
    def shutdown_tag_value(self) -> str:
        """Get the tag value used to identify instances for shutdown."""
        return self._shutdown_tag_value
    
    @property
    def aws_region(self) -> Optional[str]:
        """Get the AWS region. Returns None if not set (Lambda runtime will provide it)."""
        return self._aws_region
    
    def _get_env_var(self, key: str, default: Optional[str]) -> Optional[str]:
        """Get environment variable with optional default value."""
        value = os.environ.get(key, default)
        return value.strip() if value else value
    
    def _validate_config(self) -> None:
        """Validate configuration values."""
        if not self._shutdown_tag_key:
            raise ValueError("SHUTDOWN_TAG_KEY cannot be empty")
        
        if not self._shutdown_tag_value:
            raise ValueError("SHUTDOWN_TAG_VALUE cannot be empty")
        
        # Tag key validation - AWS tag keys have specific requirements
        if len(self._shutdown_tag_key) > 128:
            raise ValueError("SHUTDOWN_TAG_KEY cannot exceed 128 characters")
        
        # Tag value validation - AWS tag values have specific requirements
        if len(self._shutdown_tag_value) > 256:
            raise ValueError("SHUTDOWN_TAG_VALUE cannot exceed 256 characters")


# Global configuration instance
config = Config()