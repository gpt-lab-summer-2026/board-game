import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Bind all interfaces: the board is meant to be shown on a projector or a
    // tablet, not only on the Pi itself.
    host: true,
    proxy: {
      // Forward language-model calls to scripts/llama-server.sh so the page can
      // use a relative URL (see src/llm/config.ts). CORS is not the reason --
      // llama.cpp already allows any origin -- this is so no client needs to
      // know the Pi's address or which port the model server is on.
      '/llm': {
        target: 'http://127.0.0.1:8091',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/llm/, ''),
      },
    },
  },
})
