import React, { useEffect, useRef, useState } from 'react';
import { api, type Comment, type Task, type User, type Label, type Activity } from '../lib/api';
import { Avatar } from './ui';
import { STATUS_LIST, PRIORITY_LIST, statusMeta, priorityMeta } from '../lib/format';

interface Props {
  taskId: number;
  users: User[];
  labels: Label[];
  onClose: () => void;
  onChanged: (t: Task) => void;
  onDeleted: (id: number) => void;
  onToast: (msg: string, tone?: 'ok' | 'err') => void;
}

export function TaskDetail({ taskId, users, labels, onClose, onChanged, onDeleted, onToast }: Props) {
  const [task, setTask] = useState<Task | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [commentDraft, setCommentDraft] = useState('');
  const [posting, setPosting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api.getTask(taskId)
      .then((d) => {
        if (!alive) return;
        setTask(d.task);
        setComments(d.comments);
        setActivity(d.activity);
        setDraft(d.task.description);
      })
      .catch((e) => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [taskId]);

  useEffect(() => {
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !confirmDelete) onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, confirmDelete]);

  const patch = async (body: Record<string, unknown>, label: string) => {
    if (!task) return;
    const prev = task;
    setTask({ ...task, ...body } as Task);
    setSaving(label);
    try {
      const res = await api.updateTask(task.id, body);
      setTask(res.task);
      onChanged(res.task);
    } catch (e) {
      setTask(prev);
      onToast(e instanceof Error ? e.message : 'Update failed', 'err');
    } finally {
      setSaving(null);
    }
  };

  const postComment = async () => {
    if (!task || !commentDraft.trim() || posting) return;
    const body = commentDraft.trim();
    setPosting(true);
    try {
      const res = await api.addComment(task.id, body);
      setComments((c) => [...c, res.comment]);
      setTask((t) => (t ? { ...t, commentCount: t.commentCount + 1 } : t));
      setCommentDraft('');
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Could not post comment', 'err');
    } finally {
      setPosting(false);
    }
  };

  const remove = async () => {
    if (!task) return;
    try {
      await api.deleteTask(task.id);
      onDeleted(task.id);
      onToast('Deleted ' + task.key, 'ok');
      onClose();
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Delete failed', 'err');
    }
  };

  return (
    <div className="drawer-scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="drawer" role="dialog" aria-modal="true" aria-label="Task details" ref={panel} tabIndex={-1}>
        {loading && !task ? (
          <div className="drawer-body">
            <div className="sk sk-line w40" />
            <div className="sk sk-line w90" />
            <div className="sk sk-line w70" />
            <div className="sk sk-block mt16" />
          </div>
        ) : error ? (
          <div className="drawer-body">
            <div className="empty">
              <div className="empty-icon" aria-hidden="true">!</div>
              <h3>Could not load this task</h3>
              <p className="muted">{error}</p>
              <button className="btn btn-ghost" onClick={onClose}>Close</button>
            </div>
          </div>
        ) : task ? (
          <>
            <header className="drawer-head">
              <div className="task-key">{task.key}</div>
              <button className="icon-btn" aria-label="Close details" onClick={onClose}>
                <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
              </button>
            </header>
            <div className="drawer-body">
              <h2 className="drawer-title">{task.title}</h2>
              <div className="drawer-project">{task.projectName}</div>

              <section className="prop-grid" aria-label="Task properties">
                <div className="prop">
                  <div className="prop-label">Status</div>
                  <select className="field" value={task.status} onChange={(e) => patch({ status: e.target.value }, 'Status')} aria-label="Status">
                    {STATUS_LIST.map((s) => <option key={s} value={s}>{statusMeta(s).label}</option>)}
                  </select>
                </div>
                <div className="prop">
                  <div className="prop-label">Priority</div>
                  <select className="field" value={task.priority} onChange={(e) => patch({ priority: e.target.value }, 'Priority')} aria-label="Priority">
                    {PRIORITY_LIST.map((p) => <option key={p} value={p}>{priorityMeta(p).label}</option>)}
                  </select>
                </div>
                <div className="prop">
                  <div className="prop-label">Assignee</div>
                  <select className="field" value={task.assignee ? task.assignee.id : ''} onChange={(e) => patch({ assigneeId: e.target.value || null }, 'Assignee')} aria-label="Assignee">
                    <option value="">Unassigned</option>
                    {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                  </select>
                </div>
                <div className="prop">
                  <div className="prop-label">Due date</div>
                  <input className="field" type="date" value={task.dueDate ? task.dueDate : ''} onChange={(e) => patch({ dueDate: e.target.value || null }, 'Due date')} aria-label="Due date" />
                </div>
              </section>

              <div className="prop">
                <div className="prop-label">Labels</div>
                <div className="chip-row">
                  {labels.map((l) => {
                    const on = task.labels.some((tl) => tl.id === l.id);
                    return (
                      <button key={l.id} className={'chip' + (on ? ' chip-on' : '')} onClick={() => {
                        const next = on ? task.labels.filter((tl) => tl.id !== l.id) : [...task.labels, l];
                        patch({ labels: next.map((x) => x.id) }, 'Labels');
                      }} aria-pressed={on}>
                        <i className="dot" style={{ background: 'var(--' + l.color + ')' }} />{l.name}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="prop">
                <div className="prop-label">Description</div>
                <textarea
                  className="field area"
                  value={draft}
                  rows={5}
                  placeholder="Add a description..."
                  onChange={(e) => setDraft(e.target.value)}
                  onBlur={() => { if (draft !== task.description) patch({ description: draft }, 'Description'); }}
                  aria-label="Description"
                />
              </div>
            </div>

            <section className="drawer-section">
              <h3 className="mini-head">Comments</h3>
              {comments.length === 0 && <p className="muted small">No comments yet.</p>}
              <ul className="comments">
                {comments.map((c) => (
                  <li key={c.id} className="comment">
                    <Avatar user={c.author} size={26} />
                    <div className="comment-body">
                      <div className="comment-meta">
                        <strong>{c.author ? c.author.name : 'Unknown'}</strong>
                        <span>{fmtDay(c.createdAt)}</span>
                      </div>
                      <p>{c.body}</p>
                    </div>
                  </li>
                ))}
              </ul>
              <div className="composer">
                <textarea className="field area" rows={2} placeholder="Write a comment..." value={commentDraft} onChange={(e) => setCommentDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) postComment(); }}
                  aria-label="New comment" />
                <button className="btn btn-solid" onClick={postComment} disabled={!commentDraft.trim() || posting}>
                  {posting ? 'Posting...' : 'Comment'}
                </button>
              </div>
            </section>

            <section className="drawer-section">
              <h3 className="mini-head">Activity</h3>
              <ul className="feed">
                {activity.map((a) => (
                  <li key={a.id} className="feed-item">
                    <Avatar user={a.actor} size={22} />
                    <div>
                      <p>{a.summary}</p>
                      <time>{relTime(a.createdAt)}</time>
                    </div>
                  </li>
                ))}
                {activity.length === 0 && <li className="muted small">No activity yet.</li>}
              </ul>
            </section>

            <footer className="drawer-foot">
              <div className="muted small">
                Created {relTime(task.createdAt)} &middot; Updated {relTime(task.updatedAt)}
              </div>
              {confirmDelete ? (
                <div className="row gap8">
                  <button className="btn btn-danger" onClick={remove}>Delete permanently</button>
                  <button className="btn btn-ghost" onClick={() => setConfirmDelete(false)}>Cancel</button>
                </div>
              ) : (
                <button className="btn btn-ghost" onClick={() => setConfirmDelete(true)}>Delete task</button>
              )}
            </footer>
            {saving && <div className="saving-pill" role="status">{saving}...</div>}
          </>
        ) : null}
      </div>
    </div>
  );
}

function fmtDay(sql: string) {
  return new Date(sql.replace(' ', 'T') + 'Z').toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function relTime(sql: string) {
  const d = new Date(sql.replace(' ', 'T') + (sql.endsWith('Z') ? '' : 'Z'));
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  if (diff < 86400 * 7) return Math.floor(diff / 86400) + 'd ago';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
