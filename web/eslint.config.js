import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';
import tseslint from 'typescript-eslint';

/**
 * ⚠️  **Every restriction lives in a single `no-restricted-syntax`.**
 *
 *     In flat config, objects are merged by key and the last one **replaces**
 *     the previous rather than adding to it. Splitting them into two blocks
 *     looks tidier and silently drops the first — which is exactly what
 *     happened here: the colour rule cancelled the URL rule, so
 *     `fetch('http://localhost:8000/…')` passed unchallenged while the guard
 *     still appeared to be in the file.
 */
const RESTRICTED_SYNTAX = [
  // ── `base_url` — a single source (ADR-19) ───────────────
  //    "never write an API address by hand" is a verbal agreement, broken on the
  //    first late delivery night, and discovered only after deployment when
  //    production points at the dev server.
  {
    selector: 'Literal[value=/^(https?:)?\\/\\//]',
    message:
      'عنوان مطلق ممنوع خارج shared/http. استخدم http client بمسار نسبي — البيئة من VITE_API_BASE_URL.',
  },
  {
    selector: 'TemplateElement[value.raw=/^(https?:)?\\/\\//]',
    message: 'عنوان مطلق في قالب نصي — استخدم http client بمسار نسبي.',
  },
  {
    selector: 'Literal[value=/localhost|127\\.0\\.0\\.1|:\\d{4}(\\/|$)/]',
    message: 'اسم مضيف أو منفذ مكتوب يدويًا — يأتي من متغيّر البيئة وحده.',
  },
  {
    // ⚠️  `MetaProperty`, not `MemberExpression` — `import.meta` is a dedicated
    //     syntax node, and the wrong selector passes silently, so the guard looks
    //     present while catching nothing.
    selector: "MetaProperty[meta.name='import']",
    message: 'اقرأ متغيّرات البيئة من shared/http/config فقط — لا من import.meta مباشرة.',
  },
  {
    selector: "CallExpression[callee.name='fetch']",
    message: 'لا fetch مباشر. استخدم shared/http/client — فيه التوكن واللغة ومعالجة الأخطاء.',
  },

  // ── Theme — no hand-written colour ──────────────────────
  //    One button with a hard-coded colour stays green after the system turns
  //    blue, and is only ever caught by eye.
  {
    selector: 'Literal[value=/^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/]',
    message: 'لون مكتوب يدويًا — استخدم رمز الثيم var(--color-*).',
  },
];

export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'coverage'] },

  {
    extends: [js.configs.recommended, ...tseslint.configs.recommendedTypeChecked],
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        project: ['./tsconfig.app.json', './tsconfig.node.json'],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      '@typescript-eslint/consistent-type-imports': 'error',
      '@typescript-eslint/no-unnecessary-condition': 'off',
      'no-restricted-syntax': ['error', ...RESTRICTED_SYNTAX],
    },
  },

  // ⚠️  `shared/http` is the **only** place allowed to read environment
  //     variables and to use `fetch`. Confining it to one folder is what makes
  //     "a single source" verifiable by eye rather than taken on trust.
  {
    files: ['src/shared/http/**/*.ts'],
    rules: { 'no-restricted-syntax': 'off' },
  },

  // The theme's initial values are defined here before the server replaces them
  {
    files: ['src/shared/theme/**/*.{ts,tsx}'],
    rules: { 'no-restricted-syntax': 'off' },
  },
);
