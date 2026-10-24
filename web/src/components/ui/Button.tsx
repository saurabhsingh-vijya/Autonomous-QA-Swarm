import { Loader2 } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { Link, type LinkProps } from "react-router-dom";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

const BASE =
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md font-medium rao-transition disabled:cursor-not-allowed disabled:opacity-50";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-accent text-accent-fg hover:bg-accent-hover border border-transparent",
  secondary: "border border-line bg-surface text-text hover:border-line-strong hover:bg-raised",
  ghost: "border border-transparent text-muted hover:bg-raised hover:text-text",
  danger: "border border-danger/40 bg-surface text-danger hover:bg-danger/10",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "h-7 px-2.5 text-xs",
  md: "h-8 px-3 text-sm",
};

// eslint-disable-next-line react-refresh/only-export-components
export function buttonClass(variant: ButtonVariant = "secondary", size: ButtonSize = "md") {
  return `${BASE} ${VARIANTS[variant]} ${SIZES[size]}`;
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading = false, className = "", children, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={rest.type ?? "button"}
      className={`${buttonClass(variant, size)} ${className}`}
      aria-busy={loading || undefined}
      {...rest}
      disabled={rest.disabled || loading}
    >
      {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : null}
      {children}
    </button>
  );
});

export function LinkButton({
  variant = "secondary",
  size = "md",
  className = "",
  ...rest
}: LinkProps & { variant?: ButtonVariant; size?: ButtonSize }) {
  return <Link className={`${buttonClass(variant, size)} ${className}`} {...rest} />;
}
