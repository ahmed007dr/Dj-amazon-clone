import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { mergeGuestCart } from '@/features/cart/api';
import { CART_KEY } from '@/features/cart/hooks';
import { registerRefreshHandler, setAccessToken } from '@/shared/http';
import { getGuestCartSession } from '@/shared/http/guestSession';

import * as api from './api';
import { AuthContext, type AuthContextValue } from './AuthContext';
import { readRefreshToken, writeRefreshToken } from './storage';
import type { LoginPayload, User } from './types';

/**
 * مزوّد المصادقة.
 *
 * ⚠️  يربط طبقة النقل بمنطق الحساب.
 *
 *     `shared/http` يعرف «كيف يُجدَّد التوكن؟» كدالة مُحقَنة، ولا
 *     يعرف شيئًا عن المستخدم ولا نقاط المصادقة. عكس ذلك يجعل طبقة
 *     النقل تعرف نموذج الحساب، فتصير أي إضافة حقل تعديلًا في مكانين.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const [user, setUser] = useState<User | null>(null);
  const [isRestoring, setIsRestoring] = useState(true);

  // ⚠️  مرجع لا حالة: يُقرأ داخل معالج التجديد الذي يُسجَّل مرة
  //     واحدة. القراءة من الحالة هناك تلتقط قيمة قديمة إلى الأبد.
  const refreshToken = useRef<string | null>(readRefreshToken());

  const applyTokens = useCallback((access: string, refresh?: string | null) => {
    setAccessToken(access);

    if (refresh !== undefined) {
      refreshToken.current = refresh;
      writeRefreshToken(refresh);
    }
  }, []);

  const clearSession = useCallback(() => {
    setAccessToken(null);
    refreshToken.current = null;
    writeRefreshToken(null);
    setUser(null);
    // ⚠️  إفراغ الكاش عند الخروج إلزامي.
    //
    //     بقاء طلبات المستخدم السابق في الكاش يعني أن من يدخل بعده
    //     على نفس الجهاز يراها للحظة قبل أن تُستبدل.
    queryClient.clear();
  }, [queryClient]);

  // ── تجديد الجلسة — يُحقَن في طبقة النقل ─────────────────
  useEffect(() => {
    registerRefreshHandler(async () => {
      const token = refreshToken.current;
      if (!token) return false;

      try {
        const tokens = await api.refreshTokens(token);
        // التدوير مُفعَّل: القديم يُدرَج في القائمة السوداء فورًا
        applyTokens(tokens.access, tokens.refresh ?? null);
        return true;
      } catch {
        clearSession();
        return false;
      }
    });
  }, [applyTokens, clearSession]);

  // ── استعادة الجلسة عند الإقلاع ──────────────────────────
  useEffect(() => {
    const stored = refreshToken.current;

    if (!stored) {
      setIsRestoring(false);
      return;
    }

    let cancelled = false;

    void (async () => {
      try {
        const tokens = await api.refreshTokens(stored);
        applyTokens(tokens.access, tokens.refresh ?? null);

        const me = await api.getMe();
        if (!cancelled) setUser(me);
      } catch {
        // ⚠️  توكن منتهٍ أو مُبطَل (إيقاف حساب · إلغاء جلسة) —
        //     التنظيف صامت: المستخدم يرى صفحة الزائر لا رسالة خطأ
        //     عن شيء لم يفعله.
        if (!cancelled) clearSession();
      } finally {
        if (!cancelled) setIsRestoring(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [applyTokens, clearSession]);

  const signIn = useCallback(
    async (payload: LoginPayload) => {
      const response = await api.login(payload);
      applyTokens(response.access, response.refresh);
      setUser(response.user);

      // ⚠️  دمج سلة الزائر **فور** الدخول.
      //
      //     الزائر ملأ سلته ثم سجّل ليشتري؛ فقدانها هنا يحدث في
      //     أسوأ لحظة ممكنة — بعد أن أثبت نيّته وقبل أن يدفع.
      //
      //     والفشل لا يُوقف الدخول: حساب لا يُفتح لأن دمج سلة فشل
      //     خسارة أكبر من سلة ضائعة.
      try {
        const merged = await mergeGuestCart(getGuestCartSession());
        queryClient.setQueriesData({ queryKey: CART_KEY }, merged);
      } catch {
        void queryClient.invalidateQueries({ queryKey: CART_KEY });
      }

      return response.user;
    },
    [applyTokens, queryClient],
  );

  const signOut = useCallback(async () => {
    const token = refreshToken.current;

    // ⚠️  التنظيف المحلي يقع **مهما فشل نداء الخروج**.
    //
    //     شبكة منقطعة تجعل النداء يفشل؛ إبقاء المستخدم داخلًا لأن
    //     الخادم لم يردّ يترك جلسة مفتوحة على جهاز أراد صاحبه إغلاقها.
    try {
      if (token) await api.logout(token);
    } catch {
      // متوقَّع عند انقطاع الشبكة أو توكن مُبطَل مسبقًا
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isRestoring,
      isAuthenticated: user !== null,
      signIn,
      signOut,
    }),
    [user, isRestoring, signIn, signOut],
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}
