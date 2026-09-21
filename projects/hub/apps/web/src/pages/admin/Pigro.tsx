import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { ExternalLink } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Button } from '@rebase/ui/button'
import { Input } from '@rebase/ui/input'
import { ApiError, admin } from '@/lib/api'
import { formatDate } from '@/lib/format'
import { Empty, Header } from './lists'

const PAGE_SIZE = 20
const SEARCH_DEBOUNCE_MS = 300

/** The value it settles to `delayMs` after the caller stops changing it -- the search
 *  box's own text, so filtering does not run on every keystroke (REB-313). */
function useDebounce<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

/**
 * Which spaces of PigroCRM exist and whose they are (ORB-142). The list is the CRM's
 * registry as the hub's API relays it; the one thing the hub adds is the member behind an
 * address, whose name links to their card. An address nobody applied with stays an
 * address, and nothing here creates, renames or deletes a space.
 *
 * REB-313: the registry's `GET /api/tenants/` takes no query parameters of its own, so
 * search and paging happen client-side against the one full fetch, unlike the other
 * three admin lists this card touches -- a debounced search box filters the already-
 * fetched rows by `slug` or the owner's email, and «Mostra altre» reveals more of the
 * already-fetched set rather than asking the CRM for a further page.
 */
export function AdminPigro() {
  const list = useQuery({ queryKey: ['pigro-spaces'], queryFn: () => admin.pigroSpaces() })
  const failure = list.error instanceof ApiError ? list.error : null

  const [query, setQuery] = useState('')
  const debouncedQuery = useDebounce(query, SEARCH_DEBOUNCE_MS)
  const [visible, setVisible] = useState(PAGE_SIZE)

  const filtered = useMemo(() => {
    const all = list.data?.items ?? []
    const term = debouncedQuery.trim().toLowerCase()
    if (!term) return all
    return all.filter(
      (space) => space.slug.toLowerCase().includes(term) || space.owner_email.toLowerCase().includes(term),
    )
  }, [list.data, debouncedQuery])

  // A narrower or wider filter starts the client-side page over. Reset during render
  // rather than in an effect (React's own "adjusting state when a prop changes"
  // pattern): an effect would flash the previous page before the reset commits.
  const [pagedQuery, setPagedQuery] = useState(debouncedQuery)
  if (pagedQuery !== debouncedQuery) {
    setPagedQuery(debouncedQuery)
    setVisible(PAGE_SIZE)
  }

  const items = filtered.slice(0, visible)
  const hasMore = visible < filtered.length

  const sentinelRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    if (!hasMore || typeof IntersectionObserver === 'undefined') return
    const node = sentinelRef.current
    if (!node) return
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting) setVisible((current) => current + PAGE_SIZE)
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [hasMore])

  return (
    <>
      <Header title="Istanze Pigro" count={filtered.length}>
        <Input
          type="search"
          placeholder="Cerca per spazio o email…"
          aria-label="Cerca istanze"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="w-64"
        />
      </Header>
      {list.isError ? (
        // A 503 or a 502 arrives with its own sentence; anything else gets the generic one.
        <Empty>{failure && failure.status >= 500 ? failure.message : 'Non riesco a leggere il registro.'}</Empty>
      ) : list.isPending ? (
        <Empty>Caricamento…</Empty>
      ) : filtered.length === 0 ? (
        <Empty>{debouncedQuery ? 'Nessun risultato per questa ricerca.' : 'Nessuna istanza ancora.'}</Empty>
      ) : (
        <>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr className="border-b">
                <th className="px-6 py-2 font-medium">Spazio</th>
                <th className="px-3 py-2 font-medium">Di chi è</th>
                <th className="px-6 py-2 text-right font-medium">Creato</th>
              </tr>
            </thead>
            <tbody>
              {items.map((space) => (
                <tr key={space.slug} className="border-b last:border-0 hover:bg-muted">
                  <td className="px-6 py-2.5">
                    <a
                      href={space.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 font-medium hover:underline"
                    >
                      {space.slug}
                      <ExternalLink className="size-3.5 text-muted-foreground" aria-hidden="true" />
                    </a>
                  </td>
                  <td className="px-3 py-2.5">
                    {space.membro ? (
                      <>
                        <Link
                          to="/admin/freelance/$id"
                          params={{ id: space.membro.id }}
                          className="font-medium hover:underline"
                        >
                          {space.membro.nome} {space.membro.cognome}
                        </Link>
                        <p className="text-xs text-muted-foreground">{space.owner_email}</p>
                      </>
                    ) : (
                      <p>{space.owner_email}</p>
                    )}
                  </td>
                  <td className="px-6 py-2.5 text-right text-muted-foreground">{formatDate(space.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div ref={sentinelRef} />
          {hasMore && (
            <div className="flex flex-col items-center gap-2 px-6 py-5">
              <p className="text-sm text-muted-foreground">Mostrate {items.length} istanze, ce ne sono altre.</p>
              <Button type="button" variant="outline" size="sm" onClick={() => setVisible((current) => current + PAGE_SIZE)}>
                Mostra altre
              </Button>
            </div>
          )}
        </>
      )}
    </>
  )
}
