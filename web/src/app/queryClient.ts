import { QueryClient } from '@tanstack/react-query';

import { isApiError } from '@/shared/http';

/**
 * إعدادات طبقة جلب البيانات.
 *
 * ⚠️  لا تُعاد المحاولة على أخطاء العميل.
 *
 *     إعادة نداء يعيد ٤٠٤ أو ٤٠٣ ثلاث مرات تؤخّر ظهور رسالة الخطأ
 *     ثلاثة أضعاف بلا أي احتمال نجاح. الخادم المتعطّل أو الشبكة
 *     المنقطعة وحدهما يستحقّان المحاولة.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        if (isApiError(error) && !error.isRetryable) return false;
        return failureCount < 2;
      },
      staleTime: 60 * 1000,
      // ⚠️  لا إعادة جلب عند كل عودة للتبويب: على اتصال محمول تعني
      //     استهلاك بيانات المستخدم في تحديث لم يطلبه.
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
});
