import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  getTaxSettings,
  listTaxClasses,
  setDefaultTaxClass,
  updateTaxClass,
  updateTaxSettings,
  type TaxClass,
  type TaxSettings,
} from '@/features/administration/tax';
import { isApiError } from '@/shared/http';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/useToast';

import './AdminTaxPage.css';

const KEY = ['admin', 'tax'] as const;

/**
 * Tax.
 *
 * ⚠️  **Changing the rate does not touch orders already issued.**
 *
 *     Every line carries its rate at the time of sale (ADR-30), and the effect
 *     starts with the next order. Saying so on the screen prevents a legitimate
 *     fear of pressing, and prevents a false expectation that the old reports
 *     will change.
 */
export function AdminTaxPage() {
  const { t } = useTranslation();
  const localized = useLocalized();
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const classes = useQuery({ queryKey: [...KEY, 'classes'], queryFn: listTaxClasses });
  const settings = useQuery({ queryKey: [...KEY, 'settings'], queryFn: getTaxSettings });

  const [form, setForm] = useState<TaxSettings | null>(null);
  const [editing, setEditing] = useState<Record<string, string>>({});

  useEffect(() => {
    if (settings.data) setForm(settings.data);
  }, [settings.data]);

  const saveSettings = useMutation({
    mutationFn: (body: TaxSettings) => updateTaxSettings(body),
    onSuccess: () => {
      notify(t('account.saved'));
      void queryClient.invalidateQueries({ queryKey: KEY });
    },
    onError: (cause) => {
      notify(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'), 'danger');
    },
  });

  const saveRate = useMutation({
    mutationFn: (args: { id: string; rate: string }) =>
      updateTaxClass(args.id, { rate: args.rate }),
    onSuccess: () => {
      notify(t('admin.rateSaved'));
      void queryClient.invalidateQueries({ queryKey: KEY });
      setEditing({});
    },
    onError: (cause) => {
      notify(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'), 'danger');
    },
  });

  const makeDefault = useMutation({
    mutationFn: setDefaultTaxClass,
    onSuccess: () => {
      notify(t('account.saved'));
      void queryClient.invalidateQueries({ queryKey: KEY });
    },
  });

  if (classes.isPending || !form) return <Spinner />;

  const columns: Column<TaxClass>[] = [
    {
      key: 'name',
      header: t('admin.taxClass'),
      render: (item) => (
        <span>
          <strong>{localized(item, 'name')}</strong> <code style={{ direction: 'ltr' }}>{item.code}</code>
        </span>
      ),
    },
    {
      key: 'rate',
      header: t('admin.rate'),
      align: 'end',
      render: (item) => (
        <span className="tax-rate">
          <input
            type="number"
            className="tax-rate__input"
            min={0}
            max={100}
            step="0.01"
            value={editing[item.id] ?? item.rate}
            aria-label={t('admin.rate')}
            onChange={(event) => {
              setEditing((current) => ({ ...current, [item.id]: event.target.value }));
            }}
          />
          <span className="muted">%</span>
        </span>
      ),
    },
    {
      key: 'products',
      header: t('admin.affectedProducts'),
      align: 'end',
      // ⚠️  The count before the edit turns the decision from a guess into knowledge
      render: (item) => item.product_count,
    },
    {
      key: 'validity',
      header: t('admin.validity'),
      render: (item) =>
        item.is_currently_valid ? (
          <Badge tone="success">{t('admin.valid')}</Badge>
        ) : (
          <Badge tone="warning">{t('admin.notValid')}</Badge>
        ),
    },
    {
      key: 'default',
      header: t('admin.defaultClass'),
      render: (item) =>
        item.is_default ? (
          <Badge tone="info">{t('account.default')}</Badge>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              makeDefault.mutate(item.id);
            }}
          >
            {t('admin.makeDefault')}
          </Button>
        ),
    },
    {
      key: 'save',
      header: t('common.save'),
      align: 'end',
      render: (item) =>
        editing[item.id] !== undefined && editing[item.id] !== item.rate ? (
          <Button
            size="sm"
            loading={saveRate.isPending}
            onClick={() => {
              saveRate.mutate({ id: item.id, rate: editing[item.id] as string });
            }}
          >
            {t('common.save')}
          </Button>
        ) : null,
    },
  ];

  return (
    <>
      <PageHeader title={t('admin.tax')} description={t('admin.taxHint')} />

      <Alert tone="info">{t('admin.taxSnapshotNote')}</Alert>

      <section className="surface tax-settings">
        <h2 className="tax-settings__title">{t('admin.taxSettings')}</h2>

        <label className="tax-settings__row">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(event) => {
              setForm({ ...form, enabled: event.target.checked });
            }}
          />
          <span>
            <strong>{t('admin.taxEnabled')}</strong>
            <span className="muted">{t('admin.taxEnabledHint')}</span>
          </span>
        </label>

        <label className="tax-settings__row">
          <input
            type="checkbox"
            checked={form.prices_include_tax}
            onChange={(event) => {
              setForm({ ...form, prices_include_tax: event.target.checked });
            }}
          />
          <span>
            <strong>{t('admin.pricesIncludeTax')}</strong>
            <span className="muted">{t('admin.pricesIncludeTaxHint')}</span>
          </span>
        </label>

        <Button
          loading={saveSettings.isPending}
          onClick={() => {
            saveSettings.mutate(form);
          }}
        >
          {t('common.save')}
        </Button>
      </section>

      <h2 className="tax-classes__title">{t('admin.taxClasses')}</h2>
      <DataTable
        columns={columns}
        rows={classes.data ?? []}
        rowKey={(item) => item.id}
        error={classes.error}
      />
    </>
  );
}
