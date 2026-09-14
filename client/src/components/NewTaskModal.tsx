import React, { useEffect, useRef, useState } from 'react';
import { api, type Label, type Project, type User, type Task } from '../lib/api';
import { STATUS_LIST, PRIORITY_LIST, statusMeta, priorityMeta } from '../lib/format';

interface Props {
  projects: Project[];
  users: User[];
  labels: Label[];
  defaultProjectId?: number;
  defaultStatus?: string;
  onClose: () => void;
  onCreated: (t: Task) => void;
  onToast: (msg: string, tone?: 'ok' | 'err') => void;
}

interface Errors { [k: string]: string }

export function NewTaskModal({ projects, users, labels, defaultProjectId, defaultStatus, onClose, onCreated, onToast }: Props) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [projectId, setProjectId] = useState<number>(defaultProjectId ?? projects[0]?.id ?? 0);
  const [status, setStatus] = useState<string>(defaultStatus ?? 'backlog');
  const [priority, setPriority] = useState<string>('medium');
  const [assigneeId, setAssigneeId] = useState<string>('');
  const [labelIds, setLabelIds] = useState<number[]>([]);
  const [dueDate, setDueDate] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => { titleRef.current?.focus(); }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); onClose(); }
      if (e.key === 'Tab' && dialogRef.current) {
        const f = dialogRef.current.querySelectorAll<HTMLElement>('button, input, select, textarea, [href], [tabindex]:not([tabindex="-1"])');
        const list = Array.from(f).filter((el) => !el.hasAttribute('disabled'));
        if (!list.length) return;
        const first = list[0];
        const last = list[list.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  function validate(): Errors {
    const e: Errors = {};
    const t = title.trim();
    if (!t) e.title = 'A title is required';
    else if (t.length < 3) e.title = 'Titles need at least 3 characters';
    else if (t.length > 160) e.title = 'Keep titles under 160 characters';
    if (!projectId) e.projectId = 'Pick a project';
    if (description.length > 4000) e.description = 'Descriptions are limited to 4000 characters';
    if (dueDate && !/^\d{4}-\d{2}-\d{2}$/.test(dueDate)) e.dueDate = 'Use a valid date';
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
      const res = await api.createTask({
        title: title.trim(),
        description: description.trim(),
        projectId,
        status,
        priority,
        assigneeId: assigneeId || null,
        labelIds,
        dueDate: dueDate || null,
      });
      onCreated(res.task);
      onToast(res.task.key + ' created', 'ok');
      onClose();
    } catch (err) {
      setServerError(err instanceof Error ? err.message : 'Could not create the task');
    } finally {
      setSubmitting(false);
    }
  }

  const err = (k: string) => (errors[k] ? <p className="field-error" role="alert">{errors[k]}</p> : null);

  return (
    <div className="modal-scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="new-task-title" ref={dialogRef}>
        <form onSubmit={submit} noValidate>
          <header className="modal-head">
            <h2 id="new-task-title">New task</h2>
            <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}>
              <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
            </button>
          </header>

          <div className="modal-body">
            <div className="form-row">
              <label className="label" htmlFor="nt-title">Title</label>
              <input
                id="nt-title"
                ref={titleRef}
                className={'field' + (errors.title ? ' field-invalid' : '')}
                placeholder="e.g. Refine onboarding animation"
                value={title}
                maxLength={200}
                onChange={(e) => setTitle(e.target.value)}
                aria-invalid={!!errors.title}
              />
              {err('title')}
            </div>

            <div className="form-row">
              <label className="label" htmlFor="nt-desc">Description <span className="label-optional">optional</span></label>
              <textarea
                id="nt-desc"
                className={'field area' + (errors.description ? ' field-invalid' : '')}
                rows={3}
                placeholder="Add context, acceptance criteria, links..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
              {err('description')}
            </div>

            <div className="form-grid">
              <div className="form-row">
                <label className="label" htmlFor="nt-project">Project</label>
                <select id="nt-project" className="field" value={projectId} onChange={(e) => setProjectId(Number(e.target.value))}>
                  {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div className="form-row">
                <label className="label" htmlFor="nt-status">Status</label>
                <select id="nt-status" className="field" value={status} onChange={(e) => setStatus(e.target.value)}>
                  {STATUS_LIST.map((s) => <option key={s} value={s}>{statusMeta(s).label}</option>)}
                </select>
              </div>
              <div className="form-row">
                <label className="label" htmlFor="nt-priority">Priority</label>
                <select id="nt-priority" className="field" value={priority} onChange={(e) => setPriority(e.target.value)}>
                  {PRIORITY_LIST.map((p) => <option key={p} value={p}>{priorityMeta(p).label}</option>)}
                </select>
              </div>
              <div className="form-row">
                <label className="label" htmlFor="nt-assignee">Assignee</label>
                <select id="nt-assignee" className="field" value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)}>
                  <option value="">Unassigned</option>
                  {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                </select>
              </div>
              <div className="form-row">
                <label className="label" htmlFor="nt-due">Due date</label>
                <input id="nt-due" className={'field' + (errors.dueDate ? ' field-invalid' : '')} type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
                {err('dueDate')}
              </div>
            </div>

            <div className="form-row">
              <span className="label">Labels</span>
              <div className="chip-row">
                {labels.map((l) => {
                  const on = labelIds.includes(l.id);
                  return (
                    <button key={l.id} type="button" className={'chip' + (on ? ' chip-on' : '')} aria-pressed={on}
                      onClick={() => setLabelIds(on ? labelIds.filter((i) => i !== l.id) : [...labelIds, l.id])}>
                      <i className="dot" style={{ background: 'var(--' + l.color + ')' }} />{l.name}
                    </button>
                  );
                })}
              </div>
            </div>

            {serverError && <div className="form-error" role="alert">{serverError}</div>}
          </div>

          <footer className="modal-foot">
            <span className="muted small">Esc to cancel</span>
            <div className="row gap8">
              <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
              <button type="submit" className="btn btn-solid" disabled={submitting || !title.trim()}>
                {submitting ? 'Creating...' : 'Create task'}
              </button>
            </div>
          </footer>
        </form>
      </div>
    </div>
  );
}
