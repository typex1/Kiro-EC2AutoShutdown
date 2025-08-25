#!/bin/bash

# EC2 Auto-Shutdown Lambda Deployment Script with Monitoring Setup
# This script deploys the Lambda function and sets up comprehensive monitoring

set -e

# Configuration
STACK_NAME="ec2-auto-shutdown"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
S3_BUCKET="${SAM_DEPLOYMENT_BUCKET}"
SHUTDOWN_TAG_KEY="${SHUTDOWN_TAG_KEY:-AutoShutdown}"
SHUTDOWN_TAG_VALUE="${SHUTDOWN_TAG_VALUE:-yes}"
SCHEDULE_EXPRESSION="${SCHEDULE_EXPRESSION:-'cron(0 18 * * MON-FRI *)'}"
SNS_TOPIC_ARN="${SNS_TOPIC_ARN:-}"
DEPLOYMENT_TYPE="${DEPLOYMENT_TYPE:-sam}"  # sam or cloudformation

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}EC2 Auto-Shutdown Lambda Deployment with Monitoring${NC}"
echo "=================================================="

# Function to print section headers
print_section() {
    echo -e "\n${BLUE}$1${NC}"
    echo "$(printf '=%.0s' {1..50})"
}

# Function to check command availability
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}Error: $1 is not installed${NC}"
        echo "$2"
        exit 1
    fi
}

# Check prerequisites
print_section "Checking Prerequisites"

check_command "aws" "Please install AWS CLI: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"

if [ "$DEPLOYMENT_TYPE" = "sam" ]; then
    check_command "sam" "Please install SAM CLI: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html"
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}Error: AWS credentials not configured${NC}"
    echo "Please configure AWS credentials using 'aws configure' or environment variables"
    exit 1
fi

# Check if S3 bucket is provided for SAM deployment
if [ "$DEPLOYMENT_TYPE" = "sam" ] && [ -z "$S3_BUCKET" ]; then
    echo -e "${RED}Error: SAM_DEPLOYMENT_BUCKET environment variable is required for SAM deployment${NC}"
    echo "Please set SAM_DEPLOYMENT_BUCKET to an existing S3 bucket for deployment artifacts"
    exit 1
fi

echo -e "${GREEN}Prerequisites check passed${NC}"

# Display configuration
print_section "Deployment Configuration"
echo "Stack Name: $STACK_NAME"
echo "Region: $REGION"
echo "Deployment Type: $DEPLOYMENT_TYPE"
if [ "$DEPLOYMENT_TYPE" = "sam" ]; then
    echo "S3 Bucket: $S3_BUCKET"
fi
echo "Shutdown Tag Key: $SHUTDOWN_TAG_KEY"
echo "Shutdown Tag Value: $SHUTDOWN_TAG_VALUE"
echo "Schedule: $SCHEDULE_EXPRESSION"
if [ -n "$SNS_TOPIC_ARN" ]; then
    echo "SNS Topic ARN: $SNS_TOPIC_ARN"
fi

# Run tests before deployment
print_section "Running Tests"
if [ -f "pytest.ini" ] && command -v pytest &> /dev/null; then
    echo "Running unit tests..."
    pytest tests/ -v --tb=short
    echo -e "${GREEN}Tests passed${NC}"
else
    echo -e "${YELLOW}Pytest not available or configured, skipping tests${NC}"
fi

# Package and deploy based on deployment type
if [ "$DEPLOYMENT_TYPE" = "sam" ]; then
    print_section "Building and Deploying with SAM"
    
    # Build the application
    echo "Building SAM application..."
    sam build
    
    # Deploy the application
    echo "Deploying SAM application..."
    sam deploy \
        --stack-name "$STACK_NAME" \
        --s3-bucket "$S3_BUCKET" \
        --region "$REGION" \
        --capabilities CAPABILITY_IAM \
        --parameter-overrides \
            ShutdownTagKey="$SHUTDOWN_TAG_KEY" \
            ShutdownTagValue="$SHUTDOWN_TAG_VALUE" \
            ScheduleExpression="$SCHEDULE_EXPRESSION" \
        --confirm-changeset

else
    print_section "Deploying with CloudFormation"
    
    # Package Lambda code
    echo "Packaging Lambda code..."
    zip -r ec2-auto-shutdown.zip src/ -x "**/__pycache__/*" "**/*.pyc"
    
    # Upload to S3 if bucket is provided
    if [ -n "$S3_BUCKET" ]; then
        echo "Uploading Lambda package to S3..."
        aws s3 cp ec2-auto-shutdown.zip "s3://$S3_BUCKET/ec2-auto-shutdown.zip" --region "$REGION"
        S3_KEY="ec2-auto-shutdown.zip"
    else
        echo -e "${YELLOW}No S3 bucket provided, using local file for deployment${NC}"
        # Create a temporary S3 bucket for deployment
        TEMP_BUCKET="ec2-auto-shutdown-deploy-$(date +%s)-$(openssl rand -hex 4)"
        echo "Creating temporary S3 bucket: $TEMP_BUCKET"
        aws s3 mb "s3://$TEMP_BUCKET" --region "$REGION"
        aws s3 cp ec2-auto-shutdown.zip "s3://$TEMP_BUCKET/ec2-auto-shutdown.zip" --region "$REGION"
        S3_BUCKET="$TEMP_BUCKET"
        S3_KEY="ec2-auto-shutdown.zip"
    fi
    
    # Deploy CloudFormation stack
    echo "Deploying CloudFormation stack..."
    aws cloudformation deploy \
        --template-file cloudformation-template.yaml \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --capabilities CAPABILITY_NAMED_IAM \
        --parameter-overrides \
            ShutdownTagKey="$SHUTDOWN_TAG_KEY" \
            ShutdownTagValue="$SHUTDOWN_TAG_VALUE" \
            ScheduleExpression="$SCHEDULE_EXPRESSION" \
            LambdaCodeS3Bucket="$S3_BUCKET" \
            LambdaCodeS3Key="$S3_KEY"
    
    # Clean up temporary bucket if created
    if [[ "$S3_BUCKET" == ec2-auto-shutdown-deploy-* ]]; then
        echo "Cleaning up temporary S3 bucket..."
        aws s3 rm "s3://$S3_BUCKET" --recursive --region "$REGION"
        aws s3 rb "s3://$S3_BUCKET" --region "$REGION"
    fi
    
    # Clean up local zip file
    rm -f ec2-auto-shutdown.zip
fi

print_section "Deployment Completed Successfully"

# Display stack outputs
echo "Getting stack outputs..."
aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs' \
    --output table

# Set up SNS notifications for alarms if topic ARN is provided
if [ -n "$SNS_TOPIC_ARN" ]; then
    print_section "Configuring Alarm Notifications"
    
    # Get alarm names from the stack
    ALARM_NAMES=$(aws cloudformation describe-stack-resources \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'StackResources[?ResourceType==`AWS::CloudWatch::Alarm`].PhysicalResourceId' \
        --output text)
    
    if [ -n "$ALARM_NAMES" ]; then
        echo "Configuring SNS notifications for alarms..."
        for alarm_name in $ALARM_NAMES; do
            echo "  - Configuring alarm: $alarm_name"
            aws cloudwatch put-metric-alarm \
                --alarm-name "$alarm_name" \
                --alarm-actions "$SNS_TOPIC_ARN" \
                --region "$REGION" \
                --cli-input-json "$(aws cloudwatch describe-alarms --alarm-names "$alarm_name" --region "$REGION" --query 'MetricAlarms[0]' --output json | jq 'del(.AlarmArn, .AlarmConfigurationUpdatedTimestamp, .StateValue, .StateReason, .StateReasonData, .StateUpdatedTimestamp)')"
        done
        echo -e "${GREEN}SNS notifications configured for all alarms${NC}"
    else
        echo -e "${YELLOW}No alarms found in the stack${NC}"
    fi
fi

# Test the deployment
print_section "Testing Deployment"

FUNCTION_NAME=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`EC2AutoShutdownFunctionName`].OutputValue' \
    --output text)

if [ -n "$FUNCTION_NAME" ]; then
    echo "Testing Lambda function invocation..."
    TEST_RESULT=$(aws lambda invoke \
        --function-name "$FUNCTION_NAME" \
        --region "$REGION" \
        --payload '{}' \
        --cli-binary-format raw-in-base64-out \
        /tmp/lambda-test-output.json)
    
    echo "Function invocation result:"
    echo "$TEST_RESULT"
    
    echo "Function response:"
    cat /tmp/lambda-test-output.json | jq .
    rm -f /tmp/lambda-test-output.json
    
    echo -e "${GREEN}Function test completed${NC}"
else
    echo -e "${YELLOW}Could not find function name in stack outputs${NC}"
fi

# Display monitoring information
print_section "Monitoring Information"

echo "CloudWatch Dashboard:"
echo "https://${REGION}.console.aws.amazon.com/cloudwatch/home?region=${REGION}#dashboards:name=${STACK_NAME}-EC2AutoShutdown-Dashboard"

echo ""
echo "CloudWatch Alarms:"
if [ -n "$ALARM_NAMES" ]; then
    for alarm_name in $ALARM_NAMES; do
        echo "  - $alarm_name"
    done
else
    echo "  - Check the CloudWatch console for created alarms"
fi

echo ""
echo "CloudWatch Logs:"
echo "https://${REGION}.console.aws.amazon.com/cloudwatch/home?region=${REGION}#logsV2:log-groups/log-group/\$252Faws\$252Flambda\$252Fec2-auto-shutdown"

echo ""
echo "Custom Metrics Namespace: EC2AutoShutdown"
echo "Available Metrics:"
echo "  - InstancesProcessed: Number of instances processed"
echo "  - InstancesStopped: Number of instances stopped"
echo "  - InstancesSkipped: Number of instances skipped"
echo "  - ErrorCount: Number of errors encountered"

print_section "Deployment Script Completed"
echo -e "${GREEN}EC2 Auto-Shutdown Lambda function deployed successfully with monitoring!${NC}"
echo ""
echo "Next steps:"
echo "1. Review the CloudWatch dashboard for monitoring"
echo "2. Configure SNS notifications for alarms if not already done"
echo "3. Test the function with actual EC2 instances tagged for shutdown"
echo "4. Monitor the logs and metrics for the first few executions"