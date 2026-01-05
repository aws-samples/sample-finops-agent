# -----------------------------------------------------------------------------
# AIOps MCP Gateway Proxy - Terraform Makefile
# -----------------------------------------------------------------------------
# Wrapper for terraform commands with AWS credential management
# -----------------------------------------------------------------------------

# Load from terraform/config/.env if exists
-include terraform/config/.env

# Terraform directory
TF_DIR := terraform

# Defaults (override via .env or environment)
AWS_PROFILE ?= default
AWS_REGION  ?= us-east-1

# Export all TF_VAR_* variables to terraform subprocesses
export AWS_PROFILE AWS_REGION
export $(filter TF_VAR_%,$(.VARIABLES))

# Common terraform command (runs in terraform/ directory)
TF := terraform -chdir=$(TF_DIR)

.PHONY: help setup init plan apply apply-auto destroy output fmt validate lint-init lint ruff-check ruff-format ruff-fix check clean deploy update-schemas test-lambdas

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

setup: ## Initial setup - copy example configs
	@if [ ! -f $(TF_DIR)/terraform.tfvars ]; then \
		cp $(TF_DIR)/config/terraform.tfvars.example $(TF_DIR)/terraform.tfvars; \
		echo "Created $(TF_DIR)/terraform.tfvars - please edit with your values"; \
	else \
		echo "$(TF_DIR)/terraform.tfvars already exists"; \
	fi
	@if [ ! -f $(TF_DIR)/config/.env ]; then \
		cp $(TF_DIR)/config/.env.example $(TF_DIR)/config/.env; \
		echo "Created $(TF_DIR)/config/.env - please edit with your AWS profile/region"; \
	else \
		echo "$(TF_DIR)/config/.env already exists"; \
	fi
	@echo ""
	@echo "Next steps:"
	@echo "  1. Edit $(TF_DIR)/config/.env with your AWS_PROFILE and AWS_REGION"
	@echo "  2. Edit $(TF_DIR)/terraform.tfvars with your project settings"
	@echo "  3. Run 'make init' to initialize Terraform"

init: ## Initialize Terraform
	$(TF) init

plan: ## Show execution plan
	$(TF) plan

apply: ## Apply changes (with confirmation)
	$(TF) apply

apply-auto: ## Apply changes (auto-approve)
	$(TF) apply -auto-approve

destroy: ## Destroy all resources (with confirmation)
	$(TF) destroy

destroy-auto: ## Destroy all resources (auto-approve)
	$(TF) destroy -auto-approve

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
	$(TF) refresh

state-list: ## List resources in state
	$(TF) state list

show: ## Show current state
	$(TF) show

# MCP Lambda tools
update-schemas: ## Update Gateway tool schemas (run after apply)
	AWS_PROFILE=$(AWS_PROFILE) AWS_REGION=$(AWS_REGION) uv run --with boto3 python scripts/update_tool_schemas.py

deploy: apply-auto update-schemas ## Full deploy (apply + update tool schemas)
	@echo "Deployment complete!"

test-lambdas: ## Test all MCP Lambda functions
	AWS_PROFILE=$(AWS_PROFILE) AWS_REGION=$(AWS_REGION) uv run --with boto3 python scripts/test_mcp_lambdas.py
