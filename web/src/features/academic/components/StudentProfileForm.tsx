import { useMemo, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/shared/http';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import { useCreateStudentProfile, useUniversities, useUpdateStudentProfile } from '../hooks';
import type { StudentProfile } from '../types';

import './StudentProfileForm.css';

/**
 * الملف الأكاديمي — إنشاء وتعديل.
 *
 * ⚠️  **التسلسل متتالٍ لا أربع قوائم مستقلة.**
 *
 *     الخادم يرفض كلية لا تتبع الجامعة، وقسمًا لا يتبع الكلية،
 *     وسنةً تتجاوز سنوات الكلية (`StudentProfile.clean`). عرض
 *     القوائم كاملة يجعل الطالب يختار تركيبة مستحيلة ثم يقرأ خطأ
 *     خادم لا يفهم سببه — فتُشتق كل قائمة مما قبلها، ويُمسح ما
 *     بعدها عند التغيير.
 *
 * ⚠️  والسنة تُشتق من `years_count` للكلية المختارة: كلية الصيدلة
 *     خمس سنوات، والطب ست. قائمة ثابتة من ١ إلى ٦ تعطي طالب صيدلة
 *     سنةً سادسة لا وجود لها، وحزمًا فارغة إلى الأبد.
 */
export function StudentProfileForm({
  profile,
  onDone,
}: {
  profile: StudentProfile | null;
  onDone?: () => void;
}) {
  const { t } = useTranslation();
  const localized = useLocalized();

  const { data: universities, isPending, error: loadError } = useUniversities();
  const createProfile = useCreateStudentProfile();
  const updateProfile = useUpdateStudentProfile();

  const [form, setForm] = useState({
    university: profile?.university ?? '',
    faculty: profile?.faculty ?? '',
    department: profile?.department ?? '',
    academic_year: profile ? String(profile.academic_year) : '',
    student_number: profile?.student_number ?? '',
  });
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const faculties = useMemo(
    () => universities?.find((one) => one.id === form.university)?.faculties ?? [],
    [universities, form.university],
  );

  const faculty = useMemo(
    () => faculties.find((one) => one.id === form.faculty),
    [faculties, form.faculty],
  );

  const years = useMemo(
    () => Array.from({ length: faculty?.years_count ?? 0 }, (_, index) => index + 1),
    [faculty],
  );

  if (isPending) return <Spinner />;
  if (loadError) return <StateMessage icon="⚠" title={t('state.errorTitle')} />;

  if (universities.length === 0) {
    return <StateMessage icon="🎓" title={t('academic.noUniversities')} />;
  }

  /** ⚠️  تغيير الجامعة يُسقط الكلية والقسم والسنة — لا يبقيها معلّقة. */
  function pickUniversity(value: string) {
    setForm((current) => ({
      ...current,
      university: value,
      faculty: '',
      department: '',
      academic_year: '',
    }));
  }

  function pickFaculty(value: string) {
    setForm((current) => ({ ...current, faculty: value, department: '', academic_year: '' }));
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});

    const payload = {
      university: form.university,
      faculty: form.faculty,
      // ⚠️  `null` لا سلسلة فارغة: الخادم يقبل الغياب لا النص الفارغ
      department: form.department || null,
      academic_year: Number(form.academic_year),
      student_number: form.student_number,
    };

    const mutation = profile ? updateProfile : createProfile;

    mutation.mutate(payload, {
      onSuccess: () => onDone?.(),
      onError: (cause) => {
        if (isApiError(cause)) {
          const fields = Object.fromEntries(
            Object.entries(cause.fields).map(([name, list]) => [name, list[0]?.message ?? '']),
          );
          setFieldErrors(fields);
          if (Object.keys(fields).length === 0) setError(cause.displayMessage);
        } else {
          setError(t('state.errorTitle'));
        }
      },
    });
  }

  const saving = createProfile.isPending || updateProfile.isPending;

  return (
    <form className="student-form" onSubmit={handleSubmit} noValidate>
      {error ? <Alert tone="danger">{error}</Alert> : null}

      <div className="student-form__field">
        <label className="student-form__label" htmlFor="university">
          {t('academic.university')}
        </label>
        <select
          id="university"
          className="student-form__select"
          required
          value={form.university}
          onChange={(event) => {
            pickUniversity(event.target.value);
          }}
        >
          <option value="">{t('academic.pickUniversity')}</option>
          {universities.map((university) => (
            <option key={university.id} value={university.id}>
              {localized(university, 'name')}
            </option>
          ))}
        </select>
        {fieldErrors.university ? (
          <p className="student-form__error" role="alert">
            {fieldErrors.university}
          </p>
        ) : null}
      </div>

      <div className="student-form__field">
        <label className="student-form__label" htmlFor="faculty">
          {t('academic.faculty')}
        </label>
        <select
          id="faculty"
          className="student-form__select"
          required
          disabled={!form.university}
          value={form.faculty}
          onChange={(event) => {
            pickFaculty(event.target.value);
          }}
        >
          <option value="">{t('academic.pickFaculty')}</option>
          {faculties.map((one) => (
            <option key={one.id} value={one.id}>
              {localized(one, 'name')}
            </option>
          ))}
        </select>
        {fieldErrors.faculty ? (
          <p className="student-form__error" role="alert">
            {fieldErrors.faculty}
          </p>
        ) : null}
      </div>

      {/* ⚠️  القسم يظهر فقط حين تملك الكلية أقسامًا — قائمة فارغة
          تجعل الطالب يظن أن عليه اختيار شيء لا وجود له. */}
      {faculty && faculty.departments.length > 0 ? (
        <div className="student-form__field">
          <label className="student-form__label" htmlFor="department">
            {t('academic.department')}
          </label>
          <select
            id="department"
            className="student-form__select"
            value={form.department}
            onChange={(event) => {
              setForm((current) => ({ ...current, department: event.target.value }));
            }}
          >
            <option value="">{t('academic.noDepartment')}</option>
            {faculty.departments.map((one) => (
              <option key={one.id} value={one.id}>
                {localized(one, 'name')}
              </option>
            ))}
          </select>
          {fieldErrors.department ? (
            <p className="student-form__error" role="alert">
              {fieldErrors.department}
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="student-form__field">
        <label className="student-form__label" htmlFor="academic_year">
          {t('academic.academicYear')}
        </label>
        <select
          id="academic_year"
          className="student-form__select"
          required
          disabled={!form.faculty}
          value={form.academic_year}
          onChange={(event) => {
            setForm((current) => ({ ...current, academic_year: event.target.value }));
          }}
        >
          <option value="">{t('academic.pickYear')}</option>
          {years.map((year) => (
            <option key={year} value={year}>
              {t('academic.year', { count: year })}
            </option>
          ))}
        </select>
        {fieldErrors.academic_year ? (
          <p className="student-form__error" role="alert">
            {fieldErrors.academic_year}
          </p>
        ) : null}
      </div>

      <Field
        label={t('academic.studentNumber')}
        hint={t('academic.studentNumberHint')}
        value={form.student_number}
        error={fieldErrors.student_number}
        onChange={(event) => {
          setForm((current) => ({ ...current, student_number: event.target.value }));
        }}
      />

      <div className="student-form__actions">
        <Button type="submit" loading={saving} disabled={!form.faculty || !form.academic_year}>
          {t('common.save')}
        </Button>
        {onDone ? (
          <Button type="button" variant="ghost" onClick={onDone}>
            {t('common.cancel')}
          </Button>
        ) : null}
      </div>
    </form>
  );
}
