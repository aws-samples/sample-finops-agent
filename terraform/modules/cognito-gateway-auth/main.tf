terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = ">= 5.70.0" }
  }
}

resource "aws_cognito_user_pool" "this" {
  name = "${var.project_name}-gateway-auth"

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  mfa_configuration = "OFF"

  tags = var.tags
}

resource "aws_cognito_user_pool_domain" "this" {
  domain       = var.domain_prefix
  user_pool_id = aws_cognito_user_pool.this.id
}

resource "aws_cognito_resource_server" "this" {
  identifier   = var.project_name
  name         = "${var.project_name}-resource-server"
  user_pool_id = aws_cognito_user_pool.this.id

  scope {
    scope_name        = var.scope_name
    scope_description = "Permission to invoke the ${var.project_name} gateway"
  }
}

resource "aws_cognito_user_pool_client" "this" {
  name         = "${var.project_name}-gateway-client"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = true

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_scopes                 = ["${aws_cognito_resource_server.this.identifier}/${var.scope_name}"]

  explicit_auth_flows           = []
  prevent_user_existence_errors = "ENABLED"

  depends_on = [aws_cognito_resource_server.this]
}
