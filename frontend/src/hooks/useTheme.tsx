import React, { createContext, useContext, ReactNode } from 'react'

/** Theme shape matches your JSON context */
export interface Theme {
  colors: {
    background: string
    textPrimary: string
    textSecondary: string
    accent: string
    border: string
  }
  fonts: {
    heading: string
    body: string
  }
  breakpoints: {
    sm: string
    md: string
    lg: string
    xl: string
  }
}

/** The actual theme object */
export const theme: Theme = {
  colors: {
    background: '#0A1128',
    textPrimary: '#FFFFFF',
    textSecondary: '#9CA3AF',
    accent: '#8B5CF6',
    border: '#FFFFFF',
  },
  fonts: {
    heading: 'Bebas Neue, sans-serif',
    body: 'Open Sans, sans-serif',
  },
  breakpoints: {
    sm: '640px',
    md: '768px',
    lg: '1024px',
    xl: '1280px',
  },
}

/** Context to provide theme throughout your app */
const ThemeContext = createContext<Theme>(theme)

export const ThemeProvider: React.FC<{ children: ReactNode }> = ({ children }) => (
  <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>
)

/**
 * Hook: useTheme
 * Pull in colors, fonts, breakpoints from your theme object.
 */
export default function useTheme(): Theme {
  return useContext(ThemeContext)
}
