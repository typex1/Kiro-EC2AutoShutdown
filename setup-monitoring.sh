#!/bin/bash

# EC2 Auto-Shutdown Monitoring Setup Script
# This script sets up additional monitoring and alerting for the deployed Lambda function

set -e

# Configuration
STACK_NAME="${STACK_NAME:-ec2-auto-shutdown}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
SNS_TOPIC_NAME="${SNS_TOPIC_NAME:-ec2-auto-shutdown-alerts}"
EMAIL_ADDRESS="${EMAIL_ADDRESS:-}"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}EC2 Auto-Shutdown Monitoring Setup${NC}"
echo "=================================="

# Function to print section headers
print_section() {
    echo -e "\n${BLUE}$1${NC}"
    echo "$(printf '=%.0s' {1..40})"
}

# Check if stack exists
print_section "Checking Stack Status"

if ! aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" &> /dev/null; then
    echo -e "${RED}Error: Stack '$STACK_NAME' not found in region '$REGION'${NC}"
    echo "Please deploy the Lambda function first using deploy.sh or deploy-with-monitoring.sh"
    exit 1
fi

echo -e "${GREEN}Stack '$STACK_NAME' found${NC}"

# Create SNS topic for alerts if email is provided
if [ -n "$EMAIL_ADDRESS" ]; then
    print_section "Setting up SNS Notifications"
    
    # Check if topic already exists
    TOPIC_ARN=$(aws sns list-topics --region "$REGION" --query "Topics[?contains(TopicArn, '$SNS_TOPIC_NAME')].TopicArn" --output text)
    
    if [ -z "$TOPIC_ARN" ]; then
        echo "Creating SNS topic: $SNS_TOPIC_NAME"
        TOPIC_ARN=$(aws sns create-topic --name "$SNS_TOPIC_NAME" --region "$REGION" --query 'TopicArn' --output text)
        echo "Created SNS topic: $TOPIC_ARN"
    else
        echo "Using existing SNS topic: $TOPIC_ARN"
    fi
    
    # Subscribe email to topic
    echo "Subscribing email $EMAIL_ADDRESS to topic"
    aws sns subscribe \
        --topic-arn "$TOPIC_ARN" \
        --protocol email \
        --notification-endpoint "$EMAIL_ADDRESS" \
        --region "$REGION"
    
    echo -e "${YELLOW}Please check your email and confirm the subscription${NC}"
    
    # Configure alarms to use SNS topic
    echo "Configuring alarms to send notifications..."
    
    ALARM_NAMES=$(aws cloudformation describe-stack-resources \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'StackResources[?ResourceType==`AWS::CloudWatch::Alarm`].PhysicalResourceId' \
        --output text)
    
    if [ -n "$ALARM_NAMES" ]; then
        for alarm_name in $ALARM_NAMES; do
            echo "  - Configuring alarm: $alarm_name"
            
            # Get current alarm configuration
            ALARM_CONFIG=$(aws cloudwatch describe-alarms \
                --alarm-names "$alarm_name" \
                --region "$REGION" \
                --query 'MetricAlarms[0]' \
                --output json)
            
            # Update alarm with SNS action
            aws cloudwatch put-metric-alarm \
                --region "$REGION" \
                --alarm-name "$alarm_name" \
                --alarm-description "$(echo "$ALARM_CONFIG" | jq -r '.AlarmDescription')" \
                --actions-enabled \
                --alarm-actions "$TOPIC_ARN" \
                --metric-name "$(echo "$ALARM_CONFIG" | jq -r '.MetricName')" \
                --namespace "$(echo "$ALARM_CONFIG" | jq -r '.Namespace')" \
                --statistic "$(echo "$ALARM_CONFIG" | jq -r '.Statistic')" \
                --dimensions "$(echo "$ALARM_CONFIG" | jq -c '.Dimensions')" \
                --period "$(echo "$ALARM_CONFIG" | jq -r '.Period')" \
                --evaluation-periods "$(echo "$ALARM_CONFIG" | jq -r '.EvaluationPeriods')" \
                --threshold "$(echo "$ALARM_CONFIG" | jq -r '.Threshold')" \
                --comparison-operator "$(echo "$ALARM_CONFIG" | jq -r '.ComparisonOperator')" \
                --treat-missing-data "$(echo "$ALARM_CONFIG" | jq -r '.TreatMissingData')"
        done
        echo -e "${GREEN}All alarms configured with SNS notifications${NC}"
    else
        echo -e "${YELLOW}No alarms found in the stack${NC}"
    fi
fi

# Create custom CloudWatch dashboard
print_section "Creating Enhanced Dashboard"

FUNCTION_NAME=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`EC2AutoShutdownFunctionName`].OutputValue' \
    --output text)

if [ -n "$FUNCTION_NAME" ]; then
    DASHBOARD_NAME="${STACK_NAME}-Enhanced-Dashboard"
    
    # Create enhanced dashboard JSON
    cat > /tmp/dashboard.json << EOF
{
  "widgets": [
    {
      "type": "metric",
      "x": 0,
      "y": 0,
      "width": 12,
      "height": 6,
      "properties": {
        "metrics": [
          [ "EC2AutoShutdown", "InstancesProcessed", "FunctionName", "ec2-auto-shutdown" ],
          [ ".", "InstancesStopped", ".", "." ],
          [ ".", "InstancesSkipped", ".", "." ]
        ],
        "view": "timeSeries",
        "stacked": false,
        "region": "$REGION",
        "title": "Instance Processing Metrics",
        "period": 300,
        "stat": "Sum",
        "yAxis": {
          "left": {
            "min": 0
          }
        }
      }
    },
    {
      "type": "metric",
      "x": 12,
      "y": 0,
      "width": 12,
      "height": 6,
      "properties": {
        "metrics": [
          [ "AWS/Lambda", "Duration", "FunctionName", "$FUNCTION_NAME" ],
          [ ".", "Invocations", ".", "." ],
          [ ".", "Errors", ".", "." ]
        ],
        "view": "timeSeries",
        "stacked": false,
        "region": "$REGION",
        "title": "Lambda Function Performance",
        "period": 300
      }
    },
    {
      "type": "metric",
      "x": 0,
      "y": 6,
      "width": 8,
      "height": 6,
      "properties": {
        "metrics": [
          [ "EC2AutoShutdown", "ErrorCount", "FunctionName", "ec2-auto-shutdown" ]
        ],
        "view": "timeSeries",
        "stacked": false,
        "region": "$REGION",
        "title": "Error Count",
        "period": 300,
        "stat": "Sum",
        "yAxis": {
          "left": {
            "min": 0
          }
        }
      }
    },
    {
      "type": "metric",
      "x": 8,
      "y": 6,
      "width": 8,
      "height": 6,
      "properties": {
        "metrics": [
          [ "AWS/Lambda", "ConcurrentExecutions", "FunctionName", "$FUNCTION_NAME" ],
          [ ".", "Throttles", ".", "." ]
        ],
        "view": "timeSeries",
        "stacked": false,
        "region": "$REGION",
        "title": "Concurrency and Throttles",
        "period": 300
      }
    },
    {
      "type": "metric",
      "x": 16,
      "y": 6,
      "width": 8,
      "height": 6,
      "properties": {
        "metrics": [
          [ "EC2AutoShutdown", "InstancesProcessed", "FunctionName", "ec2-auto-shutdown", { "stat": "Sum" } ],
          [ ".", "InstancesStopped", ".", ".", { "stat": "Sum" } ]
        ],
        "view": "singleValue",
        "region": "$REGION",
        "title": "Daily Totals",
        "period": 86400,
        "stat": "Sum"
      }
    },
    {
      "type": "log",
      "x": 0,
      "y": 12,
      "width": 12,
      "height": 6,
      "properties": {
        "query": "SOURCE '/aws/lambda/$FUNCTION_NAME'\\n| fields @timestamp, @message\\n| filter @message like /ERROR/\\n| sort @timestamp desc\\n| limit 20",
        "region": "$REGION",
        "title": "Recent Errors",
        "view": "table"
      }
    },
    {
      "type": "log",
      "x": 12,
      "y": 12,
      "width": 12,
      "height": 6,
      "properties": {
        "query": "SOURCE '/aws/lambda/$FUNCTION_NAME'\\n| fields @timestamp, @message\\n| filter @message like /stopped instance/\\n| sort @timestamp desc\\n| limit 10",
        "region": "$REGION",
        "title": "Recent Instance Shutdowns",
        "view": "table"
      }
    }
  ]
}
EOF

    # Create the dashboard
    aws cloudwatch put-dashboard \
        --dashboard-name "$DASHBOARD_NAME" \
        --dashboard-body file:///tmp/dashboard.json \
        --region "$REGION"
    
    echo -e "${GREEN}Enhanced dashboard created: $DASHBOARD_NAME${NC}"
    rm -f /tmp/dashboard.json
fi

# Create metric filters for custom log-based metrics
print_section "Setting up Log-based Metrics"

LOG_GROUP_NAME="/aws/lambda/$FUNCTION_NAME"

# Metric filter for successful shutdowns
aws logs put-metric-filter \
    --log-group-name "$LOG_GROUP_NAME" \
    --filter-name "SuccessfulShutdowns" \
    --filter-pattern "[timestamp, request_id, level=\"INFO\", message=\"Successfully stopped instance*\"]" \
    --metric-transformations \
        metricName=SuccessfulShutdowns,metricNamespace=EC2AutoShutdown/Detailed,metricValue=1 \
    --region "$REGION" || echo "Metric filter may already exist"

# Metric filter for permission errors
aws logs put-metric-filter \
    --log-group-name "$LOG_GROUP_NAME" \
    --filter-name "PermissionErrors" \
    --filter-pattern "[timestamp, request_id, level=\"ERROR\", message=\"*permission*\"]" \
    --metric-transformations \
        metricName=PermissionErrors,metricNamespace=EC2AutoShutdown/Detailed,metricValue=1 \
    --region "$REGION" || echo "Metric filter may already exist"

# Metric filter for API throttling
aws logs put-metric-filter \
    --log-group-name "$LOG_GROUP_NAME" \
    --filter-name "APIThrottling" \
    --filter-pattern "[timestamp, request_id, level=\"WARN\", message=\"*throttl*\"]" \
    --metric-transformations \
        metricName=APIThrottling,metricNamespace=EC2AutoShutdown/Detailed,metricValue=1 \
    --region "$REGION" || echo "Metric filter may already exist"

echo -e "${GREEN}Log-based metric filters created${NC}"

# Create operational runbook
print_section "Creating Operational Documentation"

cat > MONITORING_RUNBOOK.md << 'EOF'
# EC2 Auto-Shutdown Monitoring Runbook

## Overview
This document provides operational guidance for monitoring and troubleshooting the EC2 Auto-Shutdown Lambda function.

## Key Metrics to Monitor

### Custom Metrics (Namespace: EC2AutoShutdown)
- **InstancesProcessed**: Total number of instances evaluated
- **InstancesStopped**: Number of instances successfully stopped
- **InstancesSkipped**: Number of instances already stopped
- **ErrorCount**: Number of errors encountered

### AWS Lambda Metrics
- **Duration**: Function execution time
- **Errors**: Function errors
- **Throttles**: Function throttling events
- **Invocations**: Number of function invocations

## Alarms and Thresholds

### Critical Alarms
1. **Function Errors**: Triggers when any Lambda errors occur
2. **High Duration**: Triggers when function runs longer than 4 minutes
3. **No Instances Processed**: Triggers when no instances are processed in 24 hours
4. **High Error Rate**: Triggers when more than 5 errors occur in 1 hour

### Warning Alarms
1. **Function Throttles**: Indicates concurrency limits reached
2. **Permission Errors**: Indicates IAM permission issues

## Troubleshooting Guide

### Common Issues

#### 1. No Instances Being Processed
**Symptoms**: InstancesProcessed metric is 0
**Possible Causes**:
- No EC2 instances have the required tag
- Incorrect tag key/value configuration
- Function not being invoked

**Resolution**:
1. Check EC2 instances for correct tags
2. Verify environment variables in Lambda function
3. Check EventBridge rule is enabled

#### 2. Permission Errors
**Symptoms**: Errors in logs mentioning "AccessDenied" or "UnauthorizedOperation"
**Possible Causes**:
- IAM role missing required permissions
- Resource-based policies blocking access

**Resolution**:
1. Review IAM role permissions
2. Check for resource-based policies on EC2 instances
3. Verify region-specific permissions

#### 3. High Duration
**Symptoms**: Function taking longer than expected
**Possible Causes**:
- Large number of instances to process
- API throttling causing retries
- Network issues

**Resolution**:
1. Check number of instances being processed
2. Review logs for throttling messages
3. Consider increasing function timeout or memory

#### 4. Function Throttling
**Symptoms**: Throttles metric > 0
**Possible Causes**:
- Concurrent executions exceeding limits
- Multiple invocations running simultaneously

**Resolution**:
1. Check EventBridge rule frequency
2. Review Lambda concurrency settings
3. Consider reserved concurrency if needed

## Log Analysis

### Key Log Messages to Monitor
- `Starting EC2 auto-shutdown process`: Function start
- `Successfully stopped instance`: Successful shutdown
- `Failed to stop instance`: Shutdown failure
- `No instances found`: No tagged instances
- `ERROR`: Any error conditions

### Useful CloudWatch Insights Queries

#### Find all errors in the last 24 hours:
```
fields @timestamp, @message
| filter @message like /ERROR/
| sort @timestamp desc
```

#### Count instances processed per day:
```
fields @timestamp, @message
| filter @message like /EC2 auto-shutdown process completed/
| stats sum(processedInstances) by bin(5m)
```

#### Find permission errors:
```
fields @timestamp, @message
| filter @message like /permission/ or @message like /AccessDenied/
| sort @timestamp desc
```

## Maintenance Tasks

### Daily
- Review dashboard for any anomalies
- Check alarm status
- Verify expected number of instances processed

### Weekly
- Review error trends
- Check function performance metrics
- Validate tag compliance on EC2 instances

### Monthly
- Review and update alarm thresholds if needed
- Analyze cost savings from automated shutdowns
- Update documentation if processes change

## Emergency Procedures

### Function Completely Failing
1. Check CloudWatch logs for error details
2. Verify IAM permissions
3. Test function manually with empty payload
4. If needed, disable EventBridge rule to stop automatic execution

### Too Many Instances Being Stopped
1. Immediately disable EventBridge rule
2. Review EC2 instance tags for accuracy
3. Check for tag propagation issues
4. Re-enable rule after verification

## Contact Information
- AWS Support: [Your support plan details]
- Team Escalation: [Your team contact information]
- Documentation: [Link to additional documentation]

## Dashboard Links
- Main Dashboard: https://console.aws.amazon.com/cloudwatch/home#dashboards:
- Enhanced Dashboard: [Link to enhanced dashboard]
- CloudWatch Logs: https://console.aws.amazon.com/cloudwatch/home#logsV2:log-groups
EOF

echo -e "${GREEN}Monitoring runbook created: MONITORING_RUNBOOK.md${NC}"

# Display summary
print_section "Monitoring Setup Complete"

echo -e "${GREEN}Monitoring setup completed successfully!${NC}"
echo ""
echo "Summary of configured monitoring:"
echo "✓ CloudWatch alarms for function health"
echo "✓ Custom metrics for instance processing"
echo "✓ Enhanced CloudWatch dashboard"
echo "✓ Log-based metric filters"
echo "✓ Operational runbook created"

if [ -n "$EMAIL_ADDRESS" ]; then
    echo "✓ SNS notifications configured for: $EMAIL_ADDRESS"
    echo "  ${YELLOW}Please check your email and confirm the subscription${NC}"
fi

echo ""
echo "Access your monitoring:"
echo "• Dashboard: https://${REGION}.console.aws.amazon.com/cloudwatch/home?region=${REGION}#dashboards:name=${STACK_NAME}-Enhanced-Dashboard"
echo "• Alarms: https://${REGION}.console.aws.amazon.com/cloudwatch/home?region=${REGION}#alarmsV2:"
echo "• Logs: https://${REGION}.console.aws.amazon.com/cloudwatch/home?region=${REGION}#logsV2:log-groups/log-group/\$252Faws\$252Flambda\$252F${FUNCTION_NAME}"
echo "• Metrics: https://${REGION}.console.aws.amazon.com/cloudwatch/home?region=${REGION}#metricsV2:graph=~();namespace=EC2AutoShutdown"

echo ""
echo "Next steps:"
echo "1. Review the monitoring runbook: MONITORING_RUNBOOK.md"
echo "2. Test the alarms by triggering error conditions"
echo "3. Customize alarm thresholds based on your environment"
echo "4. Set up additional integrations (Slack, PagerDuty, etc.) if needed"