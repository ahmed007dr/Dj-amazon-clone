/**
 * The visual identity API.
 *
 * ⚠️  Relative paths only — the full URL is built by `shared/http` alone.
 */

import { http } from '@/shared/http';
import type { BrandTheme } from '@/shared/theme/types';

export const getTheme = () => http.get<BrandTheme>('/branding/theme/');
