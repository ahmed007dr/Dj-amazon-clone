/**
 * وسوم الصفحة — العنوان والوصف والمعاينة والبيانات المنظَّمة.
 *
 * ⚠️  **حقن وقت التشغيل، وحدوده معروفة** (ADR-37).
 *
 *     جوجل ينفّذ JavaScript فيقرأ ما يُحقن هنا — بتأخّر وبلا ضمان.
 *     أما فيسبوك وواتساب فلا ينفّذانه إطلاقًا: معاينة رابط منتج
 *     مُشارَك ستبقى ناقصة حتى يُنفَّذ التوليد المسبق. حقن هذه
 *     الوسوم لا يلغي ذلك القيد؛ يعالج نصفه الذي يخصّ البحث.
 *
 * ⚠️  ولا مكتبة (`react-helmet`).
 *
 *     الحاجة أربعة وسوم وعنوان. مكتبة لها موفّر سياق وطابور
 *     تحديث ونسخة خادم — لسلوك يُكتب في ثلاثين سطرًا — تُضاف إلى
 *     الحزمة التي يحمّلها طالب على شبكة ضعيفة.
 *
 * ⚠️  والوسوم المحقونة **تُوسَم بـ `data-managed`**.
 *
 *     بدونها لا يمكن تنظيفها عند مغادرة الصفحة، فتتراكم وسوم كل
 *     منتج زاره المستخدم في نفس الرأس — ويقرأ المزحف أول وصف
 *     وجده، وهو وصف صفحة أخرى.
 */

import { useEffect } from 'react';

const MANAGED = 'data-managed-meta';

export interface DocumentMeta {
  title: string;
  description?: string | undefined;
  /** مسار الصورة الكامل — للمعاينة عند المشاركة. */
  image?: string | undefined;
  /** `website` للقوائم · `product` لصفحة منتج. */
  type?: 'website' | 'product';
  /**
   * بيانات منظَّمة (JSON-LD).
   *
   * ⚠️  تُبنى في المستدعي لا هنا: شكلها يختلف بين منتج وحزمة
   *     وقائمة، ودالة واحدة تحاول تغطيتها كلها تصير شرطًا داخل شرط.
   */
  jsonLd?: Record<string, unknown> | undefined;
}

function setTag(selector: string, create: () => HTMLElement, apply: (element: HTMLElement) => void) {
  let element = document.head.querySelector<HTMLElement>(selector);

  if (!element) {
    element = create();
    element.setAttribute(MANAGED, '');
    document.head.appendChild(element);
  }

  apply(element);
}

function setMeta(name: string, content: string, property = false) {
  const attribute = property ? 'property' : 'name';

  setTag(
    `meta[${attribute}="${name}"]`,
    () => {
      const meta = document.createElement('meta');
      meta.setAttribute(attribute, name);
      return meta;
    },
    (element) => {
      element.setAttribute('content', content);
    },
  );
}

export function useDocumentMeta(meta: DocumentMeta | null): void {
  const { title, description, image, type, jsonLd } = meta ?? {};
  const serializedJsonLd = jsonLd ? JSON.stringify(jsonLd) : null;

  useEffect(() => {
    // ⚠️  البيانات لم تصل بعد — لا يُكتب عنوان مؤقت.
    //
    //     كتابة «جارٍ التحميل» في العنوان تجعلها ما يظهر في تبويب
    //     المتصفح وفي سجل التاريخ، وأحيانًا ما يلتقطه المزحف السريع.
    if (!title) return;

    const previousTitle = document.title;
    document.title = title;

    const url = window.location.href;

    if (description) {
      setMeta('description', description);
      setMeta('og:description', description, true);
      setMeta('twitter:description', description);
    }

    setMeta('og:title', title, true);
    setMeta('og:type', type ?? 'website', true);
    setMeta('og:url', url, true);
    setMeta('twitter:title', title);
    // ⚠️  `summary_large_image` لا `summary`: البطاقة الصغيرة تقصّ
    //     صورة المنتج إلى مربّع يقطع العبوة من الجانبين.
    setMeta('twitter:card', image ? 'summary_large_image' : 'summary');

    if (image) {
      setMeta('og:image', image, true);
      setMeta('twitter:image', image);
    }

    setTag(
      'link[rel="canonical"]',
      () => {
        const link = document.createElement('link');
        link.setAttribute('rel', 'canonical');
        return link;
      },
      (element) => {
        // ⚠️  بلا معاملات استعلام: `?page=2&sort=price` تنتج عشرات
        //     الروابط لمحتوى واحد، فيوزّع المزحف وزنها على نسخ.
        element.setAttribute('href', `${window.location.origin}${window.location.pathname}`);
      },
    );

    let script: HTMLScriptElement | null = null;
    if (serializedJsonLd) {
      script = document.createElement('script');
      script.type = 'application/ld+json';
      script.textContent = serializedJsonLd;
      script.setAttribute(MANAGED, '');
      document.head.appendChild(script);
    }

    return () => {
      document.title = previousTitle;
      script?.remove();
    };
  }, [title, description, image, type, serializedJsonLd]);
}

/**
 * تنظيف الوسوم المحقونة عند مغادرة الصفحة.
 *
 * ⚠️  يُستدعى مرة واحدة من جذر التطبيق لا من كل شاشة: الوسوم
 *     تُعاد كتابتها بقيم الصفحة الجديدة، والحذف عند كل تنقّل يعني
 *     ومضة بلا وصف بين شاشتين.
 */
export function clearManagedMeta(): void {
  document.head.querySelectorAll(`[${MANAGED}]`).forEach((element) => {
    element.remove();
  });
}
