import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  checkout,
  closeSession,
  getMySession,
  listCashMovements,
  listRegisters,
  openSession,
  quoteSale,
  recordCash,
  searchProducts,
  type PaymentInput,
  type SaleLineInput,
} from './api';

const SESSION_KEY = ['pos', 'session'];

export function useMySession() {
  return useQuery({
    queryKey: SESSION_KEY,
    queryFn: getMySession,
    // ⚠️  بلا `staleTime`: فتح الوردية وإغلاقها يغيّران كل الشاشة،
    //     وعرض وردية مغلقة كأنها مفتوحة يجعل الكاشير يبيع في فراغ.
    staleTime: 0,
  });
}

export function useRegisters() {
  return useQuery({ queryKey: ['pos', 'registers'], queryFn: listRegisters });
}

export function useCashMovements(enabled: boolean) {
  return useQuery({
    queryKey: ['pos', 'cash'],
    queryFn: listCashMovements,
    enabled,
  });
}

function useSessionMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SESSION_KEY });
      void queryClient.invalidateQueries({ queryKey: ['pos', 'cash'] });
      void queryClient.invalidateQueries({ queryKey: ['pos', 'registers'] });
    },
  });
}

export function useOpenSession() {
  return useSessionMutation(({ register, float }: { register: string; float: string }) =>
    openSession(register, float),
  );
}

/**
 * إغلاق الوردية.
 *
 * ⚠️  **لا يُبطل استعلام الوردية — وهذا مقصود.**
 *
 *     `/session/` تعيد `null` بعد الإغلاق، والقشرة تستبدل الشاشة
 *     ببوابة فتح وردية جديدة فور ذلك. الإبطال التلقائي كان يخطف
 *     شاشة التسوية في نفس اللحظة التي تظهر فيها — فيُغلق الكاشير
 *     ورديته **ولا يرى الفرق النقدي إطلاقًا**، وهو الرقم الوحيد
 *     الذي أُغلقت الوردية من أجله.
 *
 *     الإبطال يصير فعلًا مقصودًا: `finish()` بعد قراءة التسوية.
 */
export function useCloseSession() {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: ({ counted, note }: { counted: string; note: string }) =>
      closeSession(counted, note),
  });

  const finish = () => {
    void queryClient.invalidateQueries({ queryKey: SESSION_KEY });
    void queryClient.invalidateQueries({ queryKey: ['pos', 'cash'] });
    void queryClient.invalidateQueries({ queryKey: ['pos', 'registers'] });
  };

  return { ...mutation, finish };
}

export function useRecordCash() {
  return useSessionMutation(
    ({ kind, amount, reason }: { kind: 'PAY_IN' | 'PAY_OUT'; amount: string; reason: string }) =>
      recordCash(kind, amount, reason),
  );
}

export function useProductSearch(term: string) {
  return useQuery({
    queryKey: ['pos', 'products', term],
    queryFn: () => searchProducts(term),
    // ⚠️  إبقاء النتائج السابقة أثناء الكتابة.
    //
    //     وميض القائمة فارغةً بين كل حرفين يجعل الكاشير يظن أن
    //     الصنف غير موجود فيمسح ويعيد — على شاشة يستخدمها بسرعة.
    placeholderData: keepPreviousData,
    staleTime: 30 * 1000,
  });
}

/**
 * ⚠️  التسعير **نداء خادم لا حساب في المتصفح**.
 *
 *     الشرائح والخصومات والضريبة المتغيّرة (وقد تكون غائبة أصلًا)
 *     محاكاتها هنا تعني رقمين ينفصلان — أحدهما على الشاشة والآخر
 *     على الإيصال.
 */
export function useQuote(lines: SaleLineInput[], discountPercent: string) {
  return useQuery({
    queryKey: ['pos', 'quote', lines, discountPercent],
    queryFn: () => quoteSale({ lines, discount_percent: discountPercent }),
    enabled: lines.length > 0,
    placeholderData: keepPreviousData,
    // ⚠️  بلا إعادة محاولة: الخصم فوق السقف يعيد ٤٠٣، وإعادتها
    //     ثلاث مرات تؤخّر ظهور الرسالة بينما العميل ينتظر.
    retry: false,
    staleTime: 0,
  });
}

export function useCheckout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: {
      lines: SaleLineInput[];
      payments: PaymentInput[];
      discount_percent?: string;
      note?: string;
    }) => checkout(body),
    onSuccess: () => {
      // ⚠️  البيعة تغيّر النقد في الدرج — والتسوية تُبنى عليه.
      void queryClient.invalidateQueries({ queryKey: ['pos', 'cash'] });
    },
  });
}
