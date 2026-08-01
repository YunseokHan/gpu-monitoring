interface MeterProps {
  label: string
  /** 0-100. */
  percent: number
  /** Always rendered: the meter never relies on bar length or hue alone. */
  valueText: string
  /** CSS custom property name holding this meter's hue. */
  hue: string
  title?: string
}

/**
 * A single ratio against a limit: same-ramp track, one hue, 4px rounded data end
 * anchored to the left baseline. Deliberately thin -- the number beside it is the
 * thing being read; the bar is for scanning a grid of them at a glance.
 */
export function Meter({ label, percent, valueText, hue, title }: MeterProps) {
  const clamped = Math.max(0, Math.min(100, percent))
  return (
    <div title={title}>
      <div className="flex items-baseline justify-between gap-2 text-[11px] leading-4">
        <span style={{ color: 'var(--muted)' }}>{label}</span>
        <span
          className="tabular-nums font-medium"
          style={{ color: 'var(--ink-2)' }}
        >
          {valueText}
        </span>
      </div>
      <div
        className="mt-1 h-2 w-full overflow-hidden rounded"
        style={{ background: `color-mix(in oklab, var(${hue}) 20%, var(--surface-2))` }}
        role="meter"
        aria-label={label}
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="h-full rounded transition-[width] duration-500 ease-out"
          style={{ width: `${clamped}%`, background: `var(${hue})` }}
        />
      </div>
    </div>
  )
}
