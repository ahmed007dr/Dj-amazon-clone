import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  deleteProductImage,
  listProductImages,
  reorderProductImages,
  setPrimaryImage,
  uploadProductImage,
  type ProductImage,
} from './imagesApi';

/**
 * ⚠️  The colour is part of the key: the base gallery and each colour's gallery are
 *     different lists, and sharing a key would show one colour's photos in another's panel.
 *     Invalidating the bare product prefix still refreshes all of them.
 */
const key = (productId: string, colorId?: string) => [
  'admin',
  'product-images',
  productId,
  colorId ?? 'base',
];

export function useProductImages(productId: string, enabled = true, colorId?: string) {
  return useQuery({
    queryKey: key(productId, colorId),
    queryFn: () => listProductImages(productId, colorId),
    enabled,
    // ⚠️  No `staleTime`: uploading changes the list, and the admin expects to
    //     see their image immediately, not a minute later.
    staleTime: 0,
  });
}

/**
 * ⚠️  **Every mutation writes the returned list straight into the cache.**
 *
 *     The automatic promotion of the primary image after a deletion, and the
 *     bulk reordering — both change rows the mutation never touched. Editing
 *     only the affected row locally leaves the screen showing a state that no
 *     longer exists on the server.
 */
function useImagesMutation<TArgs>(
  productId: string,
  run: (args: TArgs) => Promise<unknown>,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      // The whole product prefix: a colour's image count and thumbnail live in the
      // colours list, and the base gallery may have been affected too.
      void queryClient.invalidateQueries({ queryKey: ['admin', 'product-images', productId] });
      void queryClient.invalidateQueries({ queryKey: ['admin', 'product-colors', productId] });
    },
  });
}

export function useUploadImage(productId: string, colorId?: string) {
  return useImagesMutation<{ file: File; ar: string; en: string }>(
    productId,
    ({ file, ar, en }) => uploadProductImage(productId, file, { ar, en }, colorId),
  );
}

export function useDeleteImage(productId: string) {
  return useImagesMutation<string>(productId, (imageId) =>
    deleteProductImage(productId, imageId),
  );
}

export function useSetPrimary(productId: string) {
  return useImagesMutation<string>(productId, (imageId) =>
    setPrimaryImage(productId, imageId),
  );
}

export function useReorderImages(productId: string, colorId?: string) {
  return useImagesMutation<string[]>(productId, (order) =>
    reorderProductImages(productId, order, colorId),
  );
}

export type { ProductImage };
