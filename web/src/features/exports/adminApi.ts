import { useQuery } from '@tanstack/react-query';

import { http, saveFile } from '@/shared/http';

/**
 * Row-level export.
 *
 * ⚠️  **The catalogue of datasets comes from the server, never from here.**
 *
 *     Which datasets exist, what each one filters by, and whether this user may
 *     see it at all are decided in `reporting/export/registry.py`. A list
 *     retyped in the frontend means a dataset added on the server that no
 *     screen offers — or a button for one the caller has no permission to use,
 *     which 403s and reads as a broken system.
 */

export interface ExportFilter {
  key: string;
  label: string;
  /** 'date' · 'text' · 'choice' · 'bool' */
  kind: string;
  required: boolean;
  /** For 'choice' — the key into `ExportCatalogue.options`. */
  source: string;
  note: string;
}

export interface ExportDataset {
  key: string;
  label: string;
  note: string;
  /** Comes out with the import template's columns — editable and re-uploadable. */
  round_trip: boolean;
  /**
   * ⚠️  True only when the dataset **has** contact columns *and* this user may
   *     export them. Offering a switch that always fails teaches people the
   *     system is unreliable.
   */
  contact_available: boolean;
  filters: ExportFilter[];
}

export interface ExportGroup {
  key: string;
  label: string;
  datasets: ExportDataset[];
}

export interface ExportOption {
  value: string;
  label: string;
}

export interface ExportCatalogue {
  max_rows: number;
  groups: ExportGroup[];
  options: Record<string, ExportOption[]>;
}

const base = '/reports/exports';

export const useExportCatalogue = () =>
  useQuery({
    queryKey: ['exports', 'catalogue'],
    queryFn: () => http.get<ExportCatalogue>(`${base}/`),
    // The catalogue changes with a deployment, not within a session — but the
    // choice lists behind it (locations, brands) change with ordinary work.
    staleTime: 2 * 60 * 1000,
  });

/**
 * Download one dataset.
 *
 * ⚠️  Through `http.download`, never an `<a href>`.
 *
 *     Every dataset is behind a permission, so the request needs the bearer
 *     token — which a plain link does not carry. The browser would open a tab
 *     and show a 401 the admin can do nothing with.
 */
export const downloadExport = async (
  key: string,
  params: Record<string, string> = {},
): Promise<void> => {
  const query = Object.entries(params)
    .filter(([, value]) => value !== '' && value != null)
    .reduce<Record<string, string>>((all, [name, value]) => ({ ...all, [name]: value }), {});

  saveFile(await http.download(`${base}/${key}/`, { params: query }));
};
