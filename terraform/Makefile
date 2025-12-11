# -----------------------------------------------------------------------------
# AIOps MCP Gateway Proxy - Terraform Makefile
# -----------------------------------------------------------------------------
# Wrapper for terraform commands with AWS credential management
# -----------------------------------------------------------------------------

# Load from config/.env if exists (for Makefile AWS credentials only)
-include config/.env
export

# Defaults (override via .env or environment)
AWS_PROFILE ?= default
AWS_REGION  ?= us-east-1

# Common terraform command with AWS credentials
TF := AWS_PROFILE=$(AWS_PROFILE) AWS_REGION=$(AWS_REGION) terraform

.PHONY: help setup init plan apply apply-auto destroy output fmt validate lint-init lint check clean

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
	@if [ ! -f terraform.tfvars ]; then \
		cp config/terraform.tfvars.example terraform.tfvars; \
		echo "Created terraform.tfvars - please edit with your values"; \
	else \
		echo "terraform.tfvars already exists"; \
	fi
	@if [ ! -f config/.env ]; then \
		cp config/.env.example config/.env; \
		echo "Created config/.env - please edit with your AWS profile/region"; \
	else \
		echo "config/.env already exists"; \
	fi
	@echo ""
	@echo "Next steps:"
	@echo "  1. Edit config/.env with your AWS_PROFILE and AWS_REGION"
	@echo "  2. Edit terraform.tfvars with your project settings"
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
	tflint --config $(CURDIR)/config/.tflint.hcl
	tflint --config $(CURDIR)/config/.tflint.hcl --chdir modules/agentcore-runtime
	tflint --config $(CURDIR)/config/.tflint.hcl --chdir modules/agentcore-gateway
	tflint --config $(CURDIR)/config/.tflint.hcl --chdir modules/lambda-proxy

check: fmt validate lint ## Run all checks (fmt, validate, lint)
	@echo "All checks passed!"

clean: ## Remove local Terraform files (keeps config)
	rm -rf .terraform .terraform.lock.hcl

clean-all: ## Remove all Terraform files including state
	@echo "WARNING: This will delete terraform.tfstate!"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	rm -rf .terraform .terraform.lock.hcl terraform.tfstate terraform.tfstate.backup

# Convenience targets
refresh: ## Refresh state
	$(TF) refresh

state-list: ## List resources in state
	$(TF) state list

show: ## Show current state
	$(TF) show
