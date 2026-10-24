import { SHORTCUTS } from "../app/shortcuts";
import { Dialog } from "./ui/Dialog";
import { Kbd } from "./ui/Kbd";

export function ShortcutsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onClose={onClose} title="Keyboard shortcuts">
      <ul className="divide-y divide-line text-sm">
        {SHORTCUTS.map((s) => (
          <li key={s.label} className="flex items-center justify-between py-2">
            <span className="text-text">{s.label}</span>
            <span className="flex items-center gap-1">
              {s.keys.map((k, i) => (
                <span key={i} className="flex items-center gap-1">
                  {i > 0 ? <span className="text-2xs text-muted">then</span> : null}
                  <Kbd>{k}</Kbd>
                </span>
              ))}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-muted">
        Shortcuts are inactive while typing in a field or inside a dialog.
      </p>
    </Dialog>
  );
}
