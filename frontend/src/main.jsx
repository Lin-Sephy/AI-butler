import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { AuthProvider } from './contexts/AuthContext.jsx'
import { ChatProvider } from './contexts/ChatContext.jsx'
import { ConfirmProvider } from './contexts/ConfirmContext.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AuthProvider>
      <ChatProvider>
        <ConfirmProvider>
          <App />
        </ConfirmProvider>
      </ChatProvider>
    </AuthProvider>
  </React.StrictMode>
)
