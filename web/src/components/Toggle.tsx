interface ToggleProps {
  checked: boolean
  disabled?: boolean
  busy?: boolean
  label: string
  onChange: (next: boolean) => void
}

export function Toggle({ checked, disabled, busy, label, onChange }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      title={disabled ? 'Read-only link: append ?k=<control token> to control dummies' : label}
      disabled={disabled || busy}
      onClick={() => onChange(!checked)}
      className="relative inline-flex h-[18px] w-[32px] shrink-0 items-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-40"
      style={{
        background: checked ? 'var(--dummy)' : 'color-mix(in oklab, var(--ink) 22%, var(--surface-2))',
        outline: '1px solid var(--hairline)',
      }}
    >
      <span
        className="inline-block h-[12px] w-[12px] rounded-full transition-transform"
        style={{
          background: 'var(--surface-1)',
          transform: `translateX(${checked ? 17 : 3}px)`,
        }}
      />
    </button>
  )
}
