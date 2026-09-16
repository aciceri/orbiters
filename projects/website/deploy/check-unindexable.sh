#!/usr/bin/env sh
# Proves every host that must stay out of search still does, against the live
# names rather than the vhost files that only promise it (REB-108). Nothing ran
# this before: the day an edit to preview.letsrebase.conf,
# preview.pigro.letsrebase.conf or pigro.letsrebase.conf drops the header or the
# robots.txt location, the first sign would otherwise be a preview URL in a
# search result.
#
# Both preview names are open since REB-103 (docs/adding-a-project.md §7, "A
# preview name is open"): there is no basic auth to authenticate past any more,
# so this checks only what is left -- the header and robots.txt -- and never
# reads a credential. If a preview ever goes back behind a password, resist
# `curl -u user:pass` on a path that can redirect: it prints the credential
# inside the Location header of the redirect.
#
# `pigro.letsrebase.com` is the CRM's production host and only carries the
# header once REB-107's vhost is installed there; until then this check fails
# on that one host on purpose, which is the point of running it rather than
# assuming the install happened.
#
# Reaches three live hosts over HTTPS, so it runs from the devbox or from
# `.github/preflight.json` -- a GitHub-hosted runner has nothing to prove here --
# never as a `pull_request` or `push` job. `CHECK_UNINDEXABLE_HOSTS` and
# `CHECK_UNINDEXABLE_SCHEME` override the real names for exactly one reason: proving
# this fails on a responder that omits the header, without touching a live host to
# do it, e.g.
#
#   python3 -m http.server 8000 &
#   CHECK_UNINDEXABLE_SCHEME=http CHECK_UNINDEXABLE_HOSTS=localhost:8000 \
#     bash projects/website/deploy/check-unindexable.sh
#
#   bash projects/website/deploy/check-unindexable.sh
set -eu

SCHEME="${CHECK_UNINDEXABLE_SCHEME:-https}"
HOSTS="${CHECK_UNINDEXABLE_HOSTS:-preview.letsrebase.com preview.pigro.letsrebase.com pigro.letsrebase.com}"
STATUS=0

check_host() {
  host="$1"

  headers="$(curl -sS -o /dev/null -D - --max-time 10 "${SCHEME}://${host}/")" || {
    echo "FAIL ${host}: could not reach ${SCHEME}://${host}/"
    STATUS=1
    return
  }
  if printf '%s\n' "$headers" | grep -qi '^x-robots-tag:.*noindex'; then
    echo "PASS ${host}: X-Robots-Tag carries noindex on /"
  else
    echo "FAIL ${host}: no X-Robots-Tag: noindex on ${SCHEME}://${host}/"
    STATUS=1
  fi

  robots_body="$(mktemp)"
  code="$(curl -sS -o "$robots_body" -w '%{http_code}' --max-time 10 "${SCHEME}://${host}/robots.txt")" || {
    echo "FAIL ${host}: could not reach ${SCHEME}://${host}/robots.txt"
    STATUS=1
    rm -f "$robots_body"
    return
  }
  if [ "$code" = "200" ] && grep -qE '^Disallow:[[:space:]]*/[[:space:]]*$' "$robots_body"; then
    echo "PASS ${host}: robots.txt disallows everything"
  else
    echo "FAIL ${host}: robots.txt at ${SCHEME}://${host}/robots.txt answered ${code} or did not disallow /"
    STATUS=1
  fi
  rm -f "$robots_body"
}

for host in $HOSTS; do
  check_host "$host"
done

exit "$STATUS"
