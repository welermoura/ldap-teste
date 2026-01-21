import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css' // Reutilizando estilos globais se houver, ou criar específicos
import OrganogramPage from './components/OrganogramPage.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <OrganogramPage />
  </StrictMode>,
)
