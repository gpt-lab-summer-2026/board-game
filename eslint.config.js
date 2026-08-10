import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  // llama.cpp is a vendored checkout that ships its own eslint config (and
  // expects plugins we don't install); .venv/game-venv and models are not
  // source either. Flat config doesn't read .gitignore, so these have to be
  // named explicitly.
  globalIgnores(['dist', 'llama.cpp', 'models', '.venv', 'game-venv', 'darknet']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
  },
])
