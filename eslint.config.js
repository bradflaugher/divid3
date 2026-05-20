// ESLint flat config for divid3.
//
// The site is a static page: all production JS lives inside <script
// type="module"> blocks in index.html / setup.html. `eslint-plugin-html`
// extracts those blocks so ESLint can lint them directly. Tests are TS,
// linted separately (or skipped — Playwright errors at runtime).

import globals from 'globals';
import htmlPlugin from 'eslint-plugin-html';

export default [
  {
    // Ignore vendored / build / generated paths so the linter has nothing
    // to complain about that isn't ours.
    ignores: [
      'node_modules/**',
      'playwright-report/**',
      'test-results/**',
      'models/**',
      'search-embeddings.json',
      'search-config.json',
      'package-lock.json',
    ],
  },
  {
    files: ['**/*.html'],
    plugins: { html: htmlPlugin },
    languageOptions: {
      ecmaVersion: 2024,
      sourceType: 'module',
      globals: {
        ...globals.browser,
      },
    },
    rules: {
      'no-unused-vars': ['warn', {
        args: 'none',
        varsIgnorePattern: '^_',
        caughtErrors: 'all',
        caughtErrorsIgnorePattern: '^_',
      }],
      'no-undef': 'error',
      'no-implicit-globals': 'error',
      'no-var': 'error',
      'prefer-const': 'warn',
      'eqeqeq': ['error', 'smart'],
      'no-console': 'off',
      'no-empty': ['error', { allowEmptyCatch: true }],
      'no-constant-condition': ['error', { checkLoops: false }],
    },
  },
  {
    files: ['**/*.js', '**/*.mjs'],
    languageOptions: {
      ecmaVersion: 2024,
      sourceType: 'module',
      globals: {
        ...globals.node,
      },
    },
    rules: {
      'no-unused-vars': ['warn', {
        args: 'none',
        varsIgnorePattern: '^_',
        caughtErrors: 'all',
        caughtErrorsIgnorePattern: '^_',
      }],
      'no-undef': 'error',
    },
  },
];
