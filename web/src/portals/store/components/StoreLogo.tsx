import { Link } from 'react-router-dom';

import { BrandLogo } from '@/shared/branding/BrandLogo';
import { useBrand } from '@/shared/branding/useBrand';

import './StoreLogo.css';

/**
 * The store logo.
 *
 * ⚠️  Specific to this portal: it returns to the home page and shows the wordmark
 *     beside it on wide screens. The admin logo does not do this, and the
 *     point-of-sale logo links to no destination at all — hence three files
 *     rather than one file with three conditions.
 */
export function StoreLogo() {
  const { name, tagline } = useBrand();

  return (
    <Link to="/" className="store-logo" aria-label={name}>
      <BrandLogo size="md" />
      {tagline ? <span className="store-logo__tagline desktop-only">{tagline}</span> : null}
    </Link>
  );
}
