/**
 * SignupForm.tsx — Account creation form.
 *
 * Validation: zod, on blur and on submit.
 * Password visibility toggle. No password strength meter.
 * Full keyboard path, aria-invalid, aria-describedby.
 */
import React, { useId, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { useAuth } from '@/contexts/AuthContext';
import { DemoPanel } from './DemoPanel';

const schema = z.object({
  fullName: z.string().min(1, 'Name is required'),
  email: z.string().email('Enter a valid email address'),
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .refine(
      (v) => !['password', '12345678', 'password1', 'qwerty123', 'coldfront', 'demo1234'].includes(v.toLowerCase()),
      'This password is too common — choose something less predictable',
    ),
});

type FieldErrors = Partial<Record<keyof z.infer<typeof schema>, string>>;

export function SignupForm() {
  const id = useId();
  const { signup, login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [touched, setTouched] = useState<Partial<Record<string, boolean>>>({});
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [status, setStatus] = useState<'idle' | 'loading'>('idle');

  function validate(values: { fullName: string; email: string; password: string }): FieldErrors {
    const result = schema.safeParse(values);
    if (result.success) return {};
    const errs: FieldErrors = {};
    for (const issue of result.error.issues) {
      const key = issue.path[0] as keyof FieldErrors;
      if (!errs[key]) errs[key] = issue.message;
    }
    return errs;
  }

  function handleBlur(field: string) {
    setTouched((t) => ({ ...t, [field]: true }));
    setFieldErrors(validate({ fullName, email, password }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const values = { fullName: fullName.trim(), email: email.trim(), password };
    const errs = validate(values);
    setFieldErrors(errs);
    setTouched({ fullName: true, email: true, password: true });
    if (Object.keys(errs).length > 0) return;

    setStatus('loading');
    setServerError(null);

    try {
      await signup(values.email, values.password, values.fullName);
      const returnTo = searchParams.get('returnTo');
      const safe = returnTo && returnTo.startsWith('/') && !returnTo.startsWith('//')
        ? returnTo
        : '/tower';
      navigate(safe, { replace: true });
    } catch (err) {
      setStatus('idle');
      const msg = err instanceof Error ? err.message : 'Sign up failed';
      if (msg.includes('409') || msg.toLowerCase().includes('already exists')) {
        setServerError('An account with this email already exists — sign in instead?');
      } else {
        setServerError(msg);
      }
    }
  }

  function handleDemoFill(demoEmail: string, demoPassword: string) {
    // For demo fill on the signup page, switch to login
    navigate(`/login`);
    // The LoginPage will handle the rest
  }

  const isLoading = status === 'loading';

  function renderField(
    label: string,
    fieldKey: keyof FieldErrors,
    type: string,
    value: string,
    onChange: (v: string) => void,
    autoComplete: string,
    extra?: React.ReactNode,
  ) {
    const err = touched[fieldKey] && fieldErrors[fieldKey];
    return (
      <div className="mb-4">
        <label htmlFor={`${id}-${fieldKey}`} className="block text-sm font-medium mb-1" style={{ color: '#1a1814' }}>
          {label}
        </label>
        <div className="relative">
          <input
            id={`${id}-${fieldKey}`}
            type={type}
            autoComplete={autoComplete}
            value={value}
            onChange={(e) => { onChange(e.target.value); setServerError(null); }}
            onBlur={() => handleBlur(fieldKey)}
            aria-describedby={err ? `${id}-${fieldKey}-err` : undefined}
            aria-invalid={err ? true : undefined}
            disabled={isLoading}
            className="w-full rounded px-3 py-2 text-sm outline-none"
            style={{
              background: '#ece8e2',
              border: `1px solid ${err ? '#c0392b' : '#d6d0c8'}`,
              color: '#1a1814',
              minHeight: 44,
              paddingRight: extra ? 52 : undefined,
            }}
            onFocus={(e) => { e.currentTarget.style.boxShadow = '0 0 0 2px #1a7a8a'; }}
            onBlurCapture={(e) => { e.currentTarget.style.boxShadow = 'none'; }}
          />
          {extra}
        </div>
        {err && (
          <p id={`${id}-${fieldKey}-err`} className="mt-1 text-xs" style={{ color: '#c0392b' }} role="alert">
            {fieldErrors[fieldKey]}
          </p>
        )}
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-1" style={{ color: '#1a1814' }}>
        Create account
      </h1>
      <p className="text-sm mb-6" style={{ color: '#6b6560' }}>
        Already have an account?{' '}
        <Link
          to={`/login${searchParams.get('returnTo') ? `?returnTo=${searchParams.get('returnTo')}` : ''}`}
          className="underline"
          style={{ color: '#1a7a8a' }}
        >
          Sign in
        </Link>
      </p>

      <DemoPanel onFill={handleDemoFill} isLoading={isLoading} />

      <form onSubmit={handleSubmit} noValidate>
        {renderField('Name', 'fullName', 'text', fullName, setFullName, 'name')}
        {renderField('Email', 'email', 'email', email, setEmail, 'email')}
        {renderField(
          'Password',
          'password',
          showPassword ? 'text' : 'password',
          password,
          setPassword,
          'new-password',
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded text-xs outline-none focus-visible:ring-2"
            style={{ color: '#6b6560' }}
            aria-label={showPassword ? 'Hide password' : 'Show password'}
          >
            {showPassword ? 'Hide' : 'Show'}
          </button>,
        )}

        <p className="text-xs mb-4" style={{ color: '#6b6560' }}>
          Minimum 8 characters. No need for symbols — just don't use an obvious password.
        </p>

        {serverError && (
          <div
            className="mb-4 px-3 py-2 rounded text-sm"
            style={{ background: '#c0392b20', border: '1px solid #c0392b40', color: '#c0392b' }}
            role="alert"
          >
            {serverError.includes('already exists') ? (
              <>
                {serverError}{' '}
                <Link to="/login" className="underline">
                  Sign in
                </Link>
              </>
            ) : (
              serverError
            )}
          </div>
        )}

        <button
          type="submit"
          disabled={isLoading}
          className="w-full rounded px-4 py-2 text-sm font-medium transition-colors duration-75 outline-none focus-visible:ring-2 disabled:opacity-60"
          style={{ background: '#1a1814', color: '#f5f2ee', minHeight: 44 }}
          onMouseOver={(e) => { if (!isLoading) (e.currentTarget as HTMLButtonElement).style.background = '#2d2926'; }}
          onMouseOut={(e) => { (e.currentTarget as HTMLButtonElement).style.background = '#1a1814'; }}
        >
          {isLoading ? 'Creating account…' : 'Create account'}
        </button>
      </form>
    </div>
  );
}
