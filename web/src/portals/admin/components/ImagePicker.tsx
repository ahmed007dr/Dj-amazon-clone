import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';

import './ImagePicker.css';

/** يطابق `ALLOWED_IMAGE_TYPES` على الخادم. */
const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp'];

/** يطابق `MAX_IMAGE_SIZE` — ٥ ميجابايت. */
const MAX_BYTES = 5 * 1024 * 1024;

/**
 * اختيار صورة ومعاينتها قبل الرفع.
 *
 * ⚠️  **الفحص هنا لطف لا حماية.**
 *
 *     الخادم يفحص توقيع الملف نفسه ويرفض ما لا يعرفه. الفحص في
 *     المتصفح موجود ليقول للأدمن «هذا الملف كبير» قبل أن يقضي
 *     دقيقتين في رفعه على شبكة بطيئة — لا ليُعتمد عليه.
 */
export function ImagePicker({
  onPick,
  disabled = false,
}: {
  onPick: (file: File) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);

  const handle = (file: File | undefined) => {
    if (!file) return;

    if (!ACCEPTED.includes(file.type)) {
      setError(t('images.badType'));
      return;
    }
    if (file.size > MAX_BYTES) {
      setError(t('images.tooLarge'));
      return;
    }

    setError(null);
    onPick(file);

    // ⚠️  تصفير القيمة يسمح باختيار **نفس** الملف مرتين.
    //     المتصفح لا يطلق `change` حين لا تتغير القيمة، فيبدو
    //     الزر معطلًا بعد فشل رفعٍ وإعادة المحاولة بنفس الملف.
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <div className="image-picker">
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED.join(',')}
        className="image-picker__input"
        disabled={disabled}
        onChange={(event) => handle(event.target.files?.[0])}
      />
      <Button
        variant="secondary"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
      >
        {t('images.choose')}
      </Button>
      <p className="image-picker__hint">{t('images.hint')}</p>

      {error ? <Alert tone="danger">{error}</Alert> : null}
    </div>
  );
}
