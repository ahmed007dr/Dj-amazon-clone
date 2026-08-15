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
    // ⚠️  بلا `staleTime`: الرفع يغيّر القائمة، والأدمن ينتظر أن
    //     يرى صورته فورًا لا بعد دقيقة.
    staleTime: 0,
  });
}

/**
 * ⚠️  **كل طفرة تكتب القائمة العائدة مباشرةً في الكاش.**
 *
 *     الترقية التلقائية للصورة الرئيسية بعد الحذف، وإعادة الترتيب
 *     الجماعية — كلاهما يغيّر صفوفًا لم تلمسها الطفرة. الاكتفاء
 *     بتعديل الصف المعني محليًا يترك الشاشة تعرض حالة لم تعد
 *     موجودة على الخادم.
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
