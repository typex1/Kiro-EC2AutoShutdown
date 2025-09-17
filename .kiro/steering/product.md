# Product Overview

EC2 Auto-Shutdown Lambda Function - An AWS serverless solution that automatically shuts down EC2 instances based on tags to reduce costs and improve resource management.

## Core Functionality
- Automatically stops EC2 instances tagged with `AutoShutdown=yes`
- Runs on a configurable schedule (default: 6 PM weekdays UTC)
- Provides comprehensive logging and CloudWatch monitoring
- Handles errors gracefully with detailed reporting

## Key Features
- Tag-based instance selection with configurable tag key/value pairs
- Scheduled execution via CloudWatch Events
- Custom CloudWatch metrics for monitoring
- Comprehensive error handling and logging
- Integration tests for reliability

## Use Case
Cost optimization tool for development and staging environments where EC2 instances can be safely shut down during off-hours to reduce AWS costs.
