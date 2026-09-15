/**
 * LoginForm.tsx — Email + password login form.
 *
 * Validation: zod, on blur and on submit. Never on keystroke.
 * Errors describe what to do, not what went wrong abstractly.
 * Submit button shows pending state and is disabled during flight.
 * Full keyboard path with visible focus, aria-invalid, aria-describedby.
 */
import React, { useId, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { useAuth } from '@/contexts/AuthContext';
import { DemoPanel } from './DemoPanel';

const schema = z.object({
  email: z.string().email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
});

type FieldErrors = Partial<Record<keyof z.infer<typeof schema>, string>>;

export function LoginForm() {
  const id = useId();
  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [touched, setTouched] = useState<Partial<Record<string, boolean>>>({});
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [status, setStatus] = useState<'idle' | 'loading' | 'success'>('idle');

  const emailRef = useRef<HTMLInputElement>(null);

  function validate(values: { email: string; password: string }): FieldErrors {
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
    const errs = validate({ email, password });
    setFieldErrors(errs);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const values = { email: email.trim(), password };
    const errs = validate(values);
    setFieldErrors(errs);
    setTouched({ email: true, password: true });
    if (Object.keys(errs).length > 0) return;

    setStatus('loading');
    setServerError(null);

    try {
      await login(values.email, values.password);
      setStatus('success');
      const returnTo = searchParams.get('returnTo');
      const safe = returnTo && returnTo.startsWith('/') && !returnTo.startsWith('//')
        ? returnTo
        : '/tower';
      navigate(safe, { replace: true });
    } catch (err) {
      setStatus('idle');
      const msg = err instanceof Error ? err.message : 'Sign in failed';
      if (msg.includes('429') || msg.toLowerCase().includes('too many')) {
        const match = msg.match(/(\d+) seconds/);
        setServerError(`Too many attempts — try again in ${match ? match[0] : 'a few minutes'}`);
      } else if (msg.includes('401') || msg.toLowerCase().includes('incorrect')) {
        setServerError('Incorrect email or password');
      } else {
        setServerError(msg);
      }
    }
  }

  function handleDemoFill(demoEmail: string, demoPassword: string) {
    setEmail(demoEmail);
    setPassword(demoPassword);
    setFieldErrors({});
    setServerError(null);
    // Auto-submit after state settles
    setTimeout(() => {
      const form = emailRef.current?.closest('form');
      form?.requestSubmit();
    }, 0);
  }

  const isLoading = status === 'loading';
  const showEmailError = touched.email && fieldErrors.email;
  const showPasswordError = touched.password && fieldErrors.password;

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-1" style={{ color: '#1a1814' }}>
        Sign in
      </h1>
      <p className="text-sm mb-6" style={{ color: '#6b6560' }}>
        New here?{' '}
        <Link
          to={`/signup${searchParams.get('returnTo') ? `?returnTo=${searchParams.get('returnTo')}` : ''}`}
          className="underline"
          style={{ color: '#1a7a8a' }}
        >
          Create an account
        </Link>
      </p>

      <DemoPanel onFill={handleDemoFill} isLoading={isLoading} />

      <form onSubmit={handleSubmit} noValidate>
        {/* Email */}
        <div className="mb-4">
          <label
            htmlFor={`${id}-email`}
            className="block text-sm font-medium mb-1"
            style={{ color: '#1a1814' }}
          >
            Email
          </label>
          <input
            ref={emailRef}
            id={`${id}-email`}
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => { setEmail(e.target.value); setServerError(null); }}
            onBlur={() => handleBlur('email')}
            aria-describedby={showEmailError ? `${id}-email-err` : undefined}
            aria-invalid={showEmailError ? true : undefined}
            disabled={isLoading}
            className="w-full rounded px-3 py-2 text-sm outline-none transition-shadow"
            style={{
              background: '#ece8e2',
              border: `1px solid ${showEmailError ? '#c0392b' : '#d6d0c8'}`,
              color: '#1a1814',
              minHeight: 44,
            }}
            onFocus={(e) => { e.currentTarget.style.boxShadow = '0 0 0 2px #1a7a8a'; }}
            onBlurCapture={(e) => { e.currentTarget.style.boxShadow = 'none'; }}
          />
          {showEmailError && (
            <p id={`${id}-email-err`} className="mt-1 text-xs" style={{ color: '#c0392b' }} role="alert">
              {fieldErrors.email}
            </p>
          )}
        </div>

        {/* Password */}
        <div className="mb-5">
          <label
            htmlFor={`${id}-password`}
            className="block text-sm font-medium mb-1"
            style={{ color: '#1a1814' }}
          >
            Password
          </label>
          <div className="relative">
            <input
              id={`${id}-password`}
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              value={password}
              onChange={(e) => { setPassword(e.target.value); setServerError(null); }}
              onBlur={() => handleBlur('password')}
              aria-describedby={showPasswordError ? `${id}-password-err` : undefined}
              aria-invalid={showPasswordError ? true : undefined}
              disabled={isLoading}
              className="w-full rounded px-3 py-2 pr-10 text-sm outline-none"
              style={{
                background: '#ece8e2',
                border: `1px solid ${showPasswordError ? '#c0392b' : '#d6d0c8'}`,
                color: '#1a1814',
                minHeight: 44,
              }}
              onFocus={(e) => { e.currentTarget.style.boxShadow = '0 0 0 2px #1a7a8a'; }}
              onBlurCapture={(e) => { e.currentTarget.style.boxShadow = 'none'; }}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded text-xs outline-none focus-visible:ring-2"
              style={{ color: '#6b6560' }}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? 'Hide' : 'Show'}
            </button>
          </div>
          {showPasswordError && (
            <p id={`${id}-password-err`} className="mt-1 text-xs" style={{ color: '#c0392b' }} role="alert">
              {fieldErrors.password}
            </p>
          )}
        </div>

        {/* Server error */}
        {serverError && (
          <div
            className="mb-4 px-3 py-2 rounded text-sm"
            style={{ background: '#c0392b20', border: '1px solid #c0392b40', color: '#c0392b' }}
            role="alert"
          >
            {serverError.includes('Incorrect') ? (
              <>
                {serverError} —{' '}
                <Link to="/signup" className="underline">
                  sign up instead
                </Link>
                ?
              </>
            ) : (
              serverError
            )}
          </div>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={isLoading}
          className="w-full rounded px-4 py-2 text-sm font-medium transition-colors duration-75 outline-none focus-visible:ring-2 disabled:opacity-60"
          style={{
            background: '#1a1814',
            color: '#f5f2ee',
            minHeight: 44,
          }}
          onMouseOver={(e) => { if (!isLoading) (e.currentTarget as HTMLButtonElement).style.background = '#2d2926'; }}
          onMouseOut={(e) => { (e.currentTarget as HTMLButtonElement).style.background = '#1a1814'; }}
        >
          {isLoading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}
