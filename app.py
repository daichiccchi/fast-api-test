from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
import requests
import os
import logging
from typing import Optional
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Cross-Account AWS Access Test API")


class APIGatewayRequest(BaseModel):
    api_gateway_url: str
    method: str = "GET"
    body: Optional[str] = None
    region: str = "ap-northeast-1"
    assume_role_arn: Optional[str] = None


class S3UploadRequest(BaseModel):
    bucket_name: str
    object_key: str
    region: str = "ap-northeast-1"
    assume_role_arn: Optional[str] = None


def get_credentials(assume_role_arn: Optional[str] = None):
    """Get AWS credentials, optionally assuming a role."""
    if assume_role_arn:
        sts = boto3.client('sts')
        try:
            assumed_role = sts.assume_role(
                RoleArn=assume_role_arn,
                RoleSessionName=f"cross-account-test-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )
            creds = assumed_role['Credentials']
            return Credentials(
                access_key=creds['AccessKeyId'],
                secret_key=creds['SecretAccessKey'],
                token=creds['SessionToken']
            )
        except Exception as e:
            logger.error(f"Failed to assume role: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to assume role: {str(e)}")
    else:
        session = boto3.Session()
        credentials = session.get_credentials()
        if not credentials:
            raise HTTPException(status_code=500, detail="No AWS credentials found")
        return credentials


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "Cross-Account AWS Access Test API is running"}


@app.post("/apigw")
async def call_api_gateway(request: APIGatewayRequest):
    """
    Call an API Gateway endpoint with SigV4 authentication.
    """
    try:
        logger.info(f"Calling API Gateway: {request.api_gateway_url}")

        # Get credentials (optionally assume role)
        credentials = get_credentials(request.assume_role_arn)

        # Parse the URL to get the host
        from urllib.parse import urlparse
        parsed_url = urlparse(request.api_gateway_url)
        host = parsed_url.netloc
        path = parsed_url.path or '/'

        # Prepare the request
        headers = {
            'Host': host,
            'Content-Type': 'application/json' if request.body else 'text/plain'
        }

        # Create AWS request for signing
        aws_request = AWSRequest(
            method=request.method,
            url=request.api_gateway_url,
            data=request.body,
            headers=headers
        )

        # Sign the request
        SigV4Auth(credentials, 'execute-api', request.region).add_auth(aws_request)

        # Make the actual request
        response = requests.request(
            method=request.method,
            url=request.api_gateway_url,
            headers=dict(aws_request.headers),
            data=request.body,
            timeout=30
        )

        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")

        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.text,
            "request_headers_sent": dict(aws_request.headers)
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "Request failed",
                "detail": str(e),
                "request_headers": dict(aws_request.headers) if 'aws_request' in locals() else None
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/bucket")
async def upload_to_s3(
    request: S3UploadRequest,
    file: UploadFile = File(...)
):
    """
    Upload a file to S3 bucket.
    """
    try:
        logger.info(f"Uploading to S3: {request.bucket_name}/{request.object_key}")

        # Get credentials (optionally assume role)
        if request.assume_role_arn:
            sts = boto3.client('sts')
            assumed_role = sts.assume_role(
                RoleArn=request.assume_role_arn,
                RoleSessionName=f"s3-upload-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )
            s3_client = boto3.client(
                's3',
                region_name=request.region,
                aws_access_key_id=assumed_role['Credentials']['AccessKeyId'],
                aws_secret_access_key=assumed_role['Credentials']['SecretAccessKey'],
                aws_session_token=assumed_role['Credentials']['SessionToken']
            )
        else:
            s3_client = boto3.client('s3', region_name=request.region)

        # Read file content
        file_content = await file.read()

        # Upload to S3
        response = s3_client.put_object(
            Bucket=request.bucket_name,
            Key=request.object_key,
            Body=file_content,
            ContentType=file.content_type or 'application/octet-stream'
        )

        logger.info(f"Upload successful: {response}")

        return {
            "message": "File uploaded successfully",
            "bucket": request.bucket_name,
            "key": request.object_key,
            "etag": response.get('ETag'),
            "version_id": response.get('VersionId')
        }

    except Exception as e:
        logger.error(f"S3 upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/test-credentials")
async def test_credentials():
    """
    Test if AWS credentials are properly configured.
    """
    try:
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()
        return {
            "account": identity['Account'],
            "user_arn": identity['Arn'],
            "user_id": identity['UserId']
        }
    except Exception as e:
        logger.error(f"Credentials test failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)