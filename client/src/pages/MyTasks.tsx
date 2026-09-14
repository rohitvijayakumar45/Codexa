import React, { useMemo, useState } from 'react';
import type { Task, User } from '../lib/api';
import { Avatar } from '../components/ui';
import { STATUS_LIST, statusMeta, priorityMeta, PRIORITY_LIST } from '../lib/format';

export function MyTasksPage({ tasks, users, loading, error, onOpenTask }: {
  tasks: Task[];
  users: User[];
  loading: boolean;
  error: string | null;
  onOpenTask: (id: number) => void;
}) {
  const [statusFilter, setStatusFilter] = useState('open');
  const [priorityFilter, setPriorityFilter] = useState('all');

  const rows = useMemo(() => {
    return tasks.filter((t) => {
      if (statusFilter === 'open' && t.status === 'done') return false;
      if (statusFilter !== 'open' && statusFilter !== 'all' && t.status !== statusFilter) return false;
      if (priorityFilter !== 'all' && t.priority !== priorityFilter) return false;
      return true;
    });
  }, [tasks, statusFilter, priorityFilter]);

  const today = new Date().toISOString().slice(0, 10);
  const overdue = rows.filter((t) => t.dueDate && t.dueDate < today && t.status !== 'done');
  const dueSoon = rows.filter((t) => t.dueDate && t.dueDate >= today && t.dueDate <= addDays(today, 7) && t.status !== 'done');

  return (
    <div className="page">
      <header className="page-head">
        <h1>My tasks</h1>
        <p className="muted">Everything assigned to you across projects.</p>
      </header>

      <div className="filter-bar" role="toolbar" aria-label="Task filters">
        <div className="seg" role="group" aria-label="Status">
          <button className={'seg-btn' + (statusFilter === 'open' ? ' on' : '')} aria-pressed={statusFilter === 'open'} onClick={() => setStatusFilter('open')}>Open</button>
          {STATUS_LIST.map((s) => (
            <button key={s} className={'seg-btn' + (statusFilter === s ? ' on' : '')} aria-pressed={statusFilter === s} onClick={() => setStatusFilter(s)}>{statusMeta(s).label}</button>
          ))}
        </div>
        <div className="seg" role="group" aria-label="Priority">
          <button className={'seg-btn' + (priorityFilter === 'all' ? ' on' : '')} aria-pressed={priorityFilter === 'all'} onClick={() => setPriorityFilter('all')}>All priorities</button>
          {PRIORITY_LIST.map((p) => (
            <button key={p} className={'seg-btn' + (priorityFilter === p ? ' on' : '')} aria-pressed={priorityFilter === p} onClick={() => setPriorityFilter(p)}>{priorityMeta(p).label}</button>
          ))}
        </div>
      </div>

      {loading ? (
        <div aria-busy="true">
          {[0, 1, 2, 3, 4].map((i) => <div key={i} className="sk sk-line w90" />)}
        </div>
      ) : error ? (
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">!</div>
          <h3>Could not load tasks</h3>
          <p className="muted">{error}</p>
        </div>
      ) : rows.length === 0 ? (
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">/</div>
          <h3>Nothing here</h3>
          <p className="muted">No tasks match these filters.</p>
        </div>
      ) : (
        <>
          {overdue.length > 0 && <Group title="Overdue" tasks={overdue} onOpenTask={onOpenTask} tone="overdue" />}
          {dueSoon.length > 0 && <Group title="Due soon" tasks={dueSoon} onOpenTask={onOpenTask} tone="soon" />}
          <Group title="Everything else" tasks={rows.filter((t) => !overdue.includes(t) && !dueSoon.includes(t))} onOpenTask={onOpenTask} />
        </>
      )}
    </div>
  );
}

function Group({ title, tasks, onOpenTask, tone }: {
  title: string; tasks: Task[]; onOpenTask: (id: number) => void; tone?: string;
}) {
  if (!tasks.length) return null;
  return (
    <section className="task-group">
      <h3 className={'task-group-head' + (tone ? ' ' + tone : '')}>{title}<span>{tasks.length}</span></h3>
      <ul className="task-list">
        {tasks.map((t) => (
          <li key={t.id}>
            <button className="row-task" onClick={() => onOpenTask(t.id)}>
              <span className={'pri pri-' + t.priority} aria-label={t.priority + ' priority'} />
              <span className="row-task-key">{t.key}</span>
              <span className="row-task-title">{t.title}</span>
              <span className="row-task-proj muted small">{t.projectName}</span>
              {t.labels.length > 0 && (
                <span className="row-task-labels">
                  {t.labels.slice(0, 2).map((l) => (
                    <span key={l.id} className="mini-label"><i className="dot" style={{ background: 'var(--' + l.color + ')' }} />{l.name}</span>
                  ))}
                </span>
              )}
              <span className="row-task-due">{t.dueDate ? fmtDue(t.dueDate, t.status) : ''}</span>
              {t.commentCount > 0 && <span className="row-task-comments" aria-label={t.commentCount + ' comments'}>{t.commentCount}</span>}
              <Avatar user={t.assignee} size={22} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function fmtDue(d: string, status: string) {
  const dt = new Date(d + 'T00:00:00Z');
  const diff = Math.round((dt.getTime() - Date.now()) / 86400000);
  if (status === 'done') return dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  if (diff < 0) return Math.abs(diff) + 'd overdue';
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Tomorrow';
  return dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function addDays(iso: string, n: number) {
  const d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
