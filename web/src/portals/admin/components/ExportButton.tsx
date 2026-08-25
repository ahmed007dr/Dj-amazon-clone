import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { downloadExport } from '@/features/exports/adminApi';
import { isApiError } from '@/shared/http/errors';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';

/**
 * Export what is on screen right now.
 *
 * ⚠️  **It carries the caller's current filters, and that is the whole point.**
 *
 *     An admin who has narrowed stock to "below reorder point at the Nasr City
 *     branch" and is staring at the result wants that list, not a trip to
 *     another screen to rebuild the same three filters. The catalogue page is
 *     for discovering what exists; this is for the moment the answer is already
 *     on screen.
 *
 * ⚠️  Here the error **is** a toast, unlike on the catalogue card.
 *
 *     There the message is an instruction about filter controls sitting
 *     directly above it, so it belongs beside them. Here the filters are the
 *     page's own, the button is one control in a header, and there is nowhere
 *     to put a panel that would not push the table around.
 */
export function ExportButton({
  dataset,
  params = {},
  label,
  size = 'sm',
}: {
  dataset: string;
  params?: Record<string, string | undefined>;
  label?: string;
  size?: 'sm' | 'md';
}) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      // ⚠️  Undefined values are dropped rather than sent empty. `?status=` means
      //     "filter by an empty status" to the server, not "no filter" — the
      //     same rule the http client applies to every other query string.
      const clean = Object.entries(params).reduce<Record<string, string>>(
        (all, [key, value]) => (value ? { ...all, [key]: value } : all),
        {},
      );
      await downloadExport(dataset, clean);
    } catch (cause) {
      notify(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'), 'danger');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button variant="secondary" size={size} loading={busy} onClick={() => void run()}>
      {label ?? t('exports.action')}
    </Button>
  );
}
