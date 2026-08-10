import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Bind all interfaces: the board is meant to be shown on a projector or a
    // tablet, not only on the Pi itself.
    host: true,
    watch: {
      // This repo keeps a Python venv, a llama.cpp checkout, the models and a
      // darknet build next to the web app. That is ~107,000 files against ~60
      // files of actual source, and watching them exhausts the kernel's inotify
      // allowance (`fs.inotify.max_user_watches`, 130,983 here) -- the dev
      // server then dies with ENOSPC partway through starting. None of these
      // are ever imported by the app, so nothing is lost by not watching them.
      ignored: [
        '**/.venv/**',
        '**/llama.cpp/**',
        '**/models/**',
        '**/darknet/**',
        '**/__pycache__/**',
      ],
    },
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
      // Same relative-URL reasoning as /llm above, for the transcript
      // websocket ui_server.py broadcasts on (see voice/ui_server.py).
      '/voice-ws': {
        target: 'ws://127.0.0.1:8766',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
