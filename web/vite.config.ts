import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  // Relative asset paths + hash routing: the build works from any static host or sub-path.
  base: './',
  // `allow: ['..']` lets the import page link the sample statements in ../samples.
  server: { port: 5102, strictPort: true, fs: { allow: ['..'] } },
  preview: { port: 5102, strictPort: true },
})
