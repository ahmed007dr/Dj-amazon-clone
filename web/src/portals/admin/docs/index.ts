import { catalogSection } from './content/catalog';
import { gettingStartedSection } from './content/getting-started';
import { operationsSection } from './content/operations';
import { peopleFinanceSection } from './content/people-finance';
import { portalsSection } from './content/portals';
import { pricingSection } from './content/pricing';
import { systemSection } from './content/system';
import type { DocSection } from './types';

/** The guide, in reading order. Each section's content lives in its own file under `content/`. */
export const DOC_SECTIONS: readonly DocSection[] = [
  gettingStartedSection,
  catalogSection,
  pricingSection,
  operationsSection,
  peopleFinanceSection,
  systemSection,
  portalsSection,
];
