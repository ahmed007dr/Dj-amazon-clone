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
    // ⚠️  No `staleTime`: opening and closing the shift change the whole screen,
    //     and showing a closed shift as open makes the cashier sell into a void.
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
 * Closing the shift.
 *
 * ⚠️  **It does not invalidate the shift query — and that is deliberate.**
 *
 *     `/session/` returns `null` after closing, and the shell replaces the
 *     screen with a new open-shift gate the moment it does. Automatic
 *     invalidation snatched away the reconciliation screen at the very instant
 *     it appeared — so the cashier closed their shift **and never saw the cash
 *     discrepancy at all**, the one figure the shift was closed for.
 *
 *     Invalidation becomes a deliberate act: `finish()` after the
 *     reconciliation has been read.
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
    // ⚠️  Keep the previous results while typing.
    //
    //     The list flashing empty between every two characters makes the cashier
    //     think the item does not exist, so they clear and retype — on a screen they use at speed.
    placeholderData: keepPreviousData,
    staleTime: 30 * 1000,
  });
}

/**
 * ⚠️  Pricing is **a server call, not a calculation in the browser**.
 *
 *     Simulating the tiers, the discounts and the variable tax (which may be
 *     absent entirely) here means two figures that diverge — one on the screen
 *     and the other on the receipt.
 */
export function useQuote(lines: SaleLineInput[], discountPercent: string) {
  return useQuery({
    queryKey: ['pos', 'quote', lines, discountPercent],
    queryFn: () => quoteSale({ lines, discount_percent: discountPercent }),
    enabled: lines.length > 0,
    placeholderData: keepPreviousData,
    // ⚠️  No retry: a discount above the cap returns 403, and repeating it
    //     three times delays the message while the customer waits.
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
      // ⚠️  A sale changes the cash in the drawer — and the reconciliation is built on it.
      void queryClient.invalidateQueries({ queryKey: ['pos', 'cash'] });
    },
  });
}
