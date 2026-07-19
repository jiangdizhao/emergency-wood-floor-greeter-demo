import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './voice.css'
import './speechRecognitionDomainPatch'
import './routedInteractionGuard'
import './realtimeOutputCircuitBreaker'
import './asrModeControl'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
