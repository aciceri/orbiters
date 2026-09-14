# The records that existed before this file did. Once `terraform apply` has taken them
# into the state, this file can be deleted; kept, it is harmless and lets a fresh clone
# rebuild the state without touching a record.

import {
  to       = cloudflare_dns_record.orbiters_apex_a
  id       = "361b6234f723c08bfd1d0e79e59f3262/eab39931f980cd09a8cd1d7d73169706"
  provider = cloudflare.orbiters
}

import {
  to       = cloudflare_dns_record.orbiters_pigro_a
  id       = "361b6234f723c08bfd1d0e79e59f3262/d4180a4c2c4adf21000a56f43053631a"
  provider = cloudflare.orbiters
}

import {
  to       = cloudflare_dns_record.orbiters_preview_a
  id       = "361b6234f723c08bfd1d0e79e59f3262/a0d7b121a7a4313ac745e875189e9034"
  provider = cloudflare.orbiters
}

import {
  to       = cloudflare_dns_record.orbiters_preview_pigro_a
  id       = "361b6234f723c08bfd1d0e79e59f3262/1e5e130244e20b3ab34ade780b3edc73"
  provider = cloudflare.orbiters
}

import {
  to       = cloudflare_dns_record.orbiters_domainconnect_cname
  id       = "361b6234f723c08bfd1d0e79e59f3262/a5b791ba46abbe7f4fbf96fa7b5b219e"
  provider = cloudflare.orbiters
}

import {
  to       = cloudflare_dns_record.orbiters_www_cname
  id       = "361b6234f723c08bfd1d0e79e59f3262/9134d9b038ffebf9766953b0bd00891c"
  provider = cloudflare.orbiters
}

import {
  to       = cloudflare_dns_record.orbiters_send_mx
  id       = "361b6234f723c08bfd1d0e79e59f3262/82286462bcd72fb7a35ddc29c429c8a7"
  provider = cloudflare.orbiters
}

import {
  to       = cloudflare_dns_record.orbiters_dmarc_txt
  id       = "361b6234f723c08bfd1d0e79e59f3262/7c42f5311874a5fc869e81b69ca92ccf"
  provider = cloudflare.orbiters
}

import {
  to       = cloudflare_dns_record.orbiters_apex_txt
  id       = "361b6234f723c08bfd1d0e79e59f3262/57a9e692834ea31d5a69c38be5496057"
  provider = cloudflare.orbiters
}

import {
  to       = cloudflare_dns_record.orbiters_resend_domainkey_txt
  id       = "361b6234f723c08bfd1d0e79e59f3262/2ad5fd0cdb6ef5a69b2f4145466e77a7"
  provider = cloudflare.orbiters
}

import {
  to       = cloudflare_dns_record.orbiters_send_txt
  id       = "361b6234f723c08bfd1d0e79e59f3262/a021cdcfaccebbb9ba44a10633ebd5b5"
  provider = cloudflare.orbiters
}
