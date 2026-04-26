locals {
  issuer_url            = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.this.id}"
  discovery_url         = "${local.issuer_url}/.well-known/openid-configuration"
  token_url             = "https://${aws_cognito_user_pool_domain.this.domain}.auth.${var.aws_region}.amazoncognito.com/oauth2/token"
  fully_qualified_scope = "${aws_cognito_resource_server.this.identifier}/${var.scope_name}"
}

output "client_id" {
  description = "Cognito App Client ID"
  value       = aws_cognito_user_pool_client.this.id
}

output "client_secret" {
  description = "Cognito App Client secret"
  value       = aws_cognito_user_pool_client.this.client_secret
  sensitive   = true
}

output "token_url" {
  description = "OAuth 2.0 token endpoint"
  value       = local.token_url
}

output "scope" {
  description = "OAuth scope (<resource_server_id>/<scope_name>)"
  value       = local.fully_qualified_scope
}

output "discovery_url" {
  description = "OIDC discovery URL"
  value       = local.discovery_url
}

output "issuer_url" {
  value = local.issuer_url
}

output "resource_server_identifier" {
  value = aws_cognito_resource_server.this.identifier
}

output "user_pool_id" {
  value = aws_cognito_user_pool.this.id
}
