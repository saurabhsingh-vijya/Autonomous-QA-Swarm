import { cloneElement, useId, useState, type ReactElement, type ReactNode } from "react";

/**
 * Tooltip shown on hover and keyboard focus. The trigger must accept `aria-describedby`,
 * `onFocus`, `onBlur`, `onMouseEnter` and `onMouseLeave` (any button or link does).
 */
export function Tooltip({
  content,
  children,
  side = "bottom",
}: {
  content: ReactNode;
  children: ReactElement;
  side?: "top" | "bottom";
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const trigger = cloneElement(children, {
    "aria-describedby": id,
    onFocus: (e: unknown) => {
      setOpen(true);
      children.props.onFocus?.(e);
    },
    onBlur: (e: unknown) => {
      setOpen(false);
      children.props.onBlur?.(e);
    },
    onMouseEnter: (e: unknown) => {
      setOpen(true);
      children.props.onMouseEnter?.(e);
    },
    onMouseLeave: (e: unknown) => {
      setOpen(false);
      children.props.onMouseLeave?.(e);
    },
  });
  return (
    <span className="relative inline-flex">
      {trigger}
      <span
        role="tooltip"
        id={id}
        hidden={!open}
        className={`absolute left-1/2 z-40 w-max max-w-[280px] -translate-x-1/2 rounded-md border border-line bg-raised px-2.5 py-1.5 text-xs text-text shadow-dialog ${
          side === "top" ? "bottom-full mb-1.5" : "top-full mt-1.5"
        }`}
      >
        {content}
      </span>
    </span>
  );
}
