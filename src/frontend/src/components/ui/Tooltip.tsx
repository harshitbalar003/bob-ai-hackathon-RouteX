import React, { useState, useRef, useEffect, useId } from 'react';

interface TooltipProps {
  content: React.ReactNode;
  children: React.ReactElement;
  side?: 'top' | 'bottom' | 'left' | 'right';
}

export function Tooltip({ content, children, side = 'top' }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!visible) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setVisible(false);
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [visible]);

  const positionClass =
    side === 'top' ? 'bottom-full mb-1.5 left-1/2 -translate-x-1/2' :
    side === 'bottom' ? 'top-full mt-1.5 left-1/2 -translate-x-1/2' :
    side === 'left' ? 'right-full mr-1.5 top-1/2 -translate-y-1/2' :
    'left-full ml-1.5 top-1/2 -translate-y-1/2';

  return (
    <div ref={ref} className="relative inline-flex">
      {React.cloneElement(children, {
        'aria-describedby': visible ? id : undefined,
        onMouseEnter: () => setVisible(true),
        onMouseLeave: () => setVisible(false),
        onFocus: () => setVisible(true),
        onBlur: () => setVisible(false),
      } as React.HTMLAttributes<Element>)}
      {visible && (
        <div
          id={id}
          role="tooltip"
          className={`absolute z-50 px-2 py-1 text-xs rounded bg-surface-raised border border-surface-border
            text-text-primary shadow-lg whitespace-nowrap pointer-events-none ${positionClass}`}
        >
          {content}
        </div>
      )}
    </div>
  );
}
