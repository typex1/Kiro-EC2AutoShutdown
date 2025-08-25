# EC2 Auto-Shutdown Lambda - Deployment and Operations Guide

## Overview

This document provides comprehensive guidance for deploying, monitoring, and operating the EC2 Auto-Shutdown Lambda function. The function automatically stops EC2 instances tagged with `AutoShutdown=yes` on a scheduled basis to reduce AWS costs.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Deployment Options](#deployment-options)
3. [Configuration](#configuration)
4. [Monitoring and Alerting](#monitoring-and-alerting)
5. [Operational Procedures](#operational-procedures)
6. [Troubleshooting](#troubleshooting)
7. [Security Considerations](#security-considerations)
8. [Cost Optimization](#cost-optimization)

## Prerequisites

### Required Tools
- AWS CLI v2.x or later
- AWS SAM CLI (for SAM deployment)
- Python 3.9+ (for local testing)
- jq (for JSON processing in scripts)

### AWS Permissions
The deploying user/role needs the following permissions:
- CloudFormation: Full access to create/update stacks
- Lambda: Create and manage functions
- IAM: Create roles and policies
- CloudWatch: Create alarms, dashboards, and log groups
- EventBridge: Create and manage rules
- S3: Access to deployment bucket (for SAM)

### AWS Account Setup
- Ensure AWS CLI is configured with appropriate credentials
- Have an S3 bucket available for deployment artifacts (SAM only)
- Optionally, have an SNS topic for alarm notifications

## Deployment Options

### Option 1: SAM Deployment (Recommended)

SAM provides the simplest deployment experience with built-in best practices.

```bash
# Set required environment variables
export SAM_DEPLOYMENT_BUCKET="your-deployment-bucket"
export SHUTDOWN_TAG_KEY="AutoShutdown"  # Optional, defaults to "AutoShutdown"
export SHUTDOWN_TAG_VALUE="yes"         # Optional, defaults to "yes"
export SCHEDULE_EXPRESSION="cron(0 18 * * MON-FRI *)"  # Optional

# Deploy using the enhanced script
./deploy-with-monitoring.sh
```

### Option 2: CloudFormation Deployment

For environments where SAM is not available or for more control over the deployment process.

```bash
# Set environment variables
export DEPLOYMENT_TYPE="cloudformation"
export SHUTDOWN_TAG_KEY="AutoShutdown"
export SHUTDOWN_TAG_VALUE="yes"
export SCHEDULE_EXPRESSION="cron(0 18 * * MON-FRI *)"

# Deploy using the enhanced script
./deploy-with-monitoring.sh
```

### Option 3: Manual Deployment

For step-by-step control or CI/CD integration:

```bash
# Build and package
sam build

# Deploy with specific parameters
sam deploy \
    --stack-name ec2-auto-shutdown \
    --s3-bucket your-deployment-bucket \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides \
        ShutdownTagKey=AutoShutdown \
        ShutdownTagValue=yes \
        ScheduleExpression="cron(0 18 * * MON-FRI *)"
```

## Configuration

### Environment Variables

The Lambda function uses the following environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SHUTDOWN_TAG_KEY` | `AutoShutdown` | Tag key to identify instances for shutdown |
| `SHUTDOWN_TAG_VALUE` | `yes` | Tag value to identify instances for shutdown |
| `AWS_REGION` | Auto-detected | AWS region (set by Lambda runtime) |

### Schedule Configuration

The function execution schedule is controlled by the `ScheduleExpression` parameter:

- **Default**: `cron(0 18 * * MON-FRI *)` (6 PM UTC, Monday-Friday)
- **Format**: Standard cron expression or rate expression
- **Examples**:
  - `cron(0 22 * * SUN-THU *)` - 10 PM UTC, Sunday-Thursday
  - `rate(1 hour)` - Every hour
  - `cron(0 18 * * ? *)` - 6 PM UTC every day

### EC2 Instance Tagging

Instances must be tagged appropriately for the function to process them:

```bash
# Tag an instance for automatic shutdown
aws ec2 create-tags \
    --resources i-1234567890abcdef0 \
    --tags Key=AutoShutdown,Value=yes

# Remove the tag to exclude from shutdown
aws ec2 delete-tags \
    --resources i-1234567890abcdef0 \
    --tags Key=AutoShutdown,Value=yes
```

## Monitoring and Alerting

### Setting Up Monitoring

After deployment, run the monitoring setup script:

```bash
# Basic monitoring setup
./setup-monitoring.sh

# With email notifications
export EMAIL_ADDRESS="admin@yourcompany.com"
./setup-monitoring.sh

# With custom SNS topic
export SNS_TOPIC_NAME="ec2-shutdown-alerts"
export EMAIL_ADDRESS="admin@yourcompany.com"
./setup-monitoring.sh
```

### Key Metrics

#### Custom Metrics (Namespace: EC2AutoShutdown)
- **InstancesProcessed**: Total instances evaluated per execution
- **InstancesStopped**: Instances successfully stopped
- **InstancesSkipped**: Instances already stopped
- **ErrorCount**: Errors encountered during execution

#### AWS Lambda Metrics
- **Duration**: Function execution time
- **Errors**: Function errors and exceptions
- **Throttles**: Concurrency limit throttling
- **Invocations**: Number of function executions

### CloudWatch Alarms

The deployment creates several alarms:

1. **Function Errors**: Alerts on any Lambda errors
2. **High Duration**: Alerts when execution time exceeds 4 minutes
3. **No Instances Processed**: Alerts when no instances processed in 24 hours
4. **High Error Rate**: Alerts when >5 errors occur in 1 hour
5. **Function Throttles**: Alerts on concurrency throttling

### Dashboard Access

- **Main Dashboard**: CloudWatch console → Dashboards → `{stack-name}-EC2AutoShutdown-Dashboard`
- **Enhanced Dashboard**: CloudWatch console → Dashboards → `{stack-name}-Enhanced-Dashboard`

## Operational Procedures

### Daily Operations

1. **Review Dashboard**: Check the CloudWatch dashboard for anomalies
2. **Verify Execution**: Confirm the function executed as scheduled
3. **Check Metrics**: Review instance processing metrics
4. **Monitor Alarms**: Ensure no active alarms

### Weekly Operations

1. **Log Review**: Analyze CloudWatch logs for trends
2. **Performance Review**: Check function duration and memory usage
3. **Tag Compliance**: Verify EC2 instances have correct tags
4. **Cost Analysis**: Review cost savings from automated shutdowns

### Monthly Operations

1. **Threshold Review**: Evaluate and adjust alarm thresholds
2. **Documentation Update**: Update procedures based on learnings
3. **Security Review**: Review IAM permissions and access logs
4. **Capacity Planning**: Assess if function limits need adjustment

### Testing Procedures

#### Manual Function Test
```bash
# Test the function manually
aws lambda invoke \
    --function-name ec2-auto-shutdown \
    --payload '{}' \
    --cli-binary-format raw-in-base64-out \
    response.json

# View the response
cat response.json | jq .
```

#### End-to-End Test
1. Create a test EC2 instance
2. Tag it with `AutoShutdown=yes`
3. Invoke the function manually
4. Verify the instance is stopped
5. Check logs and metrics

### Backup and Recovery

#### Configuration Backup
```bash
# Export stack template
aws cloudformation get-template \
    --stack-name ec2-auto-shutdown \
    --template-stage Processed > backup-template.json

# Export stack parameters
aws cloudformation describe-stacks \
    --stack-name ec2-auto-shutdown \
    --query 'Stacks[0].Parameters' > backup-parameters.json
```

#### Disaster Recovery
1. Redeploy using saved configuration
2. Restore monitoring setup
3. Verify function operation
4. Update any changed configurations

## Troubleshooting

### Common Issues and Solutions

#### Issue: Function Not Executing
**Symptoms**: No recent invocations in metrics
**Diagnosis**:
```bash
# Check EventBridge rule status
aws events describe-rule --name ec2-auto-shutdown-schedule

# Check rule targets
aws events list-targets-by-rule --rule ec2-auto-shutdown-schedule
```
**Solutions**:
- Verify EventBridge rule is enabled
- Check Lambda function permissions
- Verify rule target configuration

#### Issue: No Instances Being Processed
**Symptoms**: InstancesProcessed metric is 0
**Diagnosis**:
```bash
# Check for tagged instances
aws ec2 describe-instances \
    --filters "Name=tag:AutoShutdown,Values=yes" \
    --query 'Reservations[].Instances[].{InstanceId:InstanceId,State:State.Name}'
```
**Solutions**:
- Verify instances have correct tags
- Check tag key/value configuration
- Confirm instances are in the same region

#### Issue: Permission Errors
**Symptoms**: AccessDenied errors in logs
**Diagnosis**:
```bash
# Check IAM role permissions
aws iam get-role-policy \
    --role-name ec2-auto-shutdown-role \
    --policy-name EC2AutoShutdownPolicy
```
**Solutions**:
- Review IAM role permissions
- Check for resource-based policies
- Verify region restrictions

#### Issue: High Function Duration
**Symptoms**: Duration alarm triggered
**Diagnosis**: Review CloudWatch logs for bottlenecks
**Solutions**:
- Increase function memory allocation
- Optimize retry logic
- Consider pagination for large instance lists

### Log Analysis

#### Useful CloudWatch Insights Queries

**Find all errors:**
```
fields @timestamp, @message
| filter @message like /ERROR/
| sort @timestamp desc
| limit 50
```

**Instance processing summary:**
```
fields @timestamp, @message
| filter @message like /EC2 auto-shutdown process completed/
| stats sum(processedInstances), sum(stoppedInstances) by bin(1d)
```

**Permission errors:**
```
fields @timestamp, @message
| filter @message like /AccessDenied/ or @message like /UnauthorizedOperation/
| sort @timestamp desc
```

## Security Considerations

### IAM Permissions

The function uses the principle of least privilege:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:StopInstances"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestedRegion": "${AWS::Region}"
        }
      }
    },
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricData"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "cloudwatch:namespace": "EC2AutoShutdown"
        }
      }
    }
  ]
}
```

### Security Best Practices

1. **Regular Permission Review**: Audit IAM permissions quarterly
2. **CloudTrail Monitoring**: Monitor API calls for unusual activity
3. **Tag Governance**: Implement tag policies to prevent misuse
4. **Access Control**: Limit who can modify the function or tags
5. **Encryption**: Ensure CloudWatch logs are encrypted

### Compliance Considerations

- **Change Management**: Document all configuration changes
- **Audit Trail**: Maintain logs of all function executions
- **Access Logging**: Monitor who accesses the function
- **Data Retention**: Configure appropriate log retention periods

## Cost Optimization

### Function Optimization

- **Memory Allocation**: Start with 256MB, adjust based on usage
- **Timeout**: Set to 5 minutes, monitor actual duration
- **Reserved Concurrency**: Not typically needed for scheduled execution

### Monitoring Costs

- **CloudWatch Logs**: Configure appropriate retention (30 days default)
- **Custom Metrics**: Monitor metric usage and costs
- **Dashboard**: Consider consolidating dashboards to reduce costs

### Cost Savings Tracking

Track cost savings from automated shutdowns:

```bash
# Calculate potential savings
# (Number of instances) × (Hours saved per day) × (Instance hourly cost)
```

## Support and Maintenance

### Regular Maintenance Tasks

1. **Update Dependencies**: Keep boto3 and other dependencies current
2. **Review Logs**: Regular log analysis for optimization opportunities
3. **Performance Tuning**: Adjust based on actual usage patterns
4. **Documentation Updates**: Keep procedures current

### Getting Help

1. **AWS Support**: Use your AWS support plan for infrastructure issues
2. **CloudWatch Logs**: Primary source for troubleshooting
3. **AWS Documentation**: Reference for service limits and best practices
4. **Community Resources**: AWS forums and Stack Overflow

### Version Control

Maintain version control for:
- Lambda function code
- CloudFormation/SAM templates
- Deployment scripts
- Configuration files
- Documentation

## Appendix

### Useful Commands

```bash
# View function logs
aws logs tail /aws/lambda/ec2-auto-shutdown --follow

# List all alarms
aws cloudwatch describe-alarms --alarm-name-prefix "ec2-auto-shutdown"

# Get function configuration
aws lambda get-function-configuration --function-name ec2-auto-shutdown

# Update environment variables
aws lambda update-function-configuration \
    --function-name ec2-auto-shutdown \
    --environment Variables='{SHUTDOWN_TAG_KEY=AutoShutdown,SHUTDOWN_TAG_VALUE=yes}'
```

### Configuration Templates

See the `parameters.json` file for CloudFormation parameter templates.

### Related Documentation

- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [CloudWatch Monitoring](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/)
- [EC2 Instance Lifecycle](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html)