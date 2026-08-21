import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';

import './ImagePicker.css';

/** Matches `ALLOWED_IMAGE_TYPES` on the server. */
const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp'];

/** Matches `MAX_IMAGE_SIZE` — 5 MB. */
const MAX_BYTES = 5 * 1024 * 1024;

/**
 * Choosing an image and previewing it before upload.
 *
 * ⚠️  **The check here is a courtesy, not a protection.**
 *
 *     The server checks the file's own signature and refuses what it does not
 *     recognise. The check in the browser exists to tell the admin "this file
 *     is large" before they spend two minutes uploading it on a slow connection
 *     — not to be relied on.
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

    // ⚠️  Resetting the value allows **the same** file to be chosen twice.
    //     The browser does not fire `change` when the value is unchanged, so the
    //     button looks disabled after a failed upload and a retry with the same file.
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
