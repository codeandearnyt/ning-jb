interface HeaderProps {
  model: string;
}

export function Header({ model }: HeaderProps) {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-bg/80 backdrop-blur-sm">
      <div className="mx-auto flex h-14 max-w-[1400px] items-center justify-between gap-4 px-4 sm:px-6">
        <div className="flex items-center gap-3">
          <svg
            width="18"
            height="18"
            viewBox="0 0 18 18"
            aria-hidden="true"
            className="shrink-0"
          >
            <path
              d="M9 1.2 16.2 5.4v7.2L9 16.8 1.8 12.6V5.4L9 1.2Z"
              fill="none"
              stroke="rgb(245 158 11)"
              strokeWidth="1.3"
            />
            <path
              d="M9 5.1 12.7 7.2v4.2L9 13.5 5.3 11.4V7.2L9 5.1Z"
              fill="rgb(249 115 22)"
              fillOpacity="0.85"
            />
          </svg>
          <span className="font-mono text-[13px] font-medium tracking-[0.22em] text-ink">
            NING-JB
          </span>
          <span className="hidden font-mono text-[10.5px] uppercase tracking-[0.18em] text-muted sm:inline">
            the forge
          </span>
        </div>

        <div className="flex items-center gap-3">
          <span className="hidden font-mono text-[10.5px] tracking-[0.1em] text-muted md:inline">
            {model}
          </span>
          <span className="flex items-center gap-1.5 rounded-sm border border-line bg-panel px-2 py-1">
            <span
              className="h-1.5 w-1.5 rounded-full bg-heat animate-pulseDot"
              aria-hidden="true"
            />
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
              ready
            </span>
          </span>
        </div>
      </div>
    </header>
  );
}
