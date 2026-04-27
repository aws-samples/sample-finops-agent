"""Direct AWS API calls for ground truth comparison against MCP tool results."""

import os
from datetime import UTC, datetime

import boto3


class GroundTruthClient:
    """Direct boto3 calls to Cost Explorer and Athena APIs.

    In cross-account setups, the MCP Lambda assumes a role into the management
    account. Ground truth must use the same account — set GROUND_TRUTH_PROFILE
    to the management account profile (e.g. 'root').
    """

    def __init__(
        self,
        profile: str | None = None,
        region: str | None = None,
    ):
        profile = profile or os.environ.get("GROUND_TRUTH_PROFILE", os.environ.get("AWS_PROFILE", "default"))
        region = region or os.environ.get("AWS_REGION", "us-east-1")

        session = boto3.Session(profile_name=profile)
        self.ce = session.client("ce", region_name=region)
        self.athena = session.client("athena", region_name=region)

    @staticmethod
    def current_month_period() -> tuple[str, str]:
        """Return (start_date, end_date) for the current billing month."""
        now = datetime.now(tz=UTC)
        start = now.strftime("%Y-%m-01")
        end = f"{now.year + 1}-01-01" if now.month == 12 else f"{now.year}-{now.month + 1:02d}-01"
        return start, end

    def get_cost_and_usage(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "MONTHLY",
        metrics: list[str] | None = None,
        group_by: list[str] | None = None,
        filter_expr: dict | None = None,
    ) -> dict:
        """Direct Cost Explorer GetCostAndUsage call."""
        params = {
            "TimePeriod": {"Start": start_date, "End": end_date},
            "Granularity": granularity,
            "Metrics": metrics or ["UnblendedCost"],
        }
        if group_by:
            params["GroupBy"] = []
            for g in group_by:
                if g.startswith("TAG:"):
                    params["GroupBy"].append({"Type": "TAG", "Key": g[4:]})
                else:
                    params["GroupBy"].append({"Type": "DIMENSION", "Key": g})
        if filter_expr:
            params["Filter"] = filter_expr
        return self.ce.get_cost_and_usage(**params)

    def get_dimension_values(
        self,
        dimension: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        """Direct Cost Explorer GetDimensionValues call."""
        if not start_date or not end_date:
            start_date, end_date = self.current_month_period()
        return self.ce.get_dimension_values(
            TimePeriod={"Start": start_date, "End": end_date},
            Dimension=dimension,
        )

    def get_tag_values(
        self,
        tag_key: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        """Direct Cost Explorer GetTags call."""
        if not start_date or not end_date:
            start_date, end_date = self.current_month_period()
        return self.ce.get_tags(
            TimePeriod={"Start": start_date, "End": end_date},
            TagKey=tag_key,
        )

    def get_cost_forecast(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "MONTHLY",
        metric: str = "UNBLENDED_COST",
    ) -> dict:
        """Direct Cost Explorer GetCostForecast call."""
        return self.ce.get_cost_forecast(
            TimePeriod={"Start": start_date, "End": end_date},
            Granularity=granularity,
            Metric=metric,
        )

    def list_databases(self, catalog: str = "AwsDataCatalog") -> dict:
        """Direct Athena ListDatabases call."""
        return self.athena.list_databases(CatalogName=catalog)

    def list_tables(self, database: str, catalog: str = "AwsDataCatalog") -> dict:
        """Direct Athena ListTableMetadata call."""
        return self.athena.list_table_metadata(
            CatalogName=catalog,
            DatabaseName=database,
        )

    def get_table_metadata(
        self,
        database: str,
        table: str,
        catalog: str = "AwsDataCatalog",
    ) -> dict:
        """Direct Athena GetTableMetadata call."""
        return self.athena.get_table_metadata(
            CatalogName=catalog,
            DatabaseName=database,
            TableName=table,
        )
