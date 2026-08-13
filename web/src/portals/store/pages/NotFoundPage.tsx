import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { Button } from '@/shared/ui/Button';
import { StateMessage } from '@/shared/ui/StateMessage';

export function NotFoundPage() {
  const { t } = useTranslation();

  return (
    <div className="container">
      <StateMessage
        icon="⌀"
        title={t('state.notFoundTitle')}
        body={t('state.notFoundBody')}
        action={
          <Button variant="secondary">
            <Link to="/" style={{ color: 'inherit', textDecoration: 'none' }}>
              {t('nav.home')}
            </Link>
          </Button>
        }
      />
    </div>
  );
}
