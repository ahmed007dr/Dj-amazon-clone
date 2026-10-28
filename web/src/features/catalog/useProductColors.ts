import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createColor,
  deleteColor,
  listColors,
  reorderColors,
  updateColor,
  type ColorInput,
} from './colorsApi';

const key = (productId: string) => ['admin', 'product-colors', productId];

export function useProductColors(productId: string) {
  return useQuery({
    queryKey: key(productId),
    queryFn: () => listColors(productId),
    // ⚠️  No `staleTime`, as for the images: the admin expects what they just did to show.
    staleTime: 0,
  });
}

/**
 * ⚠️  A colour change also invalidates the public catalogue and the inventory screens.
 *
 *     A new colour is a new variant with no stock (so the product page shows a sold-out
 *     swatch), and a hidden one disappears from the storefront. Leaving the storefront's
 *     two-minute cache alone means the admin opens the shop to check and sees yesterday.
 */
function useColorMutation<TArgs>(productId: string, run: (args: TArgs) => Promise<unknown>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: key(productId) });
      void queryClient.invalidateQueries({ queryKey: ['catalog'] });
      void queryClient.invalidateQueries({ queryKey: ['inventory'] });
    },
  });
}

export function useCreateColor(productId: string) {
  return useColorMutation<ColorInput>(productId, (body) => createColor(productId, body));
}

export function useUpdateColor(productId: string) {
  return useColorMutation<{ id: string; body: Partial<ColorInput> }>(productId, ({ id, body }) =>
    updateColor(productId, id, body),
  );
}

export function useDeleteColor(productId: string) {
  return useColorMutation<{ id: string; force?: boolean }>(productId, ({ id, force }) =>
    deleteColor(productId, id, force),
  );
}

export function useReorderColors(productId: string) {
  return useColorMutation<string[]>(productId, (order) => reorderColors(productId, order));
}
