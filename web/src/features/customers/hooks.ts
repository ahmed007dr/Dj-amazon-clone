import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './api';

const ADDRESSES_KEY = ['customers', 'addresses'] as const;

export function useAddresses(enabled = true) {
  return useQuery({
    queryKey: ADDRESSES_KEY,
    queryFn: api.listAddresses,
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCreateAddress() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.createAddress,
    // ⚠️  Invalidation rather than a direct write: creating a default address clears
    //     another address's default flag on the server, so the whole list changed, not one row.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ADDRESSES_KEY }),
  });
}

/**
 * ⚠️  The same reason as the invalidation on create: editing an address may make
 *     it the default and so clear another's — and the whole list changed, not one row.
 */
function useAddressMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ADDRESSES_KEY }),
  });
}

export function useUpdateAddress() {
  return useAddressMutation(
    ({ id, body }: { id: string; body: Parameters<typeof api.updateAddress>[1] }) =>
      api.updateAddress(id, body),
  );
}

/**
 * ⚠️  The deletion is **soft on the server**: previous orders point at the
 *     address they shipped to, and erasing it leaves every old invoice with no destination.
 */
export function useDeleteAddress() {
  return useAddressMutation(api.deleteAddress);
}

export function useSetDefaultAddress() {
  return useAddressMutation(api.setDefaultAddress);
}
