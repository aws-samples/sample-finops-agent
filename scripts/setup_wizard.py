#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "questionary>=2.0",
#   "boto3",
# ]
# ///
"""Interactive setup wizard for the AWS FinOps Agent.

Prompts for every required config value, validates each against AWS (STS / S3 /
Glue), and writes `terraform/config/.env` + `terraform/config/terraform.tfvars`.
Supports interactive (TTY) and non-interactive (argparse flags) modes.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime
import functools
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal, get_args


# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
TF_DIR = REPO_ROOT / "terraform"
ENV_PATH = TF_DIR / "config" / ".env"
TFVARS_PATH = TF_DIR / "config" / "terraform.tfvars"
BACKUP_SUFFIX = ".bak"

COMMON_REGIONS = (
    "us-east-1",
    "us-east-2",
    "us-west-2",
    "eu-west-1",
    "ap-southeast-1",
    "ap-southeast-2",
)

PLACEHOLDERS = {"my-cur-cost-export", "mycostexport", "your-alias", "your-cost-center"}

DeploymentMode = Literal["single", "cross"]
AuthMode = Literal["COGNITO", "CUSTOM_JWT", "NONE"]
Environment = Literal["dev", "staging", "prod"]
DEPLOYMENT_MODES: tuple[str, ...] = get_args(DeploymentMode)
AUTH_MODES: tuple[str, ...] = get_args(AuthMode)
ENVIRONMENTS: tuple[str, ...] = get_args(Environment)

PROJECT_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
REGION_RE = re.compile(r"^[a-z]{2}-[a-z]+-\d+$")


# ----------------------------------------------------------------------------
# Dataclass: single source of truth for rendering
# ----------------------------------------------------------------------------


@dataclasses.dataclass
class WizardConfig:
    project_name: str
    deployment_mode: DeploymentMode
    aws_region: str
    # Single-account: aws_profile holds the billing profile, management_profile is "".
    # Cross-account:  aws_profile holds the data-collection profile, management_profile is set.
    aws_profile: str
    management_profile: str
    auth_mode: AuthMode
    jwt_discovery_url: str
    jwt_allowed_audiences: list[str]
    cur_bucket: str
    cur_database: str
    cur_table: str
    enable_vpc: bool
    environment: Environment
    owner: str
    cost_center: str
    n8n_cross_account_id: str = ""


# ----------------------------------------------------------------------------
# Small utilities
# ----------------------------------------------------------------------------


class ValidationError(Exception):
    """Raised by validators; caught by prompt functions to re-prompt."""


def info(msg: str) -> None:
    print(msg)


def warn(msg: str) -> None:
    print(f"  ! {msg}", file=sys.stderr)


def err(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


# ----------------------------------------------------------------------------
# AWS profile discovery + session (cached)
# ----------------------------------------------------------------------------


def list_aws_profiles() -> list[str]:
    """Return merged profile list from ~/.aws/config + ~/.aws/credentials."""
    import boto3  # type: ignore

    return sorted(boto3.Session().available_profiles)


@functools.lru_cache(maxsize=16)
def aws_session(profile: str):
    import boto3  # type: ignore

    return boto3.Session(profile_name=profile)


@functools.lru_cache(maxsize=16)
def profile_account_id(profile: str) -> str | None:
    """Return account id for profile, or None if STS lookup fails."""
    try:
        return aws_session(profile).client("sts").get_caller_identity().get("Account")
    except Exception:
        return None


# ----------------------------------------------------------------------------
# Validators
# ----------------------------------------------------------------------------


def validate_project_name(name: str) -> None:
    if not PROJECT_NAME_RE.match(name):
        raise ValidationError(
            "Project name must start with a lowercase letter and contain only "
            "lowercase letters, numbers, and hyphens (regex: ^[a-z][a-z0-9-]*$)."
        )


def validate_region(region: str) -> None:
    if not REGION_RE.match(region):
        raise ValidationError(f"'{region}' is not a valid AWS region format (e.g., us-east-1).")


def validate_sts(profile: str) -> dict:
    """Call GetCallerIdentity; return {'Account': ..., 'Arn': ...}."""
    try:
        session = aws_session(profile)
        return session.client("sts").get_caller_identity()
    except Exception as e:
        raise ValidationError(f"STS GetCallerIdentity failed for profile '{profile}': {e}") from e


def validate_s3_bucket(profile: str, bucket: str) -> None:
    try:
        session = aws_session(profile)
        session.client("s3").head_bucket(Bucket=bucket)
    except Exception as e:
        msg = str(e)
        if "404" in msg or "NoSuchBucket" in msg or "Not Found" in msg:
            raise ValidationError(f"S3 bucket '{bucket}' not found (profile '{profile}').") from e
        if "403" in msg or "Forbidden" in msg:
            warn(f"S3 bucket '{bucket}' exists but profile '{profile}' has no permission (HTTP 403). Continuing.")
            return
        raise ValidationError(f"S3 head_bucket failed for '{bucket}': {e}") from e


def validate_glue_db(profile: str, region: str, db: str) -> None:
    try:
        session = aws_session(profile)
        session.client("glue", region_name=region).get_database(Name=db)
    except Exception as e:
        raise ValidationError(f"Glue database '{db}' not found in {region}: {e}") from e


def validate_glue_table(profile: str, region: str, db: str, table: str) -> None:
    try:
        session = aws_session(profile)
        session.client("glue", region_name=region).get_table(DatabaseName=db, Name=table)
    except Exception as e:
        raise ValidationError(f"Glue table '{db}.{table}' not found in {region}: {e}") from e


def validate_url_format(url: str) -> None:
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValidationError(f"Invalid URL: {e}") from e
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValidationError(f"URL must start with http(s):// and have a host: got '{url}'.")


# ----------------------------------------------------------------------------
# Existing config detection + defaults loading
# ----------------------------------------------------------------------------


def detect_existing() -> bool:
    return ENV_PATH.exists() or TFVARS_PATH.exists()


def _parse_kv_file(path: Path) -> dict[str, str]:
    """Simple KEY=VALUE parser (handles quotes and inline comments)."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        # Strip trailing inline comment (best-effort)
        if "#" in v and not (v.startswith('"') or v.startswith("'")):
            v = v.split("#", 1)[0].strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        out[k] = v
    return out


_TFVARS_STRING_RE = re.compile(r'^\s*(\w+)\s*=\s*"([^"]*)"\s*$')
_TFVARS_BOOL_RE = re.compile(r"^\s*(\w+)\s*=\s*(true|false)\s*$")


def _parse_tfvars(path: Path) -> dict[str, Any]:
    """Best-effort parse of simple scalar assignments in a tfvars file."""
    out: dict[str, Any] = {}
    if not path.exists():
        return out
    text = path.read_text()
    for line in text.splitlines():
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("#"):
            continue
        m = _TFVARS_STRING_RE.match(line)
        if m:
            out[m.group(1)] = m.group(2)
            continue
        m = _TFVARS_BOOL_RE.match(line)
        if m:
            out[m.group(1)] = m.group(2) == "true"
            continue
    # Extract tag values Owner, CostCenter, Environment from tags map
    tag_block = re.search(r"tags\s*=\s*\{([^}]*)\}", text, re.DOTALL)
    if tag_block:
        for k in ("Owner", "CostCenter", "Environment"):
            m = re.search(rf'{k}\s*=\s*"([^"]*)"', tag_block.group(1))
            if m:
                out[f"tag_{k}"] = m.group(1)
    return out


def load_defaults_from_existing() -> dict[str, Any]:
    env = _parse_kv_file(ENV_PATH)
    tfv = _parse_tfvars(TFVARS_PATH)
    defaults: dict[str, Any] = {}
    defaults["aws_region"] = env.get("AWS_REGION") or tfv.get("aws_region") or "us-east-1"
    # Determine deployment mode
    mgmt = env.get("TF_VAR_management_account_profile", "")
    data_coll_profile = env.get("TF_VAR_aws_profile") or env.get("AWS_PROFILE", "")
    defaults["deployment_mode"] = "cross" if mgmt else "single"
    defaults["aws_profile"] = data_coll_profile
    defaults["management_profile"] = mgmt
    defaults["n8n_cross_account_id"] = env.get("TF_VAR_n8n_cross_account_id", "")

    defaults["project_name"] = tfv.get("project_name", "finops-mcp")
    defaults["auth_mode"] = tfv.get("gateway_auth_type", "COGNITO")
    defaults["jwt_discovery_url"] = tfv.get("jwt_discovery_url", "")
    defaults["cur_bucket"] = tfv.get("cur_bucket_name", "")
    defaults["cur_database"] = tfv.get("cur_database_name", "")
    defaults["cur_table"] = tfv.get("cur_table_name", "")
    defaults["enable_vpc"] = tfv.get("enable_vpc", True)
    defaults["environment"] = tfv.get("environment", "dev")
    defaults["owner"] = tfv.get("tag_Owner", "")
    defaults["cost_center"] = tfv.get("tag_CostCenter", "")
    return defaults


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------


def _generated_banner() -> str:
    today = datetime.date.today().isoformat()
    return (
        f"# Generated by scripts/setup_wizard.py on {today}.\n"
        f"# Re-run 'make setup' to regenerate. Pick \"Keep existing\" to preserve edits.\n"
    )


def render_env(cfg: WizardConfig) -> str:
    lines = [_generated_banner()]
    lines.append(f"AWS_REGION={cfg.aws_region}")
    if cfg.deployment_mode == "single":
        lines.append(f"AWS_PROFILE={cfg.aws_profile}  # billing/payer account — hosts gateway + CUR")
        lines.append(f"TF_VAR_aws_profile={cfg.aws_profile}")
        lines.append("# Single-account mode: management_account_profile intentionally unset.")
    else:
        lines.append(f"AWS_PROFILE={cfg.aws_profile}  # data-collection account — gateway + Lambdas deploy here")
        lines.append(f"TF_VAR_aws_profile={cfg.aws_profile}")
        lines.append(f"TF_VAR_management_account_profile={cfg.management_profile}  # CUR lives here")
    if cfg.n8n_cross_account_id:
        lines.append(f"TF_VAR_n8n_cross_account_id={cfg.n8n_cross_account_id}")
    return "\n".join(lines) + "\n"


def _hcl_list(values: list[str]) -> str:
    if not values:
        return "[]"
    return "[" + ", ".join(f'"{v}"' for v in values) + "]"


def render_tfvars(cfg: WizardConfig) -> str:
    lines = [_generated_banner()]
    lines.append(f'project_name = "{cfg.project_name}"')
    lines.append(f'aws_region   = "{cfg.aws_region}"')
    lines.append("")
    lines.append("# Gateway authentication")
    lines.append(f'gateway_auth_type = "{cfg.auth_mode}"')
    if cfg.auth_mode == "CUSTOM_JWT":
        lines.append(f'jwt_discovery_url     = "{cfg.jwt_discovery_url}"')
        lines.append(f"jwt_allowed_audiences = {_hcl_list(cfg.jwt_allowed_audiences)}")
    lines.append("")
    lines.append("# CUR (Cost and Usage Report) configuration")
    lines.append(f'cur_bucket_name   = "{cfg.cur_bucket}"')
    lines.append(f'cur_database_name = "{cfg.cur_database}"')
    lines.append(f'cur_table_name    = "{cfg.cur_table}"')
    lines.append("")
    lines.append("# VPC + networking")
    lines.append(f"enable_vpc = {str(cfg.enable_vpc).lower()}")
    lines.append("")
    lines.append(f'environment = "{cfg.environment}"')
    lines.append("")
    lines.append("tags = {")
    lines.append(f'  Project     = "{cfg.project_name}"')
    lines.append('  ManagedBy   = "Terraform"')
    lines.append(f'  Environment = "{cfg.environment}"')
    if cfg.owner:
        lines.append(f'  Owner       = "{cfg.owner}"')
    if cfg.cost_center:
        lines.append(f'  CostCenter  = "{cfg.cost_center}"')
    lines.append('  auto-delete = "no"')
    lines.append("}")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------
# Atomic write + backup
# ----------------------------------------------------------------------------


def backup_if_exists(path: Path) -> Path | None:
    if not path.exists():
        return None
    bak = path.with_suffix(path.suffix + BACKUP_SUFFIX)
    shutil.copy2(path, bak)
    return bak


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise


# ----------------------------------------------------------------------------
# Interactive prompts
# ----------------------------------------------------------------------------


def _q():
    """Lazy import to allow --help to work without questionary installed."""
    import questionary  # type: ignore

    return questionary


def _ask_text(label: str, default: str = "", validate=None) -> str:
    q = _q()
    while True:
        ans = q.text(label, default=default or "").ask()
        if ans is None:
            raise KeyboardInterrupt
        ans = ans.strip()
        if validate is not None:
            try:
                validate(ans)
            except ValidationError as e:
                warn(str(e))
                continue
        return ans


def _ask_select(label: str, choices: list, default: str | None = None) -> str:
    q = _q()
    ans = q.select(label, choices=choices, default=default).ask()
    if ans is None:
        raise KeyboardInterrupt
    return ans


def _ask_confirm(label: str, default: bool = True) -> bool:
    q = _q()
    ans = q.confirm(label, default=default).ask()
    if ans is None:
        raise KeyboardInterrupt
    return bool(ans)


def prompt_project_name(default: str) -> str:
    return _ask_text(
        "Project name (lowercase letters, digits, hyphens):",
        default=default or "finops-mcp",
        validate=validate_project_name,
    )


def prompt_deployment_mode(default: str = "single") -> DeploymentMode:
    q = _q()
    choices = [
        q.Choice(
            title="Single-account   (gateway + CUR in the SAME account, usually the billing/payer)", value="single"
        ),
        q.Choice(
            title="Cross-account    (gateway in data-collection account; CUR in management/payer)", value="cross"
        ),
    ]
    default_value = default if default in DEPLOYMENT_MODES else "single"
    return _ask_select("Deployment mode?", choices=choices, default=default_value)


def _profile_choices(profiles: list[str]) -> list:
    """Build questionary choices with account IDs resolved in parallel."""
    q = _q()
    info("  (looking up account IDs via STS…)")
    with ThreadPoolExecutor(max_workers=min(10, max(1, len(profiles)))) as ex:
        accounts = list(ex.map(profile_account_id, profiles))
    return [
        q.Choice(
            title=f"{p}  ({acct})" if acct else f"{p}  (account lookup failed — skip or fix creds)",
            value=p,
        )
        for p, acct in zip(profiles, accounts, strict=True)
    ]


def _select_and_verify_profile(
    label: str, profiles: list[str], default: str, skip_validation: bool
) -> tuple[str, dict]:
    """Prompt user to pick a profile and verify via STS. Re-prompts on failure.

    Returns (profile, identity) where identity is the STS GetCallerIdentity
    response (empty dict if skip_validation).
    """
    while True:
        profile = _ask_select(
            label,
            choices=_profile_choices(profiles),
            default=default if default in profiles else None,
        )
        if skip_validation:
            return profile, {}
        try:
            identity = validate_sts(profile)
            ok(f"STS identity verified: {identity.get('Arn')}")
            return profile, identity
        except ValidationError as e:
            warn(str(e))


def prompt_single_account_profile(profiles: list[str], default: str, skip_validation: bool) -> str:
    profile, _ = _select_and_verify_profile(
        "AWS profile for the billing/payer account (hosts both gateway and CUR data):",
        profiles,
        default,
        skip_validation,
    )
    return profile


def prompt_cross_account_profiles(
    profiles: list[str], defaults: dict[str, str], skip_validation: bool
) -> tuple[str, str]:
    while True:
        mgmt, ident_m = _select_and_verify_profile(
            "AWS profile for the MANAGEMENT/PAYER account (CUR S3 bucket + Glue catalog live here):",
            profiles,
            defaults.get("management_profile", ""),
            skip_validation,
        )
        data_coll, ident_d = _select_and_verify_profile(
            "AWS profile for the DATA-COLLECTION account (Gateway, Lambdas, Cognito deploy here):",
            profiles,
            defaults.get("aws_profile", ""),
            skip_validation,
        )
        if not skip_validation and ident_m.get("Account") == ident_d.get("Account"):
            warn(f"Both profiles point to account {ident_m.get('Account')} — did you mean single-account mode?")
            if not _ask_confirm("Continue anyway with cross-account config?", default=False):
                continue
        return mgmt, data_coll


def prompt_region(default: str) -> str:
    q = _q()
    choices = [q.Choice(title=r, value=r) for r in COMMON_REGIONS]
    choices.append(q.Choice(title="Other (enter manually)", value="__other__"))
    default_choice = default if default in COMMON_REGIONS else "__other__"
    ans = _ask_select("AWS region?", choices=choices, default=default_choice)
    if ans == "__other__":
        return _ask_text("Region:", default=default, validate=validate_region)
    return ans


def prompt_auth_mode(default: str = "COGNITO") -> AuthMode:
    q = _q()
    titles = {
        "COGNITO": "COGNITO       — zero-config OAuth M2M for QuickSuite/n8n (default, recommended)",
        "CUSTOM_JWT": "CUSTOM_JWT    — BYO OIDC IdP (Okta/Auth0/Azure AD) for QuickSuite or human users",
        "NONE": "NONE          — no auth (DEV ONLY — insecure)",
    }
    choices = [q.Choice(title=titles[m], value=m) for m in AUTH_MODES]
    default_value = default if default in AUTH_MODES else "COGNITO"
    ans = _ask_select(
        "Gateway auth mode (QuickSuite-compatible options only; AWS_IAM hidden):",
        choices=choices,
        default=default_value,
    )
    if ans == "NONE":
        warn("NONE disables auth. This is INSECURE and should only be used for local development.")
        typed = _ask_text("Type 'yes' to confirm NONE auth:", default="")
        if typed.lower() != "yes":
            info("  Cancelled NONE selection. Pick another auth mode.")
            return prompt_auth_mode(default="COGNITO")
    if ans in ("COGNITO", "CUSTOM_JWT"):
        info(
            "  QuickSuite MCP connector will ask for: client_id / client_secret / token_url / scope.\n"
            "  After 'make apply', print them with: make show-cognito-creds"
        )
    return ans


def prompt_jwt_details(defaults: dict[str, Any]) -> tuple[str, list[str]]:
    url = _ask_text(
        "OIDC discovery URL (e.g., https://your-idp.example.com/.well-known/openid-configuration):",
        default=defaults.get("jwt_discovery_url", ""),
        validate=validate_url_format,
    )
    auds = _ask_text(
        "Allowed audiences (comma-separated):",
        default="",
    )
    audiences = [a.strip() for a in auds.split(",") if a.strip()]
    return url, audiences


def prompt_cur_bucket(profile: str, default: str, skip_validation: bool) -> str:
    while True:
        name = _ask_text("CUR S3 bucket name:", default=default)
        if not name or name in PLACEHOLDERS:
            warn("Please enter a real S3 bucket name (placeholders are not allowed).")
            continue
        if skip_validation:
            return name
        try:
            validate_s3_bucket(profile, name)
            ok(f"s3://{name} exists and is readable")
            return name
        except ValidationError as e:
            warn(str(e))


def prompt_cur_db_table(profile: str, region: str, defaults: dict[str, str], skip_validation: bool) -> tuple[str, str]:
    while True:
        db = _ask_text("CUR Glue/Athena database:", default=defaults.get("cur_database", ""))
        if not db or db in PLACEHOLDERS:
            warn("Please enter a real Glue database name.")
            continue
        if skip_validation:
            table = _ask_text("CUR Glue/Athena table:", default=defaults.get("cur_table", ""))
            if not table or table in PLACEHOLDERS:
                warn("Please enter a real Glue table name.")
                continue
            return db, table
        try:
            validate_glue_db(profile, region, db)
            ok(f"Glue database '{db}' exists in {region}")
        except ValidationError as e:
            warn(str(e))
            continue
        table = _ask_text("CUR Glue/Athena table:", default=defaults.get("cur_table", ""))
        if not table or table in PLACEHOLDERS:
            warn("Please enter a real Glue table name.")
            continue
        try:
            validate_glue_table(profile, region, db, table)
            ok(f"Glue table '{db}.{table}' exists")
            return db, table
        except ValidationError as e:
            warn(str(e))


def prompt_enable_vpc(default: bool = True) -> bool:
    return _ask_confirm(
        "Place Lambdas in a VPC (adds VPC endpoints, no NAT Gateway)?",
        default=default,
    )


def prompt_environment(default: str = "dev") -> Environment:
    q = _q()
    choices = [q.Choice(title=e, value=e) for e in ENVIRONMENTS]
    default_value = default if default in ENVIRONMENTS else "dev"
    return _ask_select("Environment?", choices=choices, default=default_value)


def prompt_owner(default: str) -> str:
    guess = default or os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
    return _ask_text("Owner tag:", default=guess)


def prompt_cost_center(default: str) -> str:
    return _ask_text("CostCenter tag (optional, press Enter to skip):", default=default or "")


# ----------------------------------------------------------------------------
# Summary + existing-config picker
# ----------------------------------------------------------------------------


def summarize(cfg: WizardConfig) -> None:
    info("")
    info("Summary")
    info("-------")
    info(f"project_name       = {cfg.project_name}")
    info(f"deployment         = {'single-account' if cfg.deployment_mode == 'single' else 'cross-account'}")
    if cfg.deployment_mode == "single":
        acct = profile_account_id(cfg.aws_profile) or "?"
        info(f"  └─ billing profile = {cfg.aws_profile} ({acct})")
    else:
        m_acct = profile_account_id(cfg.management_profile) or "?"
        d_acct = profile_account_id(cfg.aws_profile) or "?"
        info(f"  ├─ management profile      = {cfg.management_profile} ({m_acct})  ← CUR lives here")
        info(f"  └─ data-collection profile = {cfg.aws_profile} ({d_acct})  ← gateway deploys here")
    info(f"region             = {cfg.aws_region}")
    info(f"auth               = {cfg.auth_mode}")
    if cfg.auth_mode == "CUSTOM_JWT":
        info(f"  discovery_url    = {cfg.jwt_discovery_url}")
        info(f"  audiences        = {cfg.jwt_allowed_audiences or '(none)'}")
    info(f"cur                = s3://{cfg.cur_bucket} / {cfg.cur_database}.{cfg.cur_table}")
    info(f"vpc                = {'enabled' if cfg.enable_vpc else 'disabled'}")
    cc_show = cfg.cost_center or "(none)"
    info(f"tags               = Environment={cfg.environment} Owner={cfg.owner} CostCenter={cc_show}")
    info("")


def choose_existing_action() -> Literal["reconfigure", "cancel"]:
    """Prompt the user what to do when configs already exist."""
    info("terraform/config/.env and/or terraform.tfvars already exist.")
    q = _q()
    choices = [
        q.Choice(title="Keep existing (exit without changes)", value="cancel"),
        q.Choice(title="Reconfigure (back up to .bak, re-run wizard with current values)", value="reconfigure"),
        q.Choice(title="Cancel", value="cancel"),
    ]
    return _ask_select("What would you like to do?", choices=choices, default="cancel")


# ----------------------------------------------------------------------------
# Build config from argparse args (non-interactive path)
# ----------------------------------------------------------------------------


def build_config_from_args(args: argparse.Namespace) -> WizardConfig:
    missing: list[str] = []

    def require(flag: str, value: Any) -> None:
        if value in (None, ""):
            missing.append(flag)

    require("--project-name", args.project_name)
    require("--deployment-mode", args.deployment_mode)
    require("--aws-region", args.aws_region)
    require("--auth-mode", args.auth_mode)
    require("--cur-bucket", args.cur_bucket)
    require("--cur-database", args.cur_database)
    require("--cur-table", args.cur_table)
    require("--environment", args.environment)
    require("--owner", args.owner)

    if args.deployment_mode == "single":
        require("--aws-profile", args.aws_profile)
    elif args.deployment_mode == "cross":
        require("--management-profile", args.management_profile)
        require("--data-collection-profile", args.data_collection_profile)

    if args.auth_mode == "CUSTOM_JWT":
        require("--jwt-discovery-url", args.jwt_discovery_url)

    if args.auth_mode == "NONE" and not args.force_none_auth:
        err("Refusing to configure NONE auth non-interactively — pass --force-none-auth to override.")
        sys.exit(2)

    if missing:
        err("Missing required flag(s): " + ", ".join(sorted(set(missing))))
        sys.exit(2)

    try:
        validate_project_name(args.project_name)
        validate_region(args.aws_region)
        if args.auth_mode == "CUSTOM_JWT":
            validate_url_format(args.jwt_discovery_url)
    except ValidationError as e:
        err(str(e))
        sys.exit(2)

    if args.deployment_mode == "single":
        aws_profile, management_profile = args.aws_profile, ""
    else:
        aws_profile, management_profile = args.data_collection_profile, args.management_profile

    audiences = [a.strip() for a in (args.jwt_allowed_audiences or "").split(",") if a.strip()]

    return WizardConfig(
        project_name=args.project_name,
        deployment_mode=args.deployment_mode,
        aws_region=args.aws_region,
        aws_profile=aws_profile,
        management_profile=management_profile,
        auth_mode=args.auth_mode,
        jwt_discovery_url=args.jwt_discovery_url or "",
        jwt_allowed_audiences=audiences,
        cur_bucket=args.cur_bucket,
        cur_database=args.cur_database,
        cur_table=args.cur_table,
        enable_vpc=args.enable_vpc,
        environment=args.environment,
        owner=args.owner,
        cost_center=args.cost_center,
    )


def validate_non_interactive(cfg: WizardConfig, skip_aws: bool) -> None:
    """Run AWS validations on an already-built WizardConfig. Fails fast on error."""
    if skip_aws:
        return
    try:
        if cfg.deployment_mode == "single":
            ident = validate_sts(cfg.aws_profile)
            ok(f"STS identity verified: {ident.get('Arn')}")
            cur_profile = cfg.aws_profile
        else:
            ident_m = validate_sts(cfg.management_profile)
            ok(f"Management STS identity: {ident_m.get('Arn')}")
            ident_d = validate_sts(cfg.aws_profile)
            ok(f"Data-collection STS identity: {ident_d.get('Arn')}")
            cur_profile = cfg.management_profile
        validate_s3_bucket(cur_profile, cfg.cur_bucket)
        ok(f"s3://{cfg.cur_bucket} exists")
        validate_glue_db(cur_profile, cfg.aws_region, cfg.cur_database)
        ok(f"Glue database '{cfg.cur_database}' exists in {cfg.aws_region}")
        validate_glue_table(cur_profile, cfg.aws_region, cfg.cur_database, cfg.cur_table)
        ok(f"Glue table '{cfg.cur_database}.{cfg.cur_table}' exists")
    except ValidationError as e:
        err(str(e))
        sys.exit(1)


# ----------------------------------------------------------------------------
# Interactive config builder
# ----------------------------------------------------------------------------


def build_config_interactive(defaults: dict[str, Any], skip_validation: bool) -> WizardConfig:
    profiles = list_aws_profiles()
    if not profiles:
        err("No AWS profiles found in ~/.aws/config or ~/.aws/credentials. Configure one with 'aws configure'.")
        sys.exit(1)

    project_name = prompt_project_name(defaults.get("project_name", "finops-mcp"))
    deployment_mode = prompt_deployment_mode(defaults.get("deployment_mode", "single"))

    if deployment_mode == "single":
        aws_profile = prompt_single_account_profile(profiles, defaults.get("aws_profile", ""), skip_validation)
        management_profile = ""
    else:
        management_profile, aws_profile = prompt_cross_account_profiles(
            profiles,
            {
                "management_profile": defaults.get("management_profile", ""),
                "aws_profile": defaults.get("aws_profile", ""),
            },
            skip_validation,
        )

    aws_region = prompt_region(defaults.get("aws_region", "us-east-1"))
    auth_mode = prompt_auth_mode(defaults.get("auth_mode", "COGNITO"))

    jwt_discovery_url = ""
    jwt_allowed_audiences: list[str] = []
    if auth_mode == "CUSTOM_JWT":
        jwt_discovery_url, jwt_allowed_audiences = prompt_jwt_details(defaults)

    # CUR validation: in cross-account mode, validate using the management session
    cur_profile = management_profile if deployment_mode == "cross" else aws_profile
    cur_bucket = prompt_cur_bucket(cur_profile, defaults.get("cur_bucket", ""), skip_validation)
    cur_database, cur_table = prompt_cur_db_table(
        cur_profile,
        aws_region,
        {"cur_database": defaults.get("cur_database", ""), "cur_table": defaults.get("cur_table", "")},
        skip_validation,
    )

    enable_vpc = prompt_enable_vpc(default=bool(defaults.get("enable_vpc", True)))
    environment = prompt_environment(defaults.get("environment", "dev"))
    owner = prompt_owner(defaults.get("owner", ""))
    cost_center = prompt_cost_center(defaults.get("cost_center", ""))

    return WizardConfig(
        project_name=project_name,
        deployment_mode=deployment_mode,
        aws_region=aws_region,
        aws_profile=aws_profile,
        management_profile=management_profile,
        auth_mode=auth_mode,
        jwt_discovery_url=jwt_discovery_url,
        jwt_allowed_audiences=jwt_allowed_audiences,
        cur_bucket=cur_bucket,
        cur_database=cur_database,
        cur_table=cur_table,
        enable_vpc=enable_vpc,
        environment=environment,
        owner=owner,
        cost_center=cost_center,
        n8n_cross_account_id=str(defaults.get("n8n_cross_account_id", "")),
    )


# ----------------------------------------------------------------------------
# Write-out
# ----------------------------------------------------------------------------


def write_outputs(cfg: WizardConfig, dry_run: bool) -> None:
    env_content = render_env(cfg)
    tfvars_content = render_tfvars(cfg)

    if dry_run:
        info("")
        info(f"# --- {ENV_PATH} ---")
        info(env_content.rstrip())
        info("")
        info(f"# --- {TFVARS_PATH} ---")
        info(tfvars_content.rstrip())
        info("")
        info("(dry-run — no files written)")
        return

    bak_env = backup_if_exists(ENV_PATH)
    bak_tfv = backup_if_exists(TFVARS_PATH)
    if bak_env:
        ok(f"backed up {ENV_PATH} → {bak_env}")
    if bak_tfv:
        ok(f"backed up {TFVARS_PATH} → {bak_tfv}")

    atomic_write(ENV_PATH, env_content)
    ok(f"wrote {ENV_PATH}")
    atomic_write(TFVARS_PATH, tfvars_content)
    ok(f"wrote {TFVARS_PATH}")


# ----------------------------------------------------------------------------
# Argparse
# ----------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="setup_wizard.py",
        description="Interactive setup wizard for aws-finops-agent. "
        "Prompts for every required value and validates against AWS. "
        "Pass --non-interactive + flags for CI / agent use.",
    )
    p.add_argument("--non-interactive", action="store_true", help="Flag-only mode (no prompts).")
    p.add_argument("--dry-run", action="store_true", help="Print rendered files to stdout; don't write.")
    p.add_argument("--yes", action="store_true", help="Skip final confirmation prompt.")
    p.add_argument("--reconfigure", action="store_true", help="Overwrite existing configs (back up to .bak).")
    p.add_argument("--keep-existing", action="store_true", help="Exit 0 without changes if configs exist.")
    p.add_argument("--skip-aws-validation", action="store_true", help="Skip boto3 STS/S3/Glue checks.")
    p.add_argument(
        "--force-none-auth", action="store_true", help="Required to set --auth-mode=NONE non-interactively."
    )

    p.add_argument("--project-name", help="Project name (regex ^[a-z][a-z0-9-]*$)")
    p.add_argument("--deployment-mode", choices=["single", "cross"], help="Deployment topology.")
    p.add_argument("--aws-profile", help="(single-account) billing/payer profile.")
    p.add_argument("--management-profile", help="(cross-account) management/payer profile.")
    p.add_argument("--data-collection-profile", help="(cross-account) data-collection profile.")
    p.add_argument("--aws-region", help="AWS region, e.g. us-east-1.")
    p.add_argument("--auth-mode", choices=["COGNITO", "CUSTOM_JWT", "NONE"], help="Gateway auth mode.")
    p.add_argument("--jwt-discovery-url", default="", help="(CUSTOM_JWT only) OIDC discovery URL.")
    p.add_argument("--jwt-allowed-audiences", default="", help="(CUSTOM_JWT only) comma-separated audiences.")
    p.add_argument("--cur-bucket", help="CUR S3 bucket name.")
    p.add_argument("--cur-database", help="Glue/Athena database.")
    p.add_argument("--cur-table", help="Glue/Athena table.")
    p.add_argument("--environment", choices=["dev", "staging", "prod"], help="Deployment environment.")
    p.add_argument("--owner", help="Owner tag value.")
    p.add_argument("--cost-center", default="", help="CostCenter tag value (empty ok).")
    p.add_argument(
        "--enable-vpc",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Place Lambdas in a VPC (default: enabled). Use --no-enable-vpc to disable.",
    )
    return p


def _has_any_required_flags(args: argparse.Namespace) -> bool:
    """Heuristic: any of the required flags set → user probably intends non-interactive."""
    return bool(
        args.project_name
        or args.deployment_mode
        or args.aws_profile
        or args.management_profile
        or args.data_collection_profile
        or args.aws_region
        or args.auth_mode
        or args.cur_bucket
    )


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    existing = detect_existing()

    if args.non_interactive:
        # Build + validate first so missing-flag errors surface before file-existence errors.
        cfg = build_config_from_args(args)
        # File-existence guard (dry-run skips — it never writes)
        if existing and not args.dry_run:
            if args.keep_existing:
                info("configs already exist; --keep-existing passed; nothing to do.")
                return 0
            if not args.reconfigure:
                err("configs exist. Pass --reconfigure to overwrite or --keep-existing to skip.")
                return 2
        summarize(cfg)
        validate_non_interactive(cfg, skip_aws=args.skip_aws_validation)
        write_outputs(cfg, dry_run=args.dry_run)
        if not args.dry_run:
            info("\nNext: make init && make plan")
        return 0

    defaults: dict[str, Any] = {}
    if existing:
        if choose_existing_action() == "cancel":
            info("No changes made.")
            return 0
        defaults = load_defaults_from_existing()

    info("AWS FinOps Agent — interactive setup\n")
    cfg = build_config_interactive(defaults, skip_validation=args.skip_aws_validation)
    summarize(cfg)

    if not args.yes and not _ask_confirm(
        "Write terraform/config/.env and terraform/config/terraform.tfvars?", default=True
    ):
        info("Cancelled. No files changed.")
        return 0

    write_outputs(cfg, dry_run=args.dry_run)
    if not args.dry_run:
        info("\nNext: make init && make plan")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Auto-detect non-interactive when no TTY
    tty = sys.stdin.isatty()
    if not args.non_interactive and not tty:
        if _has_any_required_flags(args):
            args.non_interactive = True
        else:
            err(
                "No TTY detected and no flags given. "
                "Run with --non-interactive + required flags, or use 'make setup-quick' for CI."
            )
            return 2

    try:
        return run(args)
    except KeyboardInterrupt:
        # Clean up any leftover .tmp files
        for p in (ENV_PATH, TFVARS_PATH):
            tmp = p.with_suffix(p.suffix + ".tmp")
            if tmp.exists():
                with contextlib.suppress(OSError):
                    tmp.unlink()
        info("\nCancelled. No files changed.")
        return 130
    except Exception as e:
        err(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
