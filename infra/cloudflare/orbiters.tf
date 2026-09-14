# joinorbiters.com: every DNS record of the zone, imported from what the migration of
# 2026-09-14 (ORB-193) created by hand. `terraform plan` with no change is the proof the
# panel and this file agree.

locals {
  orbiters_zone_id = "361b6234f723c08bfd1d0e79e59f3262"
}

resource "cloudflare_dns_record" "orbiters_apex_a" {
  provider = cloudflare.orbiters
  zone_id  = local.orbiters_zone_id
  name     = "joinorbiters.com"
  type     = "A"
  content  = "204.168.255.175"
  ttl      = 1
  proxied  = false
}

resource "cloudflare_dns_record" "orbiters_pigro_a" {
  provider = cloudflare.orbiters
  zone_id  = local.orbiters_zone_id
  name     = "pigro.joinorbiters.com"
  type     = "A"
  content  = "204.168.255.175"
  ttl      = 1
  proxied  = false
}

resource "cloudflare_dns_record" "orbiters_preview_a" {
  provider = cloudflare.orbiters
  zone_id  = local.orbiters_zone_id
  name     = "preview.joinorbiters.com"
  type     = "A"
  content  = "204.168.255.175"
  ttl      = 1
  proxied  = false
}

resource "cloudflare_dns_record" "orbiters_preview_pigro_a" {
  provider = cloudflare.orbiters
  zone_id  = local.orbiters_zone_id
  name     = "preview.pigro.joinorbiters.com"
  type     = "A"
  content  = "204.168.255.175"
  ttl      = 1
  proxied  = false
}

resource "cloudflare_dns_record" "orbiters_domainconnect_cname" {
  provider = cloudflare.orbiters
  zone_id  = local.orbiters_zone_id
  name     = "_domainconnect.joinorbiters.com"
  type     = "CNAME"
  content  = "_domainconnect.gd.domaincontrol.com"
  ttl      = 1
  proxied  = true
}

resource "cloudflare_dns_record" "orbiters_www_cname" {
  provider = cloudflare.orbiters
  zone_id  = local.orbiters_zone_id
  name     = "www.joinorbiters.com"
  type     = "CNAME"
  content  = "joinorbiters.com"
  ttl      = 1
  proxied  = true
}

resource "cloudflare_dns_record" "orbiters_send_mx" {
  provider = cloudflare.orbiters
  zone_id  = local.orbiters_zone_id
  name     = "send.joinorbiters.com"
  type     = "MX"
  content  = "feedback-smtp.eu-west-1.amazonses.com"
  ttl      = 1
  priority = 10
}

resource "cloudflare_dns_record" "orbiters_dmarc_txt" {
  provider = cloudflare.orbiters
  zone_id  = local.orbiters_zone_id
  name     = "_dmarc.joinorbiters.com"
  type     = "TXT"
  content  = "\"v=DMARC1; p=quarantine; adkim=r; aspf=r; rua=mailto:dmarc_rua@onsecureserver.net;\""
  ttl      = 1
}

resource "cloudflare_dns_record" "orbiters_apex_txt" {
  provider = cloudflare.orbiters
  zone_id  = local.orbiters_zone_id
  name     = "joinorbiters.com"
  type     = "TXT"
  content  = "\"google-site-verification=g0hS04ySYDhFhhnjjNT_rf5Oq5kuk1zZPb6FT2L5Mng\""
  ttl      = 3600
}

resource "cloudflare_dns_record" "orbiters_resend_domainkey_txt" {
  provider = cloudflare.orbiters
  zone_id  = local.orbiters_zone_id
  name     = "resend._domainkey.joinorbiters.com"
  type     = "TXT"
  content  = "\"p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDa1DIm4YLThl++e2BCUhnOM6y+89Dd+fAvw58i4XH1szaXoJzr8sMYgUt1f6K8lLdyPIg6g0mTM5RDXgcGb3J5/JSvfwWn9QdWwip7fOXLaoMb9IKt3oWXTU3safRkiY5yqfsrXaSFnaSNTZtez0nuZeml2zDjjF84COmd4CX8yQIDAQAB\""
  ttl      = 1
}

resource "cloudflare_dns_record" "orbiters_send_txt" {
  provider = cloudflare.orbiters
  zone_id  = local.orbiters_zone_id
  name     = "send.joinorbiters.com"
  type     = "TXT"
  content  = "\"v=spf1 include:amazonses.com ~all\""
  ttl      = 1
}
