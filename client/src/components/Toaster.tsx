import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

export type Toast = { id: number; msg: string; tone: 'ok' | 'err' };
type Push = (msg: string, tone?: 'ok' | 'err') => void;

const Ctx = createContext<Push>(() => {});
export const useToast = () => useContext(Ctx);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((msg: string, tone: 'ok' | 'err' = 'ok') => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-3), { id, msg, tone }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === 'err' ? 5200 : 2600);
  }, []);
  const value = useMemo(() => push, [push]);
  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="toasts" role="region" aria-label="Notifications" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={'toast toast-' + t.tone} role={t.tone === 'err' ? 'alert' : 'status'}>
            <span className={'toast-dot ' + t.tone} aria-hidden="true" />
            {t.msg}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
