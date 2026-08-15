/** عقود الإشعارات — تطابق `notifications/api.py`. */

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
 * ⚠️  النص **منسوخ لحظة الحدث لا مُولَّد الآن** (`Notification` في
 *     الخادم). ولذلك لا يحمل حقولًا ثنائية اللغة: الإشعار لقطة
 *     تاريخية بلغة أُرسل بها، وترجمته الآن تعطي نصًّا يخالف ما
 *     وصل بالبريد في حينه.
 */
export interface Notification {
  id: string;
  category: NotificationCategory;
  priority: NotificationPriority;
  title: string;
  body: string;
  /**
   * مسار داخل التطبيق — يفتحه الضغط على الإشعار.
   *
   * ⚠️  **سلسلة فارغة لا `null`** حين لا وجهة (`blank=True` في
   *     الخادم). فحص `!== null` يمرّر الفارغة فيصير الإشعار رابطًا
   *     إلى الجذر.
   */
  action_url: string;
  reference_type: string;
  reference_id: string;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

/**
 * صف تفضيل.
 *
 * ⚠️  الخادم يعيد **كل** تركيبة تصنيف × قناة مسموحة لا المخزَّنة
 *     وحدها — غياب الصف يعني «مفعّل افتراضيًا»، وعرض المخزَّن
 *     وحده يجعل الشاشة فارغة لمن لم يغيّر شيئًا.
 */
export interface NotificationPreference {
  category: NotificationCategory;
  category_label: string;
  channel: NotificationChannel;
  channel_label: string;
  is_enabled: boolean;
  /** ⚠️  الإلزامي لا يُوقَف: «أُوقف حسابك» ليست تسويقًا. */
  is_mandatory: boolean;
}
