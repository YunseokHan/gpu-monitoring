import type { ThemeMode } from '../theme'

const MODES: { value: ThemeMode; label: string; title: string }[] = [
  { value: 'auto', label: 'Auto', title: 'Follow the operating system setting' },
  { value: 'light', label: 'Light', title: 'Always light' },
  { value: 'dark', label: 'Dark', title: 'Always dark' },
]

/** Explicit three-way control rather than a cycling icon: no guessing what a click does. */
export function ThemeToggle({
  mode,
  onChange,
}: {
  mode: ThemeMode
  onChange: (next: ThemeMode) => void
}) {
  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className="flex overflow-hidden rounded"
      style={{ border: '1px solid var(--hairline)' }}
    >
      {MODES.map(({ value, label, title }) => {
        const active = mode === value
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            title={title}
            onClick={() => onChange(value)}
            className="px-1.5 py-0.5 text-[10px] font-medium transition-colors"
            style={{
              background: active ? 'var(--surface-1)' : 'transparent',
              color: active ? 'var(--ink)' : 'var(--muted)',
            }}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
