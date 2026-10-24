import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useState } from "react";
import { Button } from "./Button";

/** Cursor-stack pager for `next_cursor` APIs. */
// eslint-disable-next-line react-refresh/only-export-components
export function useCursorPager() {
  const [stack, setStack] = useState<string[]>([]);
  const cursor = stack[stack.length - 1];
  const next = useCallback((c: string) => setStack((s) => [...s, c]), []);
  const prev = useCallback(() => setStack((s) => s.slice(0, -1)), []);
  const reset = useCallback(() => setStack([]), []);
  return { cursor, page: stack.length + 1, next, prev, reset, canPrev: stack.length > 0 };
}

export function Pagination({
  page,
  canPrev,
  nextCursor,
  onNext,
  onPrev,
  shown,
}: {
  page: number;
  canPrev: boolean;
  nextCursor: string | null | undefined;
  onNext: (c: string) => void;
  onPrev: () => void;
  shown: number;
}) {
  if (!canPrev && !nextCursor) return null;
  return (
    <nav
      aria-label="Pagination"
      className="flex items-center justify-between border-t border-line px-3 py-2 text-xs text-muted"
    >
      <span>
        Page {page}, {shown} shown
      </span>
      <div className="flex gap-1">
        <Button size="sm" variant="ghost" disabled={!canPrev} onClick={onPrev}>
          <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" /> Previous
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={!nextCursor}
          onClick={() => nextCursor && onNext(nextCursor)}
        >
          Next <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
        </Button>
      </div>
    </nav>
  );
}
