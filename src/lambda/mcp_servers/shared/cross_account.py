"""Cross-account AWS session management for MCP Lambda functions.

Used when deploying to data collection account with access to
Cost Explorer and CUR data in the management/payer account.
"""

import os
from functools import lru_cache

import boto3


@lru_cache(maxsize=1)
def get_cross_account_session():
    """Get boto3 session with assumed role credentials (cached for Lambda reuse).

    Returns:
        boto3.Session with assumed role credentials, or None if not configured.
    """
    role_arn = os.environ.get("CROSS_ACCOUNT_ROLE_ARN", "")
    external_id = os.environ.get("CROSS_ACCOUNT_EXTERNAL_ID", "")

    if not role_arn:
        return None

    sts = boto3.client("sts")
    params = {
        "RoleArn": role_arn,
        "RoleSessionName": "mcp-gateway-cross-account",
        "DurationSeconds": 3600,
    }
    if external_id:
        params["ExternalId"] = external_id

    creds = sts.assume_role(**params)["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )


def get_aws_client(service_name, region_name=None, **kwargs):
    """Get boto3 client - uses cross-account role if configured, else execution role.

    Args:
        service_name: AWS service name (e.g., 'ce', 'athena', 's3')
        region_name: Optional AWS region
        **kwargs: Additional arguments passed to boto3.client()

    Returns:
        boto3 client for the specified service
    """
    session = get_cross_account_session()
    client_kwargs = {"region_name": region_name} if region_name else {}
    client_kwargs.update(kwargs)

    if session:
        return session.client(service_name, **client_kwargs)
    return boto3.client(service_name, **client_kwargs)
