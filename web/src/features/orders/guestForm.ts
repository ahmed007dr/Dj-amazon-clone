/** What the guest checkout form holds — the payload is built from it at submit time. */
export interface GuestFormValues {
  recipient_name: string;
  phone: string;
  email: string;
  governorate: string;
  city: string;
  street: string;
  customer_note: string;
  /** ⚠️  The honeypot — always empty from a real browser. */
  website: string;
}

export const EMPTY_GUEST_FORM: GuestFormValues = {
  recipient_name: '',
  phone: '',
  email: '',
  governorate: '',
  city: '',
  street: '',
  customer_note: '',
  website: '',
};

/**
 * An Egyptian mobile — the same shape the server accepts (010 / 011 / 012 / 015,
 * with or without +20), after Arabic-Indic digits and separators are normalised.
 *
 * ⚠️  Only a convenience. The server is the judge; this just says "that does not
 *     look like a mobile number" before a round trip, and is deliberately no
 *     stricter than the server, so it never blocks a number the server accepts.
 */
export function looksLikeEgyptianMobile(raw: string): boolean {
  const digits = raw
    .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660))
    .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0))
    .replace(/[\s\-().]/g, '');
  return /^(?:\+?20|0020|0)?1[0125]\d{8}$/.test(digits);
}
