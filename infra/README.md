# Infra: CloudFormation (AWS, free tier)

`cloudformation.yml` provisions one EC2 instance (t3.micro, free tier — 750 h
for 12 months after signup) that runs the full `docker compose` stack: app
(static frontend + FastAPI), analysis worker and PostgreSQL.

What stays free: t3.micro instance, 30 GB gp3 root volume, one security group.
No load balancer, no NAT gateway, no RDS, no paid features.

## Deploy

```bash
aws cloudformation deploy \
  --template-file infra/cloudformation.yml \
  --stack-name chesspulse \
  --parameter-overrides KeyName=<your-key-pair> \
  --capabilities CAPABILITY_IAM
```

`KeyName` requires an existing EC2 key pair. The AMI default is
`ami-084568db438b7818` (Amazon Linux 2023, us-east-1) — pick the equivalent for
your region via the console.

The instance installs Docker, clones the repository and runs
`docker compose up -d --build --wait` on boot; it then serves
`http://<PublicIp>:8000` (see the `PublicIp` output).

Change `POSTGRES_PASSWORD` in `/opt/chesspulse/.env` on the instance before
exposing anything publicly.

## GCP alternative (Terraform)

Same shape on GCP: an e2-micro (always-free) VM with Docker and the compose
stack. A `main.tf` equivalent is intentionally thin — the delivered AWS path is
the authoritative one in this repository.

## PaaS path

`render.yaml` at the repository root deploys the web service on Render
(`docker compose`-built image; database is Render's managed PostgreSQL — that
plan is paid, so the VM path above is used for an all-free deployment).
