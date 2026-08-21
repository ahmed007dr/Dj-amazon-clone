/** Notification contracts — matching `notifications/api.py`. */

export type NotificationCategory =
  | 'ACCOUNT'
  | 'ORDER'
  | 'PAYMENT'
  | 'SHIPPING'
  | 'INVENTORY'
  | 'PROMOTION'
  | 'MARKETING'
  | 'SYSTEM';

export type NotificationChannel = 'IN_APP' | 'EMAIL' | 'SMS' | 'PUSH' | 'WHATSAPP';

export type NotificationPriority = 'LOW' | 'NORMAL' | 'HIGH' | 'URGENT';

/**
 * ⚠️  The text is **copied at the moment of the event, not generated now**
 *     (`Notification` on the server). Which is why it carries no bilingual
 *     fields: a notification is a historical snapshot in the language it was
 *     sent in, and translating it now gives text differing from what arrived by
 *     email at the time.
 */
export interface Notification {
  id: string;
  category: NotificationCategory;
  priority: NotificationPriority;
  title: string;
  body: string;
  /**
   * A path inside the app — opened by tapping the notification.
   *
   * ⚠️  **An empty string, not `null`** when there is no destination
   *     (`blank=True` on the server). A `!== null` check lets the empty one
   *     through, so the notification becomes a link to the root.
   */
  action_url: string;
  reference_type: string;
  reference_id: string;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

/**
 * A preference row.
 *
 * ⚠️  The server returns **every** permitted category × channel combination,
 *     not the stored ones alone — a missing row means "enabled by default", and
 *     showing only what is stored leaves the screen empty for anyone who has
 *     changed nothing.
 */
export interface NotificationPreference {
  category: NotificationCategory;
  category_label: string;
  channel: NotificationChannel;
  channel_label: string;
  is_enabled: boolean;
  /** ⚠️  A mandatory one cannot be disabled: "your account was suspended" is not marketing. */
  is_mandatory: boolean;
}
