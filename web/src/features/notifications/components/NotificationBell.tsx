import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useAuth } from '@/features/auth/useAuth';

import { useUnreadCount } from '../hooks';

import './NotificationBell.css';

/**
 * جرس الإشعارات.
 *
 * ⚠️  **لا يظهر للزائر إطلاقًا.**
 *
 *     نقطة العدّاد تتطلب توكنًا؛ عرض الجرس لغير المسجَّل يعني
 *     `401` متكرّرًا كل دقيقة، وكل واحد منها يستدعي محاولة تجديد
 *     جلسة لا وجود لها.
 *
 * ⚠️  ورابط لا زر بقائمة منسدلة: القائمة المنسدلة تحتاج إدارة
 *     تركيز ومصيدة لوحة مفاتيح وإغلاقًا بالنقر خارجها — وكلها
 *     تُبنى مرة واحدة في الشاشة الكاملة بدل نسختين تتباعدان.
 */
export function NotificationBell() {
  const { t } = useTranslation();
  const { user } = useAuth();

  const { data } = useUnreadCount(user !== null);

  if (!user) return null;

  const unread = data?.unread ?? 0;

  return (
    <Link
      to="/account/notifications"
      className="notification-bell"
      aria-label={t('notifications.title')}
    >
      <span className="notification-bell__icon" aria-hidden>
        ✉
      </span>

      {/* ⚠️  الصفر لا يُعرض — «٠» تُقرأ كعنصر معطّل لا كـ«لا جديد». */}
      {unread > 0 ? (
        <span className="notification-bell__count" aria-hidden>
          {unread > 99 ? '99+' : unread}
        </span>
      ) : null}

      <span className="visually-hidden">{t('notifications.unreadCount', { count: unread })}</span>
    </Link>
  );
}
