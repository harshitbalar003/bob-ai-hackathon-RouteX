import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md';
  children: React.ReactNode;
}

const VARIANT_STYLES: Record<NonNullable<ButtonProps['variant']>, string> = {
  primary:
    'bg-accent-tracking text-surface-base font-medium hover:bg-accent-tracking/90 focus-visible:ring-accent-tracking',
  secondary:
    'bg-surface-raised text-text-primary border border-surface-border hover:bg-surface-border focus-visible:ring-accent-minor',
  ghost:
    'bg-transparent text-text-muted hover:text-text-primary hover:bg-surface-raised focus-visible:ring-accent-minor',
  danger:
    'bg-accent-critical/10 text-accent-critical border border-accent-critical/30 hover:bg-accent-critical/20 focus-visible:ring-accent-critical',
};

const SIZE_STYLES: Record<NonNullable<ButtonProps['size']>, string> = {
  sm: 'px-2.5 py-1 text-sm',
  md: 'px-4 py-1.5 text-base',
};

export function Button({
  variant = 'secondary',
  size = 'md',
  className = '',
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded
        transition-colors duration-100 outline-none
        focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-offset-surface-base
        disabled:opacity-40 disabled:cursor-not-allowed
        ${VARIANT_STYLES[variant]} ${SIZE_STYLES[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  label: string; // aria-label — required for icon-only buttons
  children: React.ReactNode;
}

export function IconButton({ label, children, className = '', ...props }: IconButtonProps) {
  return (
    <button
      aria-label={label}
      className={`inline-flex items-center justify-center p-1.5 rounded text-text-muted
        hover:text-text-primary hover:bg-surface-raised
        focus-visible:ring-2 focus-visible:ring-accent-minor focus-visible:ring-offset-1 focus-visible:ring-offset-surface-base
        disabled:opacity-40 disabled:cursor-not-allowed outline-none transition-colors duration-100 ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
