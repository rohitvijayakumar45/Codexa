import React, { useState } from 'react';
import type { Project, Member, Activity } from '../lib/api';
import { api } from '../lib/api';
import { Avatar, Progress } from '../components/ui';

export function ProjectsPage({ projects, onOpen, onNew, onToast }: {
  projects: Project[];
  onOpen: (id: number) => void;
  onNew: () => void;
  onToast: (m: string, t?: 'ok' | 'err') => void;
}) {
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  async function remove(id: number, name: string) {
    setBusy(true);
    try {
      await api.deleteProject(id);
      window.location.hash = '#/projects';
      onToast('Deleted "' + name + '"', 'ok');
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Delete failed', 'err');
    } finally {
      setBusy(false);
      setConfirmId(null);
    }
  }

  if (!projects.length) {
    return (
      <div className="page">
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">/</div>
          <h3>No projects yet</h3>
          <p className="muted">Create your first project to start moving work forward.</p>
          <button className="btn btn-solid" onClick={onNew}>New project</button>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="page-head">
        <h1>Projects</h1>
        <p className="muted">{projects.length} workspace {projects.length === 1 ? 'project' : 'projects'}</p>
      </header>
      <ul className="project-grid">
        {projects.map((p) => (
          <li key={p.id} className="project-card">
            <button className="project-card-main" onClick={() => onOpen(p.id)}>
              <div className="project-card-top">
                <span className="project-key">{p.key}</span>
                <span className={'status-pill status-' + p.status}>{p.status}</span>
              </div>
              <h3>{p.name}</h3>
              <p className="muted">{p.description || 'No description'}</p>
              <div className="project-card-progress">
                <Progress value={p.stats ? p.stats.progress : 0} />
                <span className="ov-progress">{p.stats ? p.stats.progress : 0}%</span>
              </div>
              <div className="project-card-meta">
                <span className="muted small">{p.stats ? p.stats.done + ' of ' + p.stats.total + ' done' : 'No tasks'}</span>
                {p.stats && p.stats.overdue > 0 && (
                  <span className="overdue-pill">{p.stats.overdue} overdue</span>
                )}
              </div>
            </button>
            {confirmId === p.id ? (
              <div className="project-card-confirm">
                <span className="muted small">Delete this project and all its tasks?</span>
                <div className="row gap8">
                  <button className="btn btn-danger" disabled={busy} onClick={() => remove(p.id, p.name)}>Delete</button>
                  <button className="btn btn-ghost" onClick={() => setConfirmId(null)}>Cancel</button>
                </div>
              </div>
            ) : (
              <button className="project-card-del" aria-label={'Delete ' + p.name} onClick={() => setConfirmId(p.id)}>Delete</button>
            )}
          </li>
        ))}
        <li>
          <button className="project-card project-card-new" onClick={onNew}>
            <span className="plus" aria-hidden="true">+</span>
            <h3>New project</h3>
            <p className="muted">Start something in motion.</p>
          </button>
        </li>
      </ul>
    </div>
  );
}

export function ProjectDetailPage({ project, members, activity, onOpenTask, loading, error }: {
  project: Project | null;
  members: Member[];
  activity: Activity[];
  onOpenTask: (id: number) => void;
  loading: boolean;
  error: string | null;
}) {
  if (loading && !project) {
    return (
      <div className="page" aria-busy="true">
        <div className="sk sk-line w30" />
        <div className="sk sk-line w50" />
        <div className="sk sk-block mt16" />
      </div>
    );
  }
  if (error || !project) {
    return (
      <div className="page">
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">!</div>
          <h3>Could not open this project</h3>
          <p className="muted">{error || 'It may have been deleted.'}</p>
        </div>
      </div>
    );
  }
  const stats = project.stats;
  return (
    <div className="page">
      <header className="page-head">
        <div className="page-head-row">
          <div>
            <div className="crumb"><span className="project-key">{project.key}</span></div>
            <h1>{project.name}</h1>
            <p className="muted">{project.description}</p>
          </div>
        </div>
      </header>

      <div className="pd-grid">
        <section className="pd-progress">
          <div className="pd-progress-num">
            <span className="big-num">{stats ? stats.progress : 0}<small>%</small></span>
            <span className="muted">complete</span>
          </div>
          <Progress value={stats ? stats.progress : 0} height={6} />
          <div className="pd-progress-detail">
            {stats ? `${stats.done} done of ${stats.total} tasks` : 'No tasks yet'}
            {stats && stats.inProgress > 0 ? ` · ${stats.inProgress} in progress` : ''}
          </div>
        </section>
        <section className="pd-side">
          <h3 className="mini-head">Members</h3>
          <ul className="member-list">
            {members.map((m) => (
              <li key={m.id} className="member">
                <Avatar user={m} size={26} />
                <div className="member-main">
                  <span className="member-name">{m.name}</span>
                  <span className="muted small">{m.memberRole === 'lead' ? 'Project lead' : 'Member'}</span>
                </div>
              </li>
            ))}
            {members.length === 0 && <li className="muted small">No members yet.</li>}
          </ul>
        </section>
      </div>

      <section className="ov-section">
        <div className="ov-head"><h2>Activity</h2></div>
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
    </div>
  );
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
