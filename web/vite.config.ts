import { fileURLToPath, URL } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },

  server: {
    port: 5173,
    // ⚠️  لا وكيل (proxy) للـ API.
    //
    //     الوكيل يجعل التطوير يعمل بمسار نسبي بينما الإنتاج يحتاج
    //     عنوانًا كاملًا — ففرق البيئتين يظهر أول مرة بعد النشر.
    //     العنوان يأتي من متغيّر البيئة في الحالتين.
  },

  build: {
    // ⚠️  تقسيم الكود على مستوى البوابة.
    //
    //     العميل الذي يتصفّح المتجر لا يحمّل شاشات الأدمن ولا نقطة
    //     البيع. الحزمة الواحدة تجعل زائرًا على شبكة ضعيفة ينتظر
    //     كودًا لن يراه أبدًا.
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          query: ['@tanstack/react-query'],
          i18n: ['i18next', 'react-i18next'],
        },
      },
    },
  },
});
