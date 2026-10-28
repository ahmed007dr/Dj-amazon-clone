import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import { useCan } from '@/features/auth/useCan';
import { useTabParam } from '@/shared/hooks/useTabParam';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Button } from '@/shared/ui/Button';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { TabPanel } from '@/shared/ui/TabPanel';
import { AccountsPanel } from '@/portals/admin/components/AccountsPanel';
import { StaffPanel } from '@/portals/admin/components/StaffPanel';

import './AdminPeoplePage.css';

type Tab = 'accounts' | 'staff';

/** The staff tab's permission — also what creating a staff member is gated on. */
const STAFF_PERMISSION = 'employees.change_customerassignment';

/**
 * ⚠️  Each tab declares exactly what the server checks for **its** endpoints, in
 *     the order the tabs appear. The route and the sidebar open for *either*; the
 *     tabs shown are filtered here.
 */
const TABS: readonly { value: Tab; labelKey: string; permission: string }[] = [
  { value: 'accounts', labelKey: 'nav.users', permission: 'accounts.change_user' },
  { value: 'staff', labelKey: 'staff.staffTitle', permission: STAFF_PERMISSION },
];

const TABS_ID = 'people';

/**
 * Users and staff — one screen, a tab for each.
 *
 * ⚠️  **The route opens for either permission; each tab needs its own.**
 *
 *     These used to be two screens with two guards, so someone who held only one
 *     permission reached only that one. Requiring both here would lock them out of
 *     the half they were always allowed; showing both would give them a tab that
 *     answers `403`. So the tabs are filtered by what the user holds, the default
 *     is the first one they may open, and a panel that is not shown is not mounted
 *     — it makes no request the user is not allowed to make.
 *
 * ⚠️  `?tab=` naming a tab the user may not open falls back to their first one
 *     (see `useTabParam`) rather than showing a panel that fails. A bookmark of
 *     `?tab=staff` therefore still opens, on the other half, for a colleague who
 *     lacks the staff permission.
 *
 * ⚠️  **"Add staff member" lives in the header, above both tabs.**
 *
 *     The users tab used to carry a button that only navigated to the staff
 *     screen; with both on one page it just sets the URL (`?tab=staff&add=1`), and
 *     the staff panel — the one that owns the form — opens the drawer from it.
 *     The new member then appears in the list the admin is looking at.
 */
export function AdminPeoplePage() {
  const { t } = useTranslation();
  const can = useCan();
  const [, setParams] = useSearchParams();

  const allowed = TABS.filter((entry) => can(entry.permission));
  const [tab, setTab] = useTabParam<Tab>(
    allowed.map((entry) => entry.value),
    // The route guard guarantees at least one; the fallback only satisfies the type
    allowed[0]?.value ?? 'accounts',
  );

  function addStaff() {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.set('tab', 'staff');
        next.set('add', '1');
        return next;
      },
      { replace: true },
    );
  }

  return (
    <>
      <PageHeader
        title={t('nav.usersAndStaff')}
        description={t('admin.peopleSubtitle')}
        {...(can(STAFF_PERMISSION)
          ? { actions: <Button onClick={addStaff}>{t('staff.addStaff')}</Button> }
          : {})}
      />

      {/* ⚠️  One tab is not a tab bar. Someone who holds only one of the two
          permissions would see a lone label above a panel that has tabs of its
          own, so the bar appears only when there is something to switch between. */}
      {allowed.length > 1 ? (
        <>
          <StatusTabs
            id={TABS_ID}
            label={t('nav.usersAndStaff')}
            value={tab}
            onChange={(next) => {
              setTab(next as Tab);
            }}
            options={allowed.map((entry) => ({ value: entry.value, label: t(entry.labelKey) }))}
          />

          <div className="people-panels">
            <TabPanel id={TABS_ID} value="accounts" active={tab === 'accounts'}>
              <AccountsPanel />
            </TabPanel>
            <TabPanel id={TABS_ID} value="staff" active={tab === 'staff'}>
              <StaffPanel />
            </TabPanel>
          </div>
        </>
      ) : (
        <div className="people-panels">{tab === 'staff' ? <StaffPanel /> : <AccountsPanel />}</div>
      )}
    </>
  );
}
