import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { forcedTheme } from './api'
import './index.css'

// Notion gives an iframe no way to learn the page's theme, so ?theme=dark|light on the
// embed URL is the escape hatch; without it we follow the viewer's OS setting.
if (forcedTheme === 'dark' || forcedTheme === 'light') {
  document.documentElement.setAttribute('data-theme', forcedTheme)
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
