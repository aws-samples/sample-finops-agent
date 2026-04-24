terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.41.0" # AgentCore Gateway JWT authorizer: allowed_scopes support
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.0.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.0.0"
    }
  }

  # Optional: Remote state backend
  # Uncomment and configure for team environments
  # backend "s3" {
  #   bucket         = "your-terraform-state-bucket"
  #   key            = "aiops-mcp-gateway/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "terraform-locks"
  #   encrypt        = true
  # }
}

# Default provider - data collection account (where gateway deploys)
provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile != "" ? var.aws_profile : null

  default_tags {
    tags = var.tags
  }
}

# Management account provider - for cross-account IAM role (conditional)
# Only used when management_account_profile is set for cross-account deployment
provider "aws" {
  alias   = "management"
  region  = var.aws_region
  profile = var.management_account_profile != "" ? var.management_account_profile : null

  default_tags {
    tags = var.tags
  }

  # Skip metadata API calls if not doing cross-account deployment
  skip_metadata_api_check     = var.management_account_profile == ""
  skip_requesting_account_id  = var.management_account_profile == ""
  skip_credentials_validation = var.management_account_profile == ""
}
