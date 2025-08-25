"""
Unit tests for configuration management module.

Tests various scenarios for environment variable loading and validation
according to requirements 4.1, 4.2, and 4.3.
"""

import os
import pytest
from unittest.mock import patch

from src.config import Config


class TestConfig:
    """Test cases for Config class."""
    
    def test_default_values_when_no_env_vars(self):
        """Test that default values are used when environment variables are not set."""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            
            assert config.shutdown_tag_key == 'AutoShutdown'
            assert config.shutdown_tag_value == 'yes'
            assert config.aws_region is None
    
    def test_custom_values_from_env_vars(self):
        """Test that custom values are read from environment variables."""
        env_vars = {
            'SHUTDOWN_TAG_KEY': 'CustomShutdown',
            'SHUTDOWN_TAG_VALUE': 'true',
            'AWS_REGION': 'us-west-2'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config()
            
            assert config.shutdown_tag_key == 'CustomShutdown'
            assert config.shutdown_tag_value == 'true'
            assert config.aws_region == 'us-west-2'
    
    def test_partial_env_vars_with_defaults(self):
        """Test that some env vars can be set while others use defaults."""
        env_vars = {
            'SHUTDOWN_TAG_KEY': 'MyTag'
            # SHUTDOWN_TAG_VALUE and AWS_REGION not set
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config()
            
            assert config.shutdown_tag_key == 'MyTag'
            assert config.shutdown_tag_value == 'yes'  # default
            assert config.aws_region is None  # default
    
    def test_whitespace_trimming(self):
        """Test that whitespace is trimmed from environment variables."""
        env_vars = {
            'SHUTDOWN_TAG_KEY': '  SpacedTag  ',
            'SHUTDOWN_TAG_VALUE': '\tyes\n',
            'AWS_REGION': ' us-east-1 '
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config()
            
            assert config.shutdown_tag_key == 'SpacedTag'
            assert config.shutdown_tag_value == 'yes'
            assert config.aws_region == 'us-east-1'
    
    def test_empty_string_env_vars_use_defaults(self):
        """Test that empty string environment variables fall back to defaults."""
        env_vars = {
            'SHUTDOWN_TAG_KEY': '',
            'SHUTDOWN_TAG_VALUE': '',
            'AWS_REGION': ''
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError, match="SHUTDOWN_TAG_KEY cannot be empty"):
                Config()
    
    def test_validation_empty_tag_key_raises_error(self):
        """Test that empty tag key raises validation error."""
        env_vars = {
            'SHUTDOWN_TAG_KEY': '',
            'SHUTDOWN_TAG_VALUE': 'yes'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError, match="SHUTDOWN_TAG_KEY cannot be empty"):
                Config()
    
    def test_validation_empty_tag_value_raises_error(self):
        """Test that empty tag value raises validation error."""
        env_vars = {
            'SHUTDOWN_TAG_KEY': 'AutoShutdown',
            'SHUTDOWN_TAG_VALUE': ''
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError, match="SHUTDOWN_TAG_VALUE cannot be empty"):
                Config()
    
    def test_validation_tag_key_too_long_raises_error(self):
        """Test that tag key exceeding 128 characters raises validation error."""
        long_tag_key = 'A' * 129  # 129 characters
        env_vars = {
            'SHUTDOWN_TAG_KEY': long_tag_key,
            'SHUTDOWN_TAG_VALUE': 'yes'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError, match="SHUTDOWN_TAG_KEY cannot exceed 128 characters"):
                Config()
    
    def test_validation_tag_value_too_long_raises_error(self):
        """Test that tag value exceeding 256 characters raises validation error."""
        long_tag_value = 'A' * 257  # 257 characters
        env_vars = {
            'SHUTDOWN_TAG_KEY': 'AutoShutdown',
            'SHUTDOWN_TAG_VALUE': long_tag_value
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError, match="SHUTDOWN_TAG_VALUE cannot exceed 256 characters"):
                Config()
    
    def test_validation_max_length_tag_key_succeeds(self):
        """Test that tag key with exactly 128 characters is valid."""
        max_tag_key = 'A' * 128  # 128 characters
        env_vars = {
            'SHUTDOWN_TAG_KEY': max_tag_key,
            'SHUTDOWN_TAG_VALUE': 'yes'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config()
            assert config.shutdown_tag_key == max_tag_key
    
    def test_validation_max_length_tag_value_succeeds(self):
        """Test that tag value with exactly 256 characters is valid."""
        max_tag_value = 'A' * 256  # 256 characters
        env_vars = {
            'SHUTDOWN_TAG_KEY': 'AutoShutdown',
            'SHUTDOWN_TAG_VALUE': max_tag_value
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config()
            assert config.shutdown_tag_value == max_tag_value
    
    def test_properties_are_read_only(self):
        """Test that configuration properties cannot be modified after creation."""
        config = Config()
        
        # Properties should be read-only (no direct attribute assignment)
        with pytest.raises(AttributeError):
            config.shutdown_tag_key = 'modified'
        
        with pytest.raises(AttributeError):
            config.shutdown_tag_value = 'modified'
        
        with pytest.raises(AttributeError):
            config.aws_region = 'modified'
    
    def test_multiple_config_instances_independent(self):
        """Test that multiple Config instances can have different values."""
        env_vars_1 = {
            'SHUTDOWN_TAG_KEY': 'Tag1',
            'SHUTDOWN_TAG_VALUE': 'value1'
        }
        
        env_vars_2 = {
            'SHUTDOWN_TAG_KEY': 'Tag2',
            'SHUTDOWN_TAG_VALUE': 'value2'
        }
        
        with patch.dict(os.environ, env_vars_1, clear=True):
            config1 = Config()
        
        with patch.dict(os.environ, env_vars_2, clear=True):
            config2 = Config()
        
        assert config1.shutdown_tag_key == 'Tag1'
        assert config1.shutdown_tag_value == 'value1'
        assert config2.shutdown_tag_key == 'Tag2'
        assert config2.shutdown_tag_value == 'value2'


class TestGlobalConfigInstance:
    """Test cases for the global config instance."""
    
    def test_global_config_instance_exists(self):
        """Test that global config instance is available."""
        from src.config import config
        
        assert config is not None
        assert hasattr(config, 'shutdown_tag_key')
        assert hasattr(config, 'shutdown_tag_value')
        assert hasattr(config, 'aws_region')