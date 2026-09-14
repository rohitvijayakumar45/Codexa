import React from 'react';
import type { Overview as OverviewData, Task } from '../lib/api';
import { Avatar } from '../components/ui';
import { Progress } from '../components/ui';

export function OverviewPage({ data, loading, error, onOpenTask, onOpenProject }: {
  data: OverviewData | null;
  loading: boolean;
  error: string | null;
  onOpenTask: (id: number) => void;
  onOpenProject: (id: number) => void;
}) {
  if (loading && !data) return <OverviewSkeleton />;
  if (error) {
    return (
      <div className="page">
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">!</div>
          <h3>Could not load your workspace</h3>
          <p className="muted">{error}</p>
          <button className="btn btn-solid" onClick={() => window.location.reload()}>Try again</button>
        </div>
      </div>
    );
  }
  if (!data) return null;
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';

  return (
    <div className="page page-overview">
      <header className="page-head">
        <h1 className="greeting">{greeting}, {data.me.name.split(' ')[0]}.</h1>
        <p className="tagline">Everything important is in motion.</p>
      </header>

      <section className="stat-row" aria-label="Workspace summary">
        <Stat label="Active projects" value={data.totals.activeProjects} />
        <Stat label="Open tasks" value={data.totals.openTasks} />
        <Stat label="Due this week" value={data.totals.dueWeek} />
        <Stat label="Completed this month" value={data.totals.completed30} />
      </section>

      <section className="ov-section">
        <div className="ov-head">
          <h2>Recent projects</h2>
        </div>
        <ul className="ov-projects">
          {data.recentProjects.map((p) => (
            <li key={p.id}>
              <button className="ov-project" onClick={() => onOpenProject(p.id)}>
                <div className="ov-project-main">
                  <span className="project-key">{p.key}</span>
                  <div>
                    <h3>{p.name}</h3>
                    <p className="muted">{p.description}</p>
                  </div>
                </div>
                <div className="ov-project-meta">
                  <span className="ov-progress">{p.stats ? p.stats.progress : 0}%</span>
                  <Progress value={p.stats ? p.stats.progress : 0} width={72} />
                  <span className="muted small">
                    {p.stats ? `${p.stats.done} of ${p.stats.total} tasks` : 'No tasks yet'}
                  </span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <div className="ov-cols">
        <section className="ov-section">
          <div className="ov-head"><h2>My focus</h2></div>
          {data.myTasks.length === 0 ? (
            <p className="muted small">Nothing due soon. Enjoy the calm.</p>
          ) : (
            <ul className="ov-tasks">
              {data.myTasks.map((t: Task) => (
                <li key={t.id}>
                  <button className="ov-task" onClick={() => onOpenTask(t.id)}>
                    <span className={'pri pri-' + t.priority} aria-label={t.priority + ' priority'} />
                    <span className="ov-task-title">{t.title}</span>
                    {t.assignee && <Avatar user={t.assignee} size={20} />}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="ov-section">
          <div className="ov-head"><h2>Recent activity</h2></div>
          <ul className="feed">
            {data.recentActivity.map((a) => (
              <li key={a.id} className="feed-item">
                <Avatar user={a.actor} size={22} />
                <div>
                  <p>{a.summary}</p>
                  <time>{relTime(a.createdAt)}</time>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function OverviewSkeleton() {
  return (
    <div className="page page-overview" aria-busy="true">
      <div className="sk sk-line w40" />
      <div className="sk sk-line w60" />
      <div className="stat-row">{[0, 1, 2, 3].map((i) => <div key={i} className="sk sk-stat" />)}</div>
      <div className="sk sk-line w30 mt16" />
      <div className="sk sk-block" />
      <div className="sk sk-block" />
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
