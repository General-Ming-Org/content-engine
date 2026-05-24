/** Application mark — a stacked "page" glyph (rectangle + tab) that reads as
 *  "documents / content" without resorting to a bolt / robot / AI cliché.
 *
 *  Uses currentColor so it inherits text color from its container, which lets
 *  it adapt to every theme without per-theme overrides. */
export function Logo({
  size = 28,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      role="img"
      aria-label="Content Engine"
      className={className}
    >
      {/* back sheet */}
      <rect
        x="6"
        y="9"
        width="18"
        height="20"
        rx="2.5"
        stroke="currentColor"
        strokeWidth="1.75"
        opacity="0.45"
      />
      {/* front sheet */}
      <rect
        x="2"
        y="3"
        width="18"
        height="20"
        rx="2.5"
        fill="var(--accent)"
        stroke="var(--accent)"
        strokeWidth="1.75"
      />
      {/* paragraph lines */}
      <line x1="5.5" y1="9"  x2="16.5" y2="9"  stroke="var(--text-inverse)" strokeWidth="1.5" strokeLinecap="round" opacity="0.9" />
      <line x1="5.5" y1="13" x2="16.5" y2="13" stroke="var(--text-inverse)" strokeWidth="1.5" strokeLinecap="round" opacity="0.7" />
      <line x1="5.5" y1="17" x2="12.5" y2="17" stroke="var(--text-inverse)" strokeWidth="1.5" strokeLinecap="round" opacity="0.55" />
    </svg>
  );
}
