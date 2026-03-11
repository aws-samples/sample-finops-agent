"""
AWS Athena MCP Server - Lambda Implementation for AgentCore Gateway

This is a custom Lambda implementation inspired by the AWSlabs Data Processing MCP Server
(https://awslabs.github.io/mcp/servers/aws-dataprocessing-mcp-server).

Why Custom Implementation vs AWSlabs MCP Server:

The AWSlabs MCP servers are not yet ready for multi-tenant MCP setups like AgentCore
Gateway. Current limitations include:
- Container-based MCP servers on AgentCore Runtime have long cold starts (30+ seconds)
- No native support for Gateway's Lambda target pattern
- Tool schema format differences (Gateway doesn't support 'enum' in JSON Schema)

This Lambda-based approach is a workaround that provides:
1. **Gateway Integration**: Lambda returns plain JSON; Gateway handles MCP protocol
2. **Simplified Deployment**: No container registry, no Dockerfile, just Python code
3. **Direct Tool Invocation**: Gateway invokes Lambda per tool call, no MCP session needed

Future Migration:
We will migrate to use AWSlabs-provided MCP servers when they are ready for
multi-tenant Gateway deployments.

Tools implemented:
- start_query_execution: Start an Athena SQL query
- get_query_execution: Get status and details of a query execution
- get_query_results: Get results of a completed query
- list_query_executions: List recent query executions
- list_databases: List databases in a data catalog
- list_tables: List tables in a database
- get_table_metadata: Get metadata about a specific table
- stop_query_execution: Stop a running query

Architecture:
    Client -> Gateway (OAuth+MCP) -> Lambda (JSON) -> Athena API

Required IAM Permissions:
- athena:StartQueryExecution
- athena:GetQueryExecution
- athena:GetQueryResults
- athena:ListQueryExecutions
- athena:ListDatabases
- athena:ListTableMetadata
- athena:GetTableMetadata
- athena:StopQueryExecution
- s3:GetBucketLocation (for results bucket)
- s3:GetObject (for query results)
- s3:PutObject (for query results)
- glue:GetDatabases (for data catalog)
- glue:GetTables (for table metadata)
"""

import json
import re

import boto3

# Block DDL/DML operations - defense in depth (IAM also restricts write actions)
BLOCKED_SQL_PATTERNS = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|CREATE|ALTER|TRUNCATE|MERGE|GRANT|REVOKE|MSCK)\b",
    re.IGNORECASE,
)


def validate_query(query_string):
    """Validate SQL query is read-only. Returns (is_valid, error_message)."""
    if BLOCKED_SQL_PATTERNS.search(query_string):
        return False, "Only SELECT, SHOW, and DESCRIBE queries are allowed. DDL/DML operations are blocked."
    return True, None

# Cross-account support - shared module is packaged alongside lambda_function.py
try:
    from shared.cross_account import get_aws_client
except ImportError:
    # Fallback for single-account mode (shared module not present)
    def get_aws_client(service_name, region_name=None, **kwargs):
        client_kwargs = {"region_name": region_name} if region_name else {}
        client_kwargs.update(kwargs)
        return boto3.client(service_name, **client_kwargs)


def lambda_handler(event, context):
    """
    Main Lambda handler for Gateway MCP tools.

    Gateway passes tool name via context.client_context.custom["bedrockAgentCoreToolName"]
    in format: <target_name>___<tool_name>
    """
    print(f"Event: {json.dumps(event)}")

    # Get tool name from Gateway context
    extended_tool_name = context.client_context.custom["bedrockAgentCoreToolName"]
    tool_name = extended_tool_name.split("___")[1]

    print(f"Tool name: {tool_name}")

    # Route to appropriate tool handler
    handlers = {
        "start_query_execution": handle_start_query_execution,
        "get_query_execution": handle_get_query_execution,
        "get_query_results": handle_get_query_results,
        "list_query_executions": handle_list_query_executions,
        "list_databases": handle_list_databases,
        "list_tables": handle_list_tables,
        "get_table_metadata": handle_get_table_metadata,
        "stop_query_execution": handle_stop_query_execution,
    }

    handler = handlers.get(tool_name)
    if handler:
        return handler(event)
    else:
        return {"error": f"Unknown tool: {tool_name}", "available_tools": list(handlers.keys())}


def handle_start_query_execution(event):
    """
    Start an Athena SQL query execution.

    Parameters:
    - query_string: The SQL query to execute (required)
    - database: Database to query against
    - catalog: Data catalog name (default: AwsDataCatalog)
    - workgroup: Athena workgroup to use (default: primary)
    - output_location: S3 location for query results
    """
    query_string = event.get("query_string")
    database = event.get("database")
    catalog = event.get("catalog", "AwsDataCatalog")
    workgroup = event.get("workgroup", "primary")
    output_location = event.get("output_location")

    if not query_string:
        return {"error": "query_string parameter is required"}

    is_valid, error_msg = validate_query(query_string)
    if not is_valid:
        return {"error": error_msg}

    athena = get_aws_client("athena")

    try:
        params = {"QueryString": query_string, "WorkGroup": workgroup}

        # Build QueryExecutionContext
        query_context = {}
        if database:
            query_context["Database"] = database
        if catalog:
            query_context["Catalog"] = catalog
        if query_context:
            params["QueryExecutionContext"] = query_context

        # Add output location if specified
        if output_location:
            params["ResultConfiguration"] = {"OutputLocation": output_location}

        response = athena.start_query_execution(**params)

        query_execution_id = response["QueryExecutionId"]

        return {
            "query_execution_id": query_execution_id,
            "status": "QUEUED",
            "message": f"Query started. Use get_query_execution with query_execution_id '{query_execution_id}' to check status.",
        }
    except Exception as e:
        return {"error": str(e)}


def handle_get_query_execution(event):
    """
    Get the status and details of a query execution.

    Parameters:
    - query_execution_id: The unique ID of the query execution (required)
    """
    query_execution_id = event.get("query_execution_id")

    if not query_execution_id:
        return {"error": "query_execution_id parameter is required"}

    athena = get_aws_client("athena")

    try:
        response = athena.get_query_execution(QueryExecutionId=query_execution_id)

        execution = response["QueryExecution"]
        status = execution["Status"]

        result = {
            "query_execution_id": query_execution_id,
            "status": status["State"],
            "query": execution.get("Query", ""),
            "database": execution.get("QueryExecutionContext", {}).get("Database"),
            "catalog": execution.get("QueryExecutionContext", {}).get("Catalog"),
            "workgroup": execution.get("WorkGroup"),
            "submission_time": str(status.get("SubmissionDateTime", "")),
            "completion_time": str(status.get("CompletionDateTime", "")),
        }

        # Add statistics if available
        if "Statistics" in execution:
            stats = execution["Statistics"]
            result["statistics"] = {
                "engine_execution_time_ms": stats.get("EngineExecutionTimeInMillis"),
                "data_scanned_bytes": stats.get("DataScannedInBytes"),
                "total_execution_time_ms": stats.get("TotalExecutionTimeInMillis"),
                "query_queue_time_ms": stats.get("QueryQueueTimeInMillis"),
                "service_processing_time_ms": stats.get("ServiceProcessingTimeInMillis"),
            }

        # Add error info if failed
        if status["State"] == "FAILED":
            result["error_message"] = status.get("StateChangeReason", "Unknown error")

        # Add output location if available
        if "ResultConfiguration" in execution:
            result["output_location"] = execution["ResultConfiguration"].get("OutputLocation")

        return result
    except Exception as e:
        return {"error": str(e), "query_execution_id": query_execution_id}


def handle_get_query_results(event):
    """
    Get the results of a completed query execution.

    Parameters:
    - query_execution_id: The unique ID of the query execution (required)
    - max_results: Maximum number of results to return (default: 100)
    - next_token: Token for pagination
    """
    query_execution_id = event.get("query_execution_id")
    max_results = event.get("max_results", 100)
    next_token = event.get("next_token")

    if not query_execution_id:
        return {"error": "query_execution_id parameter is required"}

    athena = get_aws_client("athena")

    try:
        # First check if query is complete
        exec_response = athena.get_query_execution(QueryExecutionId=query_execution_id)
        status = exec_response["QueryExecution"]["Status"]["State"]

        if status != "SUCCEEDED":
            return {
                "error": f"Query is not complete. Current status: {status}",
                "query_execution_id": query_execution_id,
                "status": status,
            }

        # Get results
        params = {
            "QueryExecutionId": query_execution_id,
            "MaxResults": min(max_results, 1000),  # Athena max is 1000
        }

        if next_token:
            params["NextToken"] = next_token

        response = athena.get_query_results(**params)

        # Parse results
        result_set = response.get("ResultSet", {})
        columns = []
        rows = []

        # Get column info
        if "ResultSetMetadata" in result_set:
            columns = [
                {"name": col.get("Name"), "type": col.get("Type")}
                for col in result_set["ResultSetMetadata"].get("ColumnInfo", [])
            ]

        # Get row data (first row is header for SELECT queries)
        raw_rows = result_set.get("Rows", [])
        is_first_row_header = True

        for row in raw_rows:
            row_data = [datum.get("VarCharValue", "") for datum in row.get("Data", [])]
            if is_first_row_header:
                is_first_row_header = False
                continue  # Skip header row
            rows.append(row_data)

        return {
            "query_execution_id": query_execution_id,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "next_token": response.get("NextToken"),
        }
    except Exception as e:
        return {"error": str(e), "query_execution_id": query_execution_id}


def handle_list_query_executions(event):
    """
    List recent query executions.

    Parameters:
    - workgroup: Filter by workgroup (default: primary)
    - max_results: Maximum number of results (default: 50)
    - next_token: Token for pagination
    """
    workgroup = event.get("workgroup", "primary")
    max_results = event.get("max_results", 50)
    next_token = event.get("next_token")

    athena = get_aws_client("athena")

    try:
        params = {
            "WorkGroup": workgroup,
            "MaxResults": min(max_results, 50),  # Athena max is 50
        }

        if next_token:
            params["NextToken"] = next_token

        response = athena.list_query_executions(**params)

        query_ids = response.get("QueryExecutionIds", [])

        # Get details for each query
        executions = []
        if query_ids:
            batch_response = athena.batch_get_query_execution(QueryExecutionIds=query_ids)

            for execution in batch_response.get("QueryExecutions", []):
                status = execution.get("Status", {})
                executions.append(
                    {
                        "query_execution_id": execution.get("QueryExecutionId"),
                        "status": status.get("State"),
                        "query": execution.get("Query", "")[:200] + "..."
                        if len(execution.get("Query", "")) > 200
                        else execution.get("Query", ""),
                        "database": execution.get("QueryExecutionContext", {}).get("Database"),
                        "submission_time": str(status.get("SubmissionDateTime", "")),
                        "workgroup": execution.get("WorkGroup"),
                    }
                )

        return {
            "workgroup": workgroup,
            "executions": executions,
            "count": len(executions),
            "next_token": response.get("NextToken"),
        }
    except Exception as e:
        return {"error": str(e)}


def handle_list_databases(event):
    """
    List databases in a data catalog.

    Parameters:
    - catalog: Data catalog name (default: AwsDataCatalog)
    - max_results: Maximum number of results (default: 50)
    - next_token: Token for pagination
    """
    catalog = event.get("catalog", "AwsDataCatalog")
    max_results = event.get("max_results", 50)
    next_token = event.get("next_token")

    athena = get_aws_client("athena")

    try:
        params = {"CatalogName": catalog, "MaxResults": min(max_results, 50)}

        if next_token:
            params["NextToken"] = next_token

        response = athena.list_databases(**params)

        databases = [
            {"name": db.get("Name"), "description": db.get("Description", ""), "parameters": db.get("Parameters", {})}
            for db in response.get("DatabaseList", [])
        ]

        return {
            "catalog": catalog,
            "databases": databases,
            "count": len(databases),
            "next_token": response.get("NextToken"),
        }
    except Exception as e:
        return {"error": str(e), "catalog": catalog}


def handle_list_tables(event):
    """
    List tables in a database.

    Parameters:
    - database: Database name (required)
    - catalog: Data catalog name (default: AwsDataCatalog)
    - max_results: Maximum number of results (default: 50)
    - next_token: Token for pagination
    """
    database = event.get("database")
    catalog = event.get("catalog", "AwsDataCatalog")
    max_results = event.get("max_results", 50)
    next_token = event.get("next_token")

    if not database:
        return {"error": "database parameter is required"}

    athena = get_aws_client("athena")

    try:
        params = {"CatalogName": catalog, "DatabaseName": database, "MaxResults": min(max_results, 50)}

        if next_token:
            params["NextToken"] = next_token

        response = athena.list_table_metadata(**params)

        tables = [
            {
                "name": table.get("Name"),
                "type": table.get("TableType"),
                "columns": [{"name": col.get("Name"), "type": col.get("Type")} for col in table.get("Columns", [])],
                "partition_keys": [
                    {"name": pk.get("Name"), "type": pk.get("Type")} for pk in table.get("PartitionKeys", [])
                ],
                "create_time": str(table.get("CreateTime", "")),
            }
            for table in response.get("TableMetadataList", [])
        ]

        return {
            "catalog": catalog,
            "database": database,
            "tables": tables,
            "count": len(tables),
            "next_token": response.get("NextToken"),
        }
    except Exception as e:
        return {"error": str(e), "database": database}


def handle_get_table_metadata(event):
    """
    Get detailed metadata about a specific table.

    Parameters:
    - database: Database name (required)
    - table: Table name (required)
    - catalog: Data catalog name (default: AwsDataCatalog)
    """
    database = event.get("database")
    table = event.get("table")
    catalog = event.get("catalog", "AwsDataCatalog")

    if not database:
        return {"error": "database parameter is required"}
    if not table:
        return {"error": "table parameter is required"}

    athena = get_aws_client("athena")

    try:
        response = athena.get_table_metadata(CatalogName=catalog, DatabaseName=database, TableName=table)

        table_meta = response.get("TableMetadata", {})

        return {
            "catalog": catalog,
            "database": database,
            "table": table,
            "name": table_meta.get("Name"),
            "type": table_meta.get("TableType"),
            "columns": [
                {"name": col.get("Name"), "type": col.get("Type"), "comment": col.get("Comment", "")}
                for col in table_meta.get("Columns", [])
            ],
            "partition_keys": [
                {"name": pk.get("Name"), "type": pk.get("Type"), "comment": pk.get("Comment", "")}
                for pk in table_meta.get("PartitionKeys", [])
            ],
            "parameters": table_meta.get("Parameters", {}),
            "create_time": str(table_meta.get("CreateTime", "")),
        }
    except Exception as e:
        return {"error": str(e), "database": database, "table": table}


def handle_stop_query_execution(event):
    """
    Stop a running query execution.

    Parameters:
    - query_execution_id: The unique ID of the query execution to stop (required)
    """
    query_execution_id = event.get("query_execution_id")

    if not query_execution_id:
        return {"error": "query_execution_id parameter is required"}

    athena = get_aws_client("athena")

    try:
        athena.stop_query_execution(QueryExecutionId=query_execution_id)

        return {
            "query_execution_id": query_execution_id,
            "status": "CANCELLED",
            "message": "Query execution stop request submitted successfully",
        }
    except Exception as e:
        return {"error": str(e), "query_execution_id": query_execution_id}
