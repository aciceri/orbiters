import { Button } from '@/components/ui/button'

/**
 * The affordance both `InvoicesList` and `InvoicesTab` show under a truncated page: a
 * button that walks `next_cursor` one page further (REB-231), and a count so the fact
 * that the register is not fully shown is stated rather than left for the user to
 * notice on their own -- the same "say the real count" instinct `CommandPalette`'s
 * «vedi tutti» row and the Kanban's `TruncatedNotice` both follow, in this list's own
 * plain tone since a single extra page is routine here, not the pathological case
 * `TruncatedNotice` exists for.
 */
export function LoadMoreInvoices({
  shown,
  isFetchingMore,
  onLoadMore,
}: {
  shown: number
  isFetchingMore: boolean
  onLoadMore: () => void
}) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-3">
      <Button variant="outline" size="sm" onClick={onLoadMore} disabled={isFetchingMore}>
        {isFetchingMore ? 'Caricamento…' : 'Carica altre'}
      </Button>
      <span className="text-sm text-muted-foreground">
        Mostrate {shown} fatture, ce ne sono altre.
      </span>
    </div>
  )
}
