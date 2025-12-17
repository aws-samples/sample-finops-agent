#!/usr/bin/env python3
"""
Update Gateway target tool schemas.

The Terraform AWS provider only supports 1 tool_schema per Lambda target,
but the AWS API supports multiple. This script updates the targets with
the full tool schema definitions after Terraform creates them.

Usage:
    python3 scripts/update_tool_schemas.py
"""

import boto3
import json
import os

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_PROFILE = os.environ.get("AWS_PROFILE", "default")
GATEWAY_ID = os.environ.get("GATEWAY_ID", "aiops-mcp-gateway-gateway-nniwnghwtn")
ACCOUNT_ID = os.environ.get("AWS_ACCOUNT_ID", "028969191743")

# Tool schemas for each target
TOOL_SCHEMAS = {
    "aiops-mcp-gateway-lambda-target": {
        "lambda_arn": f"arn:aws:lambda:{AWS_REGION}:{ACCOUNT_ID}:function:aiops-mcp-gateway-proxy",
        "description": "AWS API MCP server proxy (call_aws, suggest_aws_commands)",
        "tools": [
            {
                "name": "call_aws",
                "description": "Execute any AWS CLI command. Provide the full CLI command string (e.g., 'aws s3 ls', 'aws ec2 describe-instances'). Returns the command output.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "cli_command": {
                            "type": "string",
                            "description": "The full AWS CLI command to execute (e.g., 'aws s3 ls', 'aws ec2 describe-instances --region us-west-2')"
                        }
                    },
                    "required": ["cli_command"]
                }
            },
            {
                "name": "suggest_aws_commands",
                "description": "Get AWS CLI command suggestions based on a natural language query. Useful for discovering the right CLI command to use.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language description of what you want to do (e.g., 'list all S3 buckets', 'get EC2 instance details')"
                        }
                    },
                    "required": ["query"]
                }
            }
        ]
    },
    "test-mcp": {
        "lambda_arn": f"arn:aws:lambda:{AWS_REGION}:{ACCOUNT_ID}:function:aiops-mcp-gateway-test-mcp",
        "description": "Simple test MCP tools (hello, echo)",
        "tools": [
            {
                "name": "hello",
                "description": "Returns a friendly greeting message. Use this to test the Gateway integration.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name to greet (optional, defaults to 'World')"
                        }
                    }
                }
            },
            {
                "name": "echo",
                "description": "Echoes back the provided message. Use this to verify tool parameters are passed correctly.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Message to echo back"
                        }
                    },
                    "required": ["message"]
                }
            }
        ]
    },
    "cost-explorer-mcp": {
        "lambda_arn": f"arn:aws:lambda:{AWS_REGION}:{ACCOUNT_ID}:function:aiops-mcp-gateway-cost-explorer-mcp",
        "description": "AWS Cost Explorer MCP tools (get_today_date, get_dimension_values, get_tag_values, get_cost_and_usage, get_cost_and_usage_comparisons, get_cost_forecast)",
        "tools": [
            {
                "name": "get_today_date",
                "description": "Get the current date for determining relevant time periods. Returns today's date, first of month, and last month's date range.",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_dimension_values",
                "description": "Get available values for a specific dimension (e.g., SERVICE, REGION, LINKED_ACCOUNT, USAGE_TYPE). Use this to discover what services or regions have costs.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "dimension": {
                            "type": "string",
                            "description": "Dimension name: SERVICE, REGION, LINKED_ACCOUNT, USAGE_TYPE, INSTANCE_TYPE, etc."
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Start date (YYYY-MM-DD format)"
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date (YYYY-MM-DD format)"
                        }
                    }
                }
            },
            {
                "name": "get_tag_values",
                "description": "Get available values for a specific cost allocation tag key. Use this to discover tag values for filtering costs.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tag_key": {
                            "type": "string",
                            "description": "The tag key to get values for (e.g., 'Environment', 'Project')"
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Start date (YYYY-MM-DD format)"
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date (YYYY-MM-DD format)"
                        }
                    },
                    "required": ["tag_key"]
                }
            },
            {
                "name": "get_cost_and_usage",
                "description": "Retrieve AWS cost and usage data with filtering and grouping options. Use this to analyze costs by service, region, or other dimensions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "start_date": {
                            "type": "string",
                            "description": "Start date (YYYY-MM-DD format). Defaults to first of current month."
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date (YYYY-MM-DD format). Defaults to today."
                        },
                        "granularity": {
                            "type": "string",
                            "description": "Time granularity: DAILY, MONTHLY, or HOURLY"
                        },
                        "metrics": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Cost metrics to retrieve: UnblendedCost, BlendedCost, AmortizedCost, UsageQuantity, etc."
                        },
                        "group_by": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Dimensions to group by: SERVICE, REGION, LINKED_ACCOUNT, USAGE_TYPE, etc."
                        },
                        "filter": {
                            "type": "object",
                            "description": "Cost Explorer filter expression (Dimensions, Tags, CostCategories)"
                        }
                    }
                }
            },
            {
                "name": "get_cost_and_usage_comparisons",
                "description": "Compare costs between two time periods to identify changes and trends. Shows which services increased or decreased in cost.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "current_start": {
                            "type": "string",
                            "description": "Current period start date (YYYY-MM-DD)"
                        },
                        "current_end": {
                            "type": "string",
                            "description": "Current period end date (YYYY-MM-DD)"
                        },
                        "previous_start": {
                            "type": "string",
                            "description": "Previous period start date (YYYY-MM-DD)"
                        },
                        "previous_end": {
                            "type": "string",
                            "description": "Previous period end date (YYYY-MM-DD)"
                        },
                        "granularity": {
                            "type": "string",
                            "description": "Time granularity: DAILY or MONTHLY"
                        },
                        "metrics": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Cost metrics to compare"
                        },
                        "group_by": {
                            "type": "string",
                            "description": "Dimension to group by: SERVICE, REGION, LINKED_ACCOUNT, etc."
                        }
                    }
                }
            },
            {
                "name": "get_cost_forecast",
                "description": "Generate cost forecasts based on historical usage patterns. Predicts future costs with confidence intervals.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "start_date": {
                            "type": "string",
                            "description": "Forecast start date (YYYY-MM-DD). Must be in the future."
                        },
                        "end_date": {
                            "type": "string",
                            "description": "Forecast end date (YYYY-MM-DD)"
                        },
                        "granularity": {
                            "type": "string",
                            "description": "Forecast granularity: DAILY or MONTHLY"
                        },
                        "metric": {
                            "type": "string",
                            "description": "Metric to forecast: UNBLENDED_COST, BLENDED_COST, AMORTIZED_COST, etc."
                        }
                    }
                }
            }
        ]
    },
    "athena-mcp": {
        "lambda_arn": f"arn:aws:lambda:{AWS_REGION}:{ACCOUNT_ID}:function:aiops-mcp-gateway-athena-mcp",
        "description": "AWS Athena MCP tools (start_query_execution, get_query_execution, get_query_results, list_query_executions, list_databases, list_tables, get_table_metadata, stop_query_execution)",
        "tools": [
            {
                "name": "start_query_execution",
                "description": "Start an Athena SQL query execution. Returns a query execution ID to track the query status.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query_string": {
                            "type": "string",
                            "description": "The SQL query to execute (required)"
                        },
                        "database": {
                            "type": "string",
                            "description": "Database name to query against"
                        },
                        "catalog": {
                            "type": "string",
                            "description": "Data catalog name (default: AwsDataCatalog)"
                        },
                        "workgroup": {
                            "type": "string",
                            "description": "Athena workgroup to use (default: primary)"
                        },
                        "output_location": {
                            "type": "string",
                            "description": "S3 location for query results (e.g., s3://bucket/path/)"
                        }
                    },
                    "required": ["query_string"]
                }
            },
            {
                "name": "get_query_execution",
                "description": "Get the status and details of a query execution. Use this to check if a query has completed.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query_execution_id": {
                            "type": "string",
                            "description": "The unique ID of the query execution (required)"
                        }
                    },
                    "required": ["query_execution_id"]
                }
            },
            {
                "name": "get_query_results",
                "description": "Get the results of a completed query execution. Only works for queries with SUCCEEDED status.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query_execution_id": {
                            "type": "string",
                            "description": "The unique ID of the query execution (required)"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 100, max: 1000)"
                        },
                        "next_token": {
                            "type": "string",
                            "description": "Token for pagination to get more results"
                        }
                    },
                    "required": ["query_execution_id"]
                }
            },
            {
                "name": "list_query_executions",
                "description": "List recent query executions in a workgroup. Shows query IDs, status, and truncated query text.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workgroup": {
                            "type": "string",
                            "description": "Athena workgroup to list queries from (default: primary)"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 50, max: 50)"
                        },
                        "next_token": {
                            "type": "string",
                            "description": "Token for pagination"
                        }
                    }
                }
            },
            {
                "name": "list_databases",
                "description": "List databases in a data catalog. Use this to discover available databases for querying.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "catalog": {
                            "type": "string",
                            "description": "Data catalog name (default: AwsDataCatalog)"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 50)"
                        },
                        "next_token": {
                            "type": "string",
                            "description": "Token for pagination"
                        }
                    }
                }
            },
            {
                "name": "list_tables",
                "description": "List tables in a database. Use this to discover available tables for querying.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "database": {
                            "type": "string",
                            "description": "Database name (required)"
                        },
                        "catalog": {
                            "type": "string",
                            "description": "Data catalog name (default: AwsDataCatalog)"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 50)"
                        },
                        "next_token": {
                            "type": "string",
                            "description": "Token for pagination"
                        }
                    },
                    "required": ["database"]
                }
            },
            {
                "name": "get_table_metadata",
                "description": "Get detailed metadata about a specific table including columns, partition keys, and parameters.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "database": {
                            "type": "string",
                            "description": "Database name (required)"
                        },
                        "table": {
                            "type": "string",
                            "description": "Table name (required)"
                        },
                        "catalog": {
                            "type": "string",
                            "description": "Data catalog name (default: AwsDataCatalog)"
                        }
                    },
                    "required": ["database", "table"]
                }
            },
            {
                "name": "stop_query_execution",
                "description": "Stop a running query execution. Use this to cancel long-running queries.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query_execution_id": {
                            "type": "string",
                            "description": "The unique ID of the query execution to stop (required)"
                        }
                    },
                    "required": ["query_execution_id"]
                }
            }
        ]
    },
    "cur-analyst-mcp": {
        "lambda_arn": f"arn:aws:lambda:{AWS_REGION}:{ACCOUNT_ID}:function:aiops-mcp-gateway-cur-analyst-mcp",
        "description": "CUR Data Analyst MCP tools (analyze_cur)",
        "tools": [
            {
                "name": "analyze_cur",
                "description": "Analyze AWS Cost and Usage Report data with multi-account breakdown. Executes 10 Athena queries. Defaults to current month vs previous month.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "report_month": {
                            "type": "string",
                            "description": "Report month in YYYY-MM format. Defaults to current month."
                        },
                        "compare_month": {
                            "type": "string",
                            "description": "Comparison month in YYYY-MM format. Defaults to previous month."
                        }
                    }
                }
            }
        ]
    }
}


def update_target_tool_schemas(client, gateway_id: str, target_name: str, config: dict):
    """Update a gateway target with the full tool schema."""
    print(f"\nUpdating {target_name}...")

    # Get current target
    targets = client.list_gateway_targets(gatewayIdentifier=gateway_id, maxResults=100)
    target_id = None
    for target in targets.get("items", []):
        if target["name"] == target_name:
            target_id = target["targetId"]
            break

    if not target_id:
        print(f"  Target {target_name} not found!")
        return False

    print(f"  Target ID: {target_id}")
    print(f"  Tools: {len(config['tools'])}")

    # Build the target configuration with all tools
    lambda_target_config = {
        "mcp": {
            "lambda": {
                "lambdaArn": config["lambda_arn"],
                "toolSchema": {
                    "inlinePayload": config["tools"]
                }
            }
        }
    }

    credential_config = [
        {"credentialProviderType": "GATEWAY_IAM_ROLE"}
    ]

    try:
        client.update_gateway_target(
            gatewayIdentifier=gateway_id,
            targetId=target_id,
            name=target_name,
            description=config["description"],
            targetConfiguration=lambda_target_config,
            credentialProviderConfigurations=credential_config
        )
        print(f"  Updated successfully!")
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def main():
    print("=" * 60)
    print("Updating Gateway Target Tool Schemas")
    print("=" * 60)

    session = boto3.Session(profile_name=AWS_PROFILE)
    client = session.client("bedrock-agentcore-control", region_name=AWS_REGION)

    success_count = 0
    for target_name, config in TOOL_SCHEMAS.items():
        if update_target_tool_schemas(client, GATEWAY_ID, target_name, config):
            success_count += 1

    print("\n" + "=" * 60)
    print(f"Updated {success_count}/{len(TOOL_SCHEMAS)} targets")
    print("=" * 60)

    # List updated targets
    print("\nVerifying targets...")
    targets = client.list_gateway_targets(gatewayIdentifier=GATEWAY_ID, maxResults=100)
    for target in targets.get("items", []):
        print(f"  {target['name']}: {target['status']}")


if __name__ == "__main__":
    main()
