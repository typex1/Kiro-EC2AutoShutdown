#!/bin/bash

# EC2 Auto-Shutdown Lambda Deployment Script
# This script deploys the Lambda function using AWS SAM

set -e

# Configuration
STACK_NAME="ec2-auto-shutdown"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
S3_BUCKET="${SAM_DEPLOYMENT_BUCKET}"
SHUTDOWN_TAG_KEY="${SHUTDOWN_TAG_KEY:-AutoShutdown}"
SHUTDOWN_TAG_VALUE="${SHUTDOWN_TAG_VALUE:-yes}"
SCHEDULE_EXPRESSION="${SCHEDULE_EXPRESSION:-'cron(42 16 ? * MON-FRI *)'}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}EC2 Auto-Shutdown Lambda Deployment${NC}"
echo "=================================="

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v sam &> /dev/null; then
    echo -e "${RED}Error: AWS SAM CLI is not installed${NC}"
    echo "Please install SAM CLI: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html"
    exit 1
fi

if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed${NC}"
    echo "Please install AWS CLI: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}Error: AWS credentials not configured${NC}"
    echo "Please configure AWS credentials using 'aws configure' or environment variables"
    exit 1
fi

# Check if S3 bucket is provided
if [ -z "$S3_BUCKET" ]; then
    echo -e "${RED}Error: SAM_DEPLOYMENT_BUCKET environment variable is required${NC}"
    echo "Please set SAM_DEPLOYMENT_BUCKET to an existing S3 bucket for deployment artifacts"
    exit 1
fi

echo -e "${GREEN}Prerequisites check passed${NC}"

# Display configuration
echo -e "${YELLOW}Deployment Configuration:${NC}"
echo "Stack Name: $STACK_NAME"
echo "Region: $REGION"
echo "S3 Bucket: $S3_BUCKET"
echo "Shutdown Tag Key: $SHUTDOWN_TAG_KEY"
echo "Shutdown Tag Value: $SHUTDOWN_TAG_VALUE"
echo "Schedule: $SCHEDULE_EXPRESSION"
echo ""

# Build the application
echo -e "${YELLOW}Building SAM application...${NC}"
sam build

# Deploy the application
echo -e "${YELLOW}Deploying SAM application...${NC}"
sam deploy \
    --stack-name "$STACK_NAME" \
    --s3-bucket "$S3_BUCKET" \
    --region "$REGION" \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides \
        ShutdownTagKey="$SHUTDOWN_TAG_KEY" \
        ShutdownTagValue="$SHUTDOWN_TAG_VALUE" \
        ScheduleExpression="$SCHEDULE_EXPRESSION" \
    --no-confirm-changeset

echo -e "${GREEN}Deployment completed successfully!${NC}"

# Display outputs
echo -e "${YELLOW}Getting stack outputs...${NC}"
aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs' \
    --output table

echo -e "${GREEN}Deployment script completed${NC}"