import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/ad-tree/',
  build: {
    manifest: true,
    rollupOptions: {
      input: {
        main: './index.html',
        organograma: './organograma.html',
      },
    },
  },
})
