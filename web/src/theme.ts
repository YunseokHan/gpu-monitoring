export type ThemeMode = 'auto' | 'light' | 'dark'

const STORAGE_KEY = 'gpu-monitoring.theme'

function fromUrl(): ThemeMode | null {
  const value = new URLSearchParams(window.location.search).get('theme')
  return value === 'light' || value === 'dark' || value === 'auto' ? value : null
}

function fromStorage(): ThemeMode | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' || value === 'auto' ? value : null
  } catch {
    return null
  }
}

/**
 * ?theme= wins on first load, because that is how a Notion embed pins the theme for
 * everyone; after that the viewer's own choice is remembered.
 */
export function initialTheme(): ThemeMode {
  return fromStorage() ?? fromUrl() ?? 'auto'
}

export function applyTheme(mode: ThemeMode): void {
  const root = document.documentElement
  if (mode === 'auto') {
    root.removeAttribute('data-theme')
  } else {
    root.setAttribute('data-theme', mode)
  }
  try {
    window.localStorage.setItem(STORAGE_KEY, mode)
  } catch {
    /* private browsing; the setting simply will not persist */
  }
}
