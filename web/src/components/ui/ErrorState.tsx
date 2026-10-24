import { RefreshCw } from "lucide-react";
import { ProblemAlert } from "../ProblemAlert";
import { Button } from "./Button";

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="p-4">
      <ProblemAlert error={error}>
        {onRetry ? (
          <div className="mt-3">
            <Button size="sm" onClick={onRetry}>
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> Try again
            </Button>
          </div>
        ) : null}
      </ProblemAlert>
    </div>
  );
}
