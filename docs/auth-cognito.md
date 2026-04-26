# Cognito Authentication (client_credentials)

## Overview

The AWS FinOps Agent uses Amazon Cognito as its default gateway authentication provider. A Cognito User Pool with a `client_credentials` OAuth grant is auto-provisioned when `gateway_auth_type = "COGNITO"` (the default).

This provides machine-to-machine (M2M) authentication for external MCP clients like QuickSuite, n8n, or CI jobs — no browser sign-in or user accounts required.

### Auth Flow

```
MCP Client (QuickSuite / n8n / CI)
  | 1. POST {token_url}  grant_type=client_credentials
  |    + client_id/secret + scope=<project_name>/invoke
  v
Cognito User Pool
  | 2. Returns access_token (JWT)
  v
MCP Client
  | 3. POST {gateway_endpoint}  Authorization: Bearer <token>
  v
AgentCore Gateway (CUSTOM_JWT validator)
  |  validates: issuer, client_id
  |  (Cognito M2M tokens have no `aud` claim -- validated via allowed_clients)
  v
MCP Lambda Targets
```

## Provisioning

Cognito resources are provisioned automatically during `make apply` when:

```hcl
gateway_auth_type = "COGNITO"   # default in terraform.tfvars.example
```

This creates:
- Cognito User Pool (`<project_name>-gateway-auth`)
- Cognito Domain (`<project_name>-<account_id>` unless overridden by `cognito_domain_prefix`)
- Resource Server (`<project_name>` with scope `invoke` — override via `cognito_scope_name`)
- App Client (with `client_credentials` grant, secret generated)

## Retrieving Credentials

```bash
make show-cognito-creds
```

Output:
```
client_id:     <app-client-id>
client_secret: <app-client-secret>
token_url:     https://<domain>.auth.<region>.amazoncognito.com/oauth2/token
scope:         <project_name>/invoke
discovery_url: https://cognito-idp.<region>.amazonaws.com/<pool-id>/.well-known/openid-configuration
```

## QuickSuite Setup

In QuickSuite's MCP connector:

1. **Gateway URL**: from `terraform output -raw gateway_endpoint`
2. **Client ID**: from `make show-cognito-creds`
3. **Client Secret**: from `make show-cognito-creds`
4. **Token URL**: from `make show-cognito-creds`
5. **Scope**: `<project_name>/invoke` (e.g., `finops-mcp/invoke`)

## Local Testing

```bash
# Fetch a token
make get-token

# End-to-end: fetch token + call gateway
make test-jwt
```

## Rotating Credentials

To rotate the app client secret:

```bash
terraform -chdir=terraform taint 'module.cognito_gateway_auth[0].aws_cognito_user_pool_client.this'
make apply
```

This generates a new `client_id` and `client_secret`. Update the MCP client (QuickSuite, etc.) with the new values from `make show-cognito-creds`.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `401 Unauthorized` from Gateway | Expired/invalid token or wrong client | Re-run `make get-token`, verify `client_id` matches `make show-cognito-creds` |
| `400 Bad Request` from token endpoint | Wrong scope or missing grant_type | Verify scope is `<project_name>/invoke` |
| `invalid_client` from token endpoint | Wrong client_id or client_secret | Re-check `make show-cognito-creds` |
| Token works locally but not in QuickSuite | QuickSuite may cache old credentials | Clear QuickSuite's cached credentials and re-enter |

## Alternative: CUSTOM_JWT (BYO IdP)

For Okta, Auth0, Azure AD, Amazon Federate, or any other OIDC-compliant provider:

```hcl
gateway_auth_type     = "CUSTOM_JWT"
jwt_discovery_url     = "https://your-idp.example.com/.well-known/openid-configuration"
jwt_allowed_audiences = ["your-audience-id"]
jwt_allowed_clients   = []
```

No Cognito resources are created when `gateway_auth_type != "COGNITO"`.
