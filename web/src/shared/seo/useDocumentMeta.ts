/**
 * The page's tags — the title, the description, the preview and the structured data.
 *
 * ⚠️  **Runtime injection, with known limits** (ADR-37).
 *
 *     Google executes JavaScript and so reads what is injected here — with a
 *     delay and with no guarantee. Facebook and WhatsApp, by contrast, do not
 *     execute it at all: the preview of a shared product link will stay
 *     incomplete until pre-rendering is implemented. Injecting these tags does
 *     not remove that constraint; it addresses the half of it that concerns search.
 *
 * ⚠️  And no library (`react-helmet`).
 *
 *     The need is four tags and a title. A library with a context provider, an
 *     update queue and a server version — for behaviour written in thirty lines
 *     — is added to the bundle a student downloads on a weak connection.
 *
 * ⚠️  And the injected tags are **marked with `data-managed`**.
 *
 *     Without it they cannot be cleaned up when the page is left, so the tags
 *     for every product the user visited pile up in the same head — and the
 *     crawler reads the first description it finds, which is another page's.
 */

import { useEffect } from 'react';

const MANAGED = 'data-managed-meta';

export interface DocumentMeta {
  title: string;
  description?: string | undefined;
  /** The full image path — for the preview when shared. */
  image?: string | undefined;
  /** `website` for listings · `product` for a product page. */
  type?: 'website' | 'product';
  /**
   * Structured data (JSON-LD).
   *
   * ⚠️  Built in the caller rather than here: its shape differs between a
   *     product, a bundle and a listing, and one function trying to cover them
   *     all becomes a condition inside a condition.
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
    // ⚠️  The data has not arrived yet — no placeholder title is written.
    //
    //     Writing "loading" into the title makes it what appears in the browser tab
    //     and in the history log, and sometimes what a fast crawler picks up.
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
    // ⚠️  `summary_large_image`, not `summary`: the small card crops the product
    //     image to a square that cuts the packaging off on both sides.
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
        // ⚠️  Without query parameters: `?page=2&sort=price` produces dozens of
        //     links for one piece of content, so the crawler splits its weight across copies.
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
 * Cleaning up the injected tags when the page is left.
 *
 * ⚠️  Called once from the application root rather than from every screen: the
 *     tags are rewritten with the new page's values, and removing them on every
 *     navigation means a flash with no description between two screens.
 */
export function clearManagedMeta(): void {
  document.head.querySelectorAll(`[${MANAGED}]`).forEach((element) => {
    element.remove();
  });
}
