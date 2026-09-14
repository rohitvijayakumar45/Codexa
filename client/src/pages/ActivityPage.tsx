import React, { useEffect, useState } from 'react';
import type { Activity as Act, Project } from '../lib/api';
import { api } from '../lib/api';
import { Avatar } from '../components/ui';

export function ActivityPage({ projects }: { projects: Project[] }) {
  const [items, setItems] = useState<Act[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [projectId, setProjectId] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.listActivity(projectId ? Number(projectId) : undefined, 60)
      .then((d) => { if (alive) { setItems(d.activity); setError(null); } })
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [projectId]);

  return (
    <div className="page">
      <header className="page-head">
        <h1>Activity</h1>
        <p className="muted">Everything that happened across the workspace.</p>
      </header>

      <div className="filter-bar" role="toolbar" aria-label="Activity filters">
        <div className="seg" role="group" aria-label="Project">
          <button className={'seg-btn' + (projectId === '' ? ' on' : '')} aria-pressed={projectId === ''} onClick={() => setProjectId('')}>All projects</button>
          {projects.map((p) => (
            <button key={p.id} className={'seg-btn' + (projectId === String(p.id) ? ' on' : '')} aria-pressed={projectId === String(p.id)} onClick={() => setProjectId(String(p.id))}>{p.name}</button>
          ))}
        </div>
      </div>

      {loading && !items ? (
        <div aria-busy="true">
          {[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="sk sk-line w90" />)}
        </div>
      ) : error ? (
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">!</div>
          <h3>Could not load activity</h3>
          <p className="muted">{error}</p>
        </div>
      ) : !items || items.length === 0 ? (
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">/</div>
          <h3>No activity yet</h3>
          <p className="muted">Move a task or add a comment and it will show up here.</p>
        </div>
      ) : (
        <ul className="feed feed-page">
          {items.map((a) => (
            <li key={a.id} className="feed-item">
              <Avatar user={a.actor} size={26} />
              <div className="feed-main">
                <p>{a.summary}</p>
                <div className="feed-meta muted small">
                  {a.projectName && <span className="project-key">{a.projectKey}</span>}
                  <time>{relTime(a.createdAt)}</time>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function relTime(sql: string) {
  const d = new Date(sql.replace(' ', 'T') + (sql.endsWith('Z') ? '' : 'Z'));
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  if (diff < 86400 * 30) return Math.floor(diff / 86400) + 'd ago';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
