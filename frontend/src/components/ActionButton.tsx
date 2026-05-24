import clsx from "clsx";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { BTN_DISABLED } from "../lib/formActions";

type Variant = "primary" | "ghost";

interface ActionButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

/** Primary/ghost button with consistent disabled (greyed) styling. */
export function ActionButton({
  variant = "primary",
  className,
  disabled,
  type = "button",
  children,
  ...rest
}: ActionButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled}
      className={clsx(variant === "primary" ? "btn-primary" : "btn-ghost", BTN_DISABLED, className)}
      {...rest}
    >
      {children}
    </button>
  );
}
