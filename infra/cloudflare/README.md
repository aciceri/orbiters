# Cloudflare DNS, as code

The DNS of the platform's two zones, `letsrebase.com` and `joinorbiters.com`, described
in Terraform (ORB-196). Until 2026-09-14 every record was typed into Cloudflare's panel
or sent with `curl`; the migration to `letsrebase.com` (ORB-193,
`docs/migrations/2026-09-14-letsrebase.md`) was the last time. From here on a record is
a resource in `rebase.tf` or `orbiters.tf`, and `terraform plan` says whether the panel
and the repository still agree.

## Running it

Two zones in two Cloudflare accounts means two tokens, each scoped to its zone with
*Zone → DNS → Edit*. They are variables read from the environment and never written
here:

```sh
export TF_VAR_rebase_api_token=cfut_...      # letsrebase.com, Lorenzo's account
export TF_VAR_orbiters_api_token=cfat_...    # joinorbiters.com, Ivan's account
cd infra/cloudflare
terraform init
terraform plan        # nothing to do is the expected answer
```

A change is a change to a `.tf` file, a `plan` read twice, an `apply`, and the commit
that ships the file. Never the panel first: a record changed by hand is drift, and the
next `plan` proposes to undo it.

## The state

The state is a local `terraform.tfstate`, ignored by git, on the machine that ran the
last `apply`. That is acceptable while one person runs this, because the state holds
nothing that is not in Cloudflare and the `*-imports.tf` files rebuild it from nothing:
on a fresh clone, `terraform init && terraform apply` imports the twenty-one records
into a new state and changes none. When a second person needs to run it, the decision to
take is a remote backend, not a copied file.

## What is not here

The two zones themselves (created once, by hand, in each account), the Resend domain
(one resource, a community provider: not worth the dependency), the host's nginx
(`projects/*/deploy`), and the records Cloudflare manages for itself. The zone of
`joinorbiters.com` also carries GoDaddy's `_domainconnect` and the Google Search
Console verification: imported as they are, so that a `plan` stays quiet, and to be
removed here when they are removed for real (ORB-195).
