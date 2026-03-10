# -----------------------------------------------------------------------------
# VPC Module for Lambda Functions
# Private subnets with VPC endpoints — no NAT Gateway needed
# -----------------------------------------------------------------------------

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

# -----------------------------------------------------------------------------
# VPC
# -----------------------------------------------------------------------------

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, {
    Name = "${var.project_name}-vpc"
  })
}

# -----------------------------------------------------------------------------
# VPC Flow Logs (CKV2_AWS_11)
# -----------------------------------------------------------------------------

resource "aws_flow_log" "this" {
  vpc_id               = aws_vpc.this.id
  traffic_type         = "ALL"
  log_destination_type = "cloud-watch-logs"
  log_destination      = aws_cloudwatch_log_group.flow_log.arn
  iam_role_arn         = aws_iam_role.flow_log.arn

  tags = merge(var.tags, {
    Name = "${var.project_name}-vpc-flow-log"
  })
}

resource "aws_cloudwatch_log_group" "flow_log" {
  name              = "/aws/vpc/flow-log/${var.project_name}"
  retention_in_days = var.flow_log_retention_in_days
  kms_key_id        = var.log_group_kms_key_arn

  tags = var.tags
}

data "aws_iam_policy_document" "flow_log_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["vpc-flow-logs.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "flow_log_permissions" {
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams"
    ]
    resources = ["${aws_cloudwatch_log_group.flow_log.arn}:*"]
  }
}

resource "aws_iam_role" "flow_log" {
  name               = "${var.project_name}-vpc-flow-log-role"
  assume_role_policy = data.aws_iam_policy_document.flow_log_trust.json

  tags = var.tags
}

resource "aws_iam_role_policy" "flow_log" {
  name   = "${var.project_name}-vpc-flow-log-policy"
  role   = aws_iam_role.flow_log.id
  policy = data.aws_iam_policy_document.flow_log_permissions.json
}

# Restrict default security group to deny all traffic (CKV2_AWS_12)
resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, {
    Name = "${var.project_name}-default-sg-restricted"
  })
}

# -----------------------------------------------------------------------------
# Private Subnets (2 AZs for HA)
# -----------------------------------------------------------------------------

resource "aws_subnet" "private" {
  for_each = toset(local.azs)

  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 1, index(local.azs, each.key))
  availability_zone = each.key

  tags = merge(var.tags, {
    Name = "${var.project_name}-private-${each.key}"
  })
}

# -----------------------------------------------------------------------------
# Route Table
# -----------------------------------------------------------------------------

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, {
    Name = "${var.project_name}-private-rt"
  })
}

resource "aws_route_table_association" "private" {
  for_each = aws_subnet.private

  subnet_id      = each.value.id
  route_table_id = aws_route_table.private.id
}

# -----------------------------------------------------------------------------
# Security Group (shared by Lambda and VPC endpoints)
# -----------------------------------------------------------------------------

resource "aws_security_group" "lambda" {
  name        = "${var.project_name}-lambda-vpc-sg"
  description = "Security group for Lambda functions and VPC endpoints"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "HTTPS from self for VPC endpoint traffic"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    self        = true
  }

  egress {
    description = "HTTPS to self for VPC endpoint traffic"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    self        = true
  }

  egress {
    description     = "HTTPS to S3 via gateway endpoint"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    prefix_list_ids = [aws_vpc_endpoint.s3.prefix_list_id]
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-lambda-vpc-sg"
  })
}

# -----------------------------------------------------------------------------
# S3 Gateway Endpoint (free, route-table based)
# -----------------------------------------------------------------------------

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = merge(var.tags, {
    Name = "${var.project_name}-s3-endpoint"
  })
}

# -----------------------------------------------------------------------------
# Interface VPC Endpoints
# -----------------------------------------------------------------------------

resource "aws_vpc_endpoint" "interface" {
  for_each = toset(var.interface_endpoint_services)

  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${var.aws_region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [for s in aws_subnet.private : s.id]
  security_group_ids  = [aws_security_group.lambda.id]

  tags = merge(var.tags, {
    Name = "${var.project_name}-${each.key}-endpoint"
  })
}
