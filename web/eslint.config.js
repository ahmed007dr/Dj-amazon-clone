import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';
import tseslint from 'typescript-eslint';

/**
 * ⚠️  **كل القيود في `no-restricted-syntax` واحد.**
 *
 *     في الإعداد المسطّح تُدمَج الكائنات بالمفتاح، والأخير
 *     **يستبدل** السابق لا يضاف إليه. فصلها إلى كتلتين يبدو أنظف
 *     ويُسقط الأولى بصمت — وهو ما وقع فعلًا هنا: قاعدة الألوان
 *     ألغت قاعدة الروابط، فمرّ `fetch('http://localhost:8000/…')`
 *     بلا اعتراض بينما بدا الحارس قائمًا في الملف.
 */
const RESTRICTED_SYNTAX = [
  // ── `base_url` — مصدر واحد (ADR-19) ────────────────────
  //    «ممنوع كتابة عنوان API يدويًا» اتفاق شفهي يُخرَق في أول ليلة
  //    تسليم متأخرة، ولا يُكتشف إلا بعد النشر حين يشير الإنتاج إلى
  //    خادم التطوير.
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
    // ⚠️  `MetaProperty` لا `MemberExpression` — `import.meta` عقدة
    //     نحوية خاصة، والمحدِّد الخاطئ يمرّ صامتًا فيبدو الحارس قائمًا
    //     وهو لا يمسك شيئًا.
    selector: "MetaProperty[meta.name='import']",
    message: 'اقرأ متغيّرات البيئة من shared/http/config فقط — لا من import.meta مباشرة.',
  },
  {
    selector: "CallExpression[callee.name='fetch']",
    message: 'لا fetch مباشر. استخدم shared/http/client — فيه التوكن واللغة ومعالجة الأخطاء.',
  },

  // ── الثيم — لا لون مكتوب يدويًا ────────────────────────
  //    زر واحد بلون ثابت يبقى أخضر بعد أن يصير النظام أزرق، ولا
  //    يُكتشف إلا بالنظر.
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

  // ⚠️  `shared/http` هو المكان **الوحيد** المسموح فيه بقراءة
  //     متغيّرات البيئة واستخدام `fetch`. حصره في مجلد واحد هو ما
  //     يجعل «مصدر واحد» قابلًا للتحقق بالعين لا بالثقة.
  {
    files: ['src/shared/http/**/*.ts'],
    rules: { 'no-restricted-syntax': 'off' },
  },

  // القيم الابتدائية للثيم تُعرَّف هنا قبل أن يستبدلها الخادم
  {
    files: ['src/shared/theme/**/*.{ts,tsx}'],
    rules: { 'no-restricted-syntax': 'off' },
  },
);
