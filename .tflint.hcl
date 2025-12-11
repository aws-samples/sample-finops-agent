# -----------------------------------------------------------------------------
# TFLint Configuration
# https://github.com/terraform-linters/tflint
# -----------------------------------------------------------------------------

config {
  # Enable module inspection
  call_module_type = "local"
}

# AWS Provider Plugin
# Install: tflint --init
plugin "aws" {
  enabled = true
  version = "0.32.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}

# Terraform Language Rules
plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

# Custom rule overrides
rule "terraform_naming_convention" {
  enabled = true
}

rule "terraform_documented_variables" {
  enabled = true
}

rule "terraform_documented_outputs" {
  enabled = true
}
