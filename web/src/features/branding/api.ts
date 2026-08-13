/**
 * واجهة الهوية البصرية.
 *
 * ⚠️  مسارات نسبية فقط — العنوان الكامل يبنيه `shared/http` وحده.
 */

import { http } from '@/shared/http';
import type { BrandTheme } from '@/shared/theme/types';

export const getTheme = () => http.get<BrandTheme>('/branding/theme/');
