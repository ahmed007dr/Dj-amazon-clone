import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  deleteProductImage,
  listProductImages,
  reorderProductImages,
  setPrimaryImage,
  uploadProductImage,
  type ProductImage,
} from './imagesApi';

const key = (productId: string) => ['admin', 'product-images', productId];

export function useProductImages(productId: string, enabled = true) {
  return useQuery({
    queryKey: key(productId),
    queryFn: () => listProductImages(productId),
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
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key(productId) }),
  });
}

export function useUploadImage(productId: string) {
  return useImagesMutation<{ file: File; ar: string; en: string }>(
    productId,
    ({ file, ar, en }) => uploadProductImage(productId, file, { ar, en }),
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

export function useReorderImages(productId: string) {
  return useImagesMutation<string[]>(productId, (order) =>
    reorderProductImages(productId, order),
  );
}

export type { ProductImage };
