# EC2 Auto-Shutdown Lambda Deployment Guide

This document provides instructions for deploying the EC2 Auto-Shutdown Lambda function using either AWS SAM or CloudFormation.

## Prerequisites

1. **AWS CLI** - Install and configure with appropriate credentials
2. **AWS SAM CLI** (for SAM deployment) - Install from [AWS documentation](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)
3. **S3 Bucket** - For storing deployment artifacts
4. **IAM Permissions** - Ability to create Lambda functions, IAM roles, and CloudWatch resources

## Deployment Options

### Option 1: AWS SAM (Recommended)

AWS SAM provides a simplified deployment experience with built-in best practices.

#### Quick Deployment

1. Set required environment variables:
```bash
export SAM_DEPLOYMENT_BUCKET=your-deployment-bucket
export AWS_DEFAULT_REGION=us-east-1  # Optional, defaults to us-east-1
```

2. Run the deployment script:
```bash
./deploy.sh
```

#### Manual SAM Deployment

1. Build the application:
```bash
sam build
```

2. Deploy with guided setup (first time):
```bash
sam deploy --guided
```

3. Deploy with parameters:
```bash
sam deploy \
    --stack-name ec2-auto-shutdown \
    --s3-bucket your-deployment-bucket \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides \
        ShutdownTagKey=AutoShutdown \
        ShutdownTagValue=yes \
        ScheduleExpression="cron(0 18 * * MON-FRI *)"
```

### Option 2: CloudFormation

For environments where SAM is not available, use the CloudFormation template.

#### Prepare Deployment Package

1. Create deployment package:
```bash
zip -r ec2-auto-shutdown.zip src/
```

2. Upload to S3:
```bash
aws s3 cp ec2-auto-shutdown.zip s3://your-deployment-bucket/
```

#### Deploy CloudFormation Stack

```bash
aws cloudformation create-stack \
    --stack-name ec2-auto-shutdown \
    --template-body file://cloudformation-template.yaml \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameters \
        ParameterKey=LambdaCodeS3Bucket,ParameterValue=your-deployment-bucket \
        ParameterKey=LambdaCodeS3Key,ParameterValue=ec2-auto-shutdown.zip \
        ParameterKey=ShutdownTagKey,ParameterValue=AutoShutdown \
        ParameterKey=ShutdownTagValue,ParameterValue=yes \
        ParameterKey=ScheduleExpression,ParameterValue="cron(0 18 * * MON-FRI *)"
```

## Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ShutdownTagKey` | `AutoShutdown` | Tag key to identify instances for shutdown |
| `ShutdownTagValue` | `yes` | Tag value to identify instances for shutdown |
| `ScheduleExpression` | `cron(0 18 * * MON-FRI *)` | EventBridge schedule expression |

## Lambda Function Settings

The deployment configures the Lambda function with the following settings:

- **Runtime**: Python 3.9
- **Memory**: 256 MB
- **Timeout**: 5 minutes (300 seconds)
- **Environment Variables**:
  - `SHUTDOWN_TAG_KEY`: Configurable tag key
  - `SHUTDOWN_TAG_VALUE`: Configurable tag value

## IAM Permissions

The Lambda function is granted minimal required permissions:

### EC2 Permissions
- `ec2:DescribeInstances` - To find instances with shutdown tags
- `ec2:StopInstances` - To stop tagged instances

### CloudWatch Logs Permissions
- `logs:CreateLogGroup` - To create log groups
- `logs:CreateLogStream` - To create log streams
- `logs:PutLogEvents` - To write log events

### Security Features
- Regional restriction: EC2 actions are limited to the deployment region
- Resource-specific logging permissions
- No unnecessary permissions granted

## Monitoring and Alarms

The deployment includes CloudWatch monitoring:

### Alarms
- **Error Alarm**: Triggers when the function has errors
- **Duration Alarm**: Triggers when execution time exceeds 80% of timeout

### Logs
- **Log Group**: `/aws/lambda/ec2-auto-shutdown`
- **Retention**: 30 days
- **Format**: Structured JSON logs

## Testing the Deployment

### Manual Test
```bash
aws lambda invoke \
    --function-name ec2-auto-shutdown \
    --payload '{}' \
    response.json && cat response.json
```

### Check Logs
```bash
aws logs describe-log-streams \
    --log-group-name /aws/lambda/ec2-auto-shutdown \
    --order-by LastEventTime \
    --descending \
    --max-items 1
```

## Updating the Function

### SAM Update
```bash
sam build && sam deploy
```

### CloudFormation Update
```bash
# Upload new code
aws s3 cp ec2-auto-shutdown.zip s3://your-deployment-bucket/

# Update stack
aws cloudformation update-stack \
    --stack-name ec2-auto-shutdown \
    --template-body file://cloudformation-template.yaml \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameters file://parameters.json
```

## Cleanup

### Remove SAM Stack
```bash
sam delete --stack-name ec2-auto-shutdown
```

### Remove CloudFormation Stack
```bash
aws cloudformation delete-stack --stack-name ec2-auto-shutdown
```

## Troubleshooting

### Common Issues

1. **Permission Denied**: Ensure the deployment role has sufficient permissions
2. **S3 Bucket Not Found**: Verify the S3 bucket exists and is accessible
3. **Function Timeout**: Increase timeout if processing many instances
4. **No Instances Found**: Verify instances have the correct tags

### Debug Commands

```bash
# Check function configuration
aws lambda get-function --function-name ec2-auto-shutdown

# View recent logs
aws logs filter-log-events \
    --log-group-name /aws/lambda/ec2-auto-shutdown \
    --start-time $(date -d '1 hour ago' +%s)000

# Test with specific event
aws lambda invoke \
    --function-name ec2-auto-shutdown \
    --payload '{"test": true}' \
    --log-type Tail \
    response.json
```