import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:3001',
      '/clang-format': 'http://localhost:3001',
      '/ruff.toml': 'http://localhost:3001',
    },
  },
})
