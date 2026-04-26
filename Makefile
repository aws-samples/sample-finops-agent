# -----------------------------------------------------------------------------
# AIOps MCP Gateway Proxy - Terraform Makefile
# -----------------------------------------------------------------------------
# Wrapper for terraform commands with AWS credential management
# -----------------------------------------------------------------------------

# Terraform directory
TF_DIR := terraform

# Load from terraform/config/.env if it exists. We use `include` + re-assign
# with `override` so values in .env win over any pre-existing shell env vars
# (e.g. a stale AWS_PROFILE=prod from aws-vault). Without `override`, Make
# treats environment-origin variables as higher priority than file assignments.
# The wizard emits comments only on their own lines, so plain `include` parses
# KEY=VALUE cleanly without trailing-whitespace contamination.
ENV_FILE := $(TF_DIR)/config/.env
ifneq (,$(wildcard $(ENV_FILE)))
include $(ENV_FILE)
override AWS_PROFILE := $(AWS_PROFILE)
override AWS_REGION := $(AWS_REGION)
$(foreach v,$(filter TF_VAR_%,$(.VARIABLES)),$(eval override $(v) := $($(v))))
endif

# Defaults (used only if neither .env nor shell env set them)
AWS_PROFILE ?= default
AWS_REGION  ?= us-east-1

# Export to terraform subprocesses. AWS_SDK_LOAD_CONFIG tells the Go SDK
# (used by the Terraform AWS provider) to read named profiles from
# ~/.aws/config, not just ~/.aws/credentials.
export AWS_PROFILE AWS_REGION
export AWS_SDK_LOAD_CONFIG := 1
export $(filter TF_VAR_%,$(.VARIABLES))

# Common terraform command (runs in terraform/ directory)
TF := terraform -chdir=$(TF_DIR)
TF_VARS := -var-file=config/terraform.tfvars

.PHONY: help setup setup-quick init plan apply apply-auto destroy output fmt validate lint-init lint ruff-check ruff-format ruff-fix check clean deploy update-schemas test-lambdas get-token test-jwt show-cognito-creds

help: ## Show this help
	@echo "AIOps MCP Gateway Proxy - Terraform Commands"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Current Configuration:"
	@echo "  AWS_PROFILE: $(AWS_PROFILE)"
	@echo "  AWS_REGION:  $(AWS_REGION)"

setup: ## Interactive setup wizard (prompts + AWS validation). Pass WIZARD_ARGS=... for flags.
	@uv run --with 'questionary>=2.0,boto3' python scripts/setup_wizard.py $(WIZARD_ARGS)

setup-quick: ## Copy example configs only (no validation; for CI / power users)
	@if [ ! -f $(TF_DIR)/config/terraform.tfvars ]; then \
		cp $(TF_DIR)/config/terraform.tfvars.example $(TF_DIR)/config/terraform.tfvars; \
		echo "Created $(TF_DIR)/config/terraform.tfvars"; \
	else \
		echo "$(TF_DIR)/config/terraform.tfvars already exists"; \
	fi
	@if [ ! -f $(TF_DIR)/config/.env ]; then \
		cp $(TF_DIR)/config/.env.example $(TF_DIR)/config/.env; \
		echo "Created $(TF_DIR)/config/.env"; \
	else \
		echo "$(TF_DIR)/config/.env already exists"; \
	fi
	@echo ""
	@echo "Copied example configs to $(TF_DIR)/config/. Edit them before 'make apply'."
	@echo "Tip: 'make setup' runs an interactive wizard that fills these in for you."

init: ## Initialize Terraform
	$(TF) init

plan: ## Show execution plan
	$(TF) plan $(TF_VARS)

apply: ## Apply changes (with confirmation)
	$(TF) apply $(TF_VARS)

apply-auto: ## Apply changes (auto-approve)
	$(TF) apply $(TF_VARS) -auto-approve

destroy: ## Destroy all resources (with confirmation)
	$(TF) destroy $(TF_VARS)

destroy-auto: ## Destroy all resources (auto-approve)
	$(TF) destroy $(TF_VARS) -auto-approve

output: ## Show outputs (gateway endpoint, etc.)
	$(TF) output

fmt: ## Format Terraform files
	$(TF) fmt -recursive

validate: ## Validate configuration
	$(TF) validate

lint-init: ## Initialize tflint plugins (run once after install)
	@command -v tflint >/dev/null 2>&1 || { echo "tflint not installed. Run: brew install tflint"; exit 1; }
	tflint --init

lint: ## Run tflint (install: brew install tflint)
	@command -v tflint >/dev/null 2>&1 || { echo "tflint not installed. Run: brew install tflint"; exit 1; }
	tflint --config $(CURDIR)/$(TF_DIR)/config/.tflint.hcl --chdir $(TF_DIR)
	tflint --config $(CURDIR)/$(TF_DIR)/config/.tflint.hcl --chdir $(TF_DIR)/modules/agentcore-runtime
	tflint --config $(CURDIR)/$(TF_DIR)/config/.tflint.hcl --chdir $(TF_DIR)/modules/agentcore-gateway
	tflint --config $(CURDIR)/$(TF_DIR)/config/.tflint.hcl --chdir $(TF_DIR)/modules/lambda-proxy

# Python linting with ruff (via uv)
ruff-check: ## Check Python code with ruff
	uv run ruff check src/ scripts/

ruff-format: ## Format Python code with ruff
	uv run ruff format src/ scripts/

ruff-fix: ## Fix Python code with ruff (check + format)
	uv run ruff check --fix src/ scripts/
	uv run ruff format src/ scripts/

check: fmt validate lint ruff-check ## Run all checks (terraform + ruff)
	@echo "All checks passed!"

clean: ## Remove local Terraform files (keeps config)
	rm -rf $(TF_DIR)/.terraform $(TF_DIR)/.terraform.lock.hcl

clean-all: ## Remove all Terraform files including state
	@echo "WARNING: This will delete terraform.tfstate!"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	rm -rf $(TF_DIR)/.terraform $(TF_DIR)/.terraform.lock.hcl $(TF_DIR)/terraform.tfstate $(TF_DIR)/terraform.tfstate.backup

# Convenience targets
refresh: ## Refresh state
	$(TF) refresh $(TF_VARS)

state-list: ## List resources in state
	$(TF) state list

show: ## Show current state
	$(TF) show

# MCP Lambda tools
update-schemas: ## Update Gateway tool schemas (run after apply)
	$(eval GATEWAY_ID := $(shell $(TF) output -raw gateway_id 2>/dev/null))
	@if [ -z "$(GATEWAY_ID)" ]; then \
		echo "Error: gateway_id not found. Run 'make apply' first."; \
		exit 1; \
	fi
	GATEWAY_ID=$(GATEWAY_ID) AWS_PROFILE=$(AWS_PROFILE) AWS_REGION=$(AWS_REGION) uv run --with boto3 python scripts/update_tool_schemas.py

deploy: apply-auto update-schemas ## Full deploy (apply + update tool schemas)
	@echo "Deployment complete!"

test-lambdas: ## Test all MCP Lambda functions
	$(eval GATEWAY_ID := $(shell $(TF) output -raw gateway_id 2>/dev/null))
	GATEWAY_ID=$(GATEWAY_ID) AWS_PROFILE=$(AWS_PROFILE) AWS_REGION=$(AWS_REGION) uv run --with boto3 python scripts/test_mcp_lambdas.py

# Cognito / JWT targets (only useful when gateway_auth_type = COGNITO)
get-token: ## Fetch a Cognito access token and cache to .gateway-token.json
	uv run --with httpx python scripts/get_gateway_token.py

test-jwt: ## End-to-end smoke test: Cognito -> Gateway
	uv run --with httpx python scripts/test_gateway_jwt.py

show-cognito-creds: ## Print Cognito client_id / secret / token_url / scope for QuickSuite setup
	@echo "client_id:     $$(cd terraform && terraform output -raw gateway_cognito_client_id)"
	@echo "client_secret: $$(cd terraform && terraform output -raw gateway_cognito_client_secret)"
	@echo "token_url:     $$(cd terraform && terraform output -raw gateway_cognito_token_url)"
	@echo "scope:         $$(cd terraform && terraform output -raw gateway_cognito_scope)"
	@echo "gateway_url:   $$(cd terraform && terraform output -raw gateway_endpoint)"
	@echo "discovery_url: $$(cd terraform && terraform output -raw gateway_cognito_discovery_url)"


debug-plan:
	@echo "=== pre-exec env ==="
	@env | grep -E "^(AWS_|TF_VAR_)" | sort
	@echo "=== shell info ==="
	@echo "SHELL=$(SHELL)"
	@echo "=== direct terraform call ==="
	terraform -chdir=terraform plan -var-file=config/terraform.tfvars 2>&1 | tail -3
