import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

interface FieldShellProps {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  optional?: boolean;
}

function Shell({
  id,
  label,
  hint,
  error,
  optional,
  children,
}: FieldShellProps & { id: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="label">
        {label}
        {optional ? <span className="ml-1 font-normal text-muted/80">(optional)</span> : null}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="mt-1 text-xs text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="mt-1 text-xs text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

function describedBy(id: string, error?: string | null, hint?: ReactNode) {
  if (error) return `${id}-error`;
  if (hint) return `${id}-hint`;
  return undefined;
}

export const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement> & FieldShellProps
>(function Input({ label, hint, error, optional, id, className = "", ...rest }, ref) {
  const auto = useId();
  const fid = id ?? auto;
  return (
    <Shell id={fid} label={label} hint={hint} error={error} optional={optional}>
      <input
        ref={ref}
        id={fid}
        className={`input ${error ? "border-danger" : ""} ${className}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(fid, error, hint)}
        {...rest}
      />
    </Shell>
  );
});

export const Select = forwardRef<
  HTMLSelectElement,
  SelectHTMLAttributes<HTMLSelectElement> & FieldShellProps
>(function Select({ label, hint, error, optional, id, className = "", children, ...rest }, ref) {
  const auto = useId();
  const fid = id ?? auto;
  return (
    <Shell id={fid} label={label} hint={hint} error={error} optional={optional}>
      <select
        ref={ref}
        id={fid}
        className={`input ${error ? "border-danger" : ""} ${className}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(fid, error, hint)}
        {...rest}
      >
        {children}
      </select>
    </Shell>
  );
});

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement> & FieldShellProps
>(function Textarea({ label, hint, error, optional, id, className = "", ...rest }, ref) {
  const auto = useId();
  const fid = id ?? auto;
  return (
    <Shell id={fid} label={label} hint={hint} error={error} optional={optional}>
      <textarea
        ref={ref}
        id={fid}
        className={`input ${error ? "border-danger" : ""} ${className}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(fid, error, hint)}
        {...rest}
      />
    </Shell>
  );
});
