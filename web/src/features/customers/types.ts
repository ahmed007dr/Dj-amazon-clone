/** عقود العملاء — تطابق `customers/serializers.py`. */

export interface CustomerAddress {
  id: string;
  label: string;
  recipient_name: string;
  phone: string;
  governorate: string;
  city: string;
  street: string;
  building: string;
  landmark: string;
  is_default: boolean;
  created_at: string;
}

export type AddressInput = Omit<CustomerAddress, 'id' | 'created_at'>;
