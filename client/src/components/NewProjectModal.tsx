import React, { useEffect, useRef, useState } from 'react';
import { api, type Project, type User } from '../lib/api';

interface Props {
  users: User[];
  onClose: () => void;
  onCreated: (p: Project) => void;
  onToast: (msg: string, tone?: 'ok' | 'err') => void;
}

export function NewProjectModal({ users, onClose, onCreated, onToast }: Props) {
  const [name, setName] = useState('');
  const [key, setKey] = useState('');
  const [description, setDescription] = useState('');
  const [leadId, setLeadId] = useState<string>(String(users[0]?.id ?? ''));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  function autoKey(v: string) {
    const words = v.trim().split(/\s+/).filter(Boolean);
    const k = words.map((w) => w[0]).join('').toUpperCase();
    setKey(k.slice(0, 4));
  }

  function validate() {
    const e: Record<string, string> = {};
    if (name.trim().length < 2) e.name = 'Project names need at least 2 characters';
    if (name.trim().length > 60) e.name = 'Keep names under 60 characters';
    if (!/^[A-Z][A-Z0-9]{1,4}$/.test(key)) e.key = 'Keys are 2 to 5 uppercase letters or digits';
    return e;
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    const errs = validate();
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setSubmitting(true);
    setServerError(null);
    try {
      const res = await api.createProject({ name: name.trim(), key, description: description.trim(), leadId: leadId ? Number(leadId) : null });
      onCreated(res.project);
      onToast('Project "' + res.project.name + '" created', 'ok');
      onClose();
    } catch (err) {
      setServerError(err instanceof Error ? err.message : 'Could not create the project');
    } finally {
      setSubmitting(false);
    }
  }

  const err = (k: string) => (errors[k] ? <p className="field-error" role="alert">{errors[k]}</p> : null);

  return (
    <div className="modal-scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal modal-sm" role="dialog" aria-modal="true" aria-labelledby="np-title">
        <form onSubmit={submit} noValidate>
          <header className="modal-head">
            <h2 id="np-title">New project</h2>
            <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}>
              <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
            </button>
          </header>
          <div className="modal-body">
            <div className="form-row">
              <label className="label" htmlFor="np-name">Name</label>
              <input id="np-name" ref={ref} className={'field' + (errors.name ? ' field-invalid' : '')} placeholder="e.g. Payments Platform"
                value={name} maxLength={70}
                onChange={(e) => { setName(e.target.value); if (!key) autoKey(e.target.value); }} />
              {err('name')}
            </div>
            <div className="form-grid">
              <div className="form-row">
                <label className="label" htmlFor="np-key">Key</label>
                <input id="np-key" className={'field' + (errors.key ? ' field-invalid' : '')} placeholder="PP"
                  value={key} maxLength={5}
                  onChange={(e) => setKey(e.target.value.toUpperCase())} />
                {err('key')}
              </div>
              <div className="form-row">
                <label className="label" htmlFor="np-lead">Lead</label>
                <select id="np-lead" className="field" value={leadId} onChange={(e) => setLeadId(e.target.value)}>
                  {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                </select>
              </div>
            </div>
            <div className="form-row">
              <label className="label" htmlFor="np-desc">Description <span className="label-optional">optional</span></label>
              <textarea id="np-desc" className="field area" rows={3} placeholder="What is this project about?"
                value={description} maxLength={400} onChange={(e) => setDescription(e.target.value)} />
            </div>
            {serverError && <div className="form-error" role="alert">{serverError}</div>}
          </div>
          <footer className="modal-foot">
            <span className="muted small">Esc to cancel</span>
            <div className="row gap8">
              <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
              <button type="submit" className="btn btn-solid" disabled={submitting || !name.trim()}>
                {submitting ? 'Creating...' : 'Create project'}
              </button>
            </div>
          </footer>
        </form>
      </div>
    </div>
  );
}
