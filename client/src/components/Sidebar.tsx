import React, { useState } from 'react';
import type { Project, User } from '../lib/api';
import { Avatar } from './ui';

export type View =
  | { kind: 'overview' }
  | { kind: 'projects' }
  | { kind: 'project'; id: number }
  | { kind: 'my-tasks' }
  | { kind: 'activity' };

interface Props {
  view: View;
  projects: Project[];
  me: User;
  onNavigate: (v: View) => void;
  onNewTask: () => void;
  onNewProject: () => void;
  open: boolean;
  onClose: () => void;
  syncing: boolean;
}

function isActive(v: View, view: View) {
  if (v.kind === 'project') return view.kind === 'project' && view.id === v.id;
  return v.kind === view.kind;
}

export function Sidebar({ view, projects, me, onNavigate, onNewTask, onNewProject, open, onClose, syncing }: Props) {
  const [expanded, setExpanded] = useState(true);
  const go = (v: View) => { onNavigate(v); onClose(); };

  return (
    <>
      <div className={'scrim-mobile' + (open ? ' show' : '')} onClick={onClose} aria-hidden="true" />
      <aside className={'sidebar' + (open ? ' open' : '')} aria-label="Workspace navigation">
        <div className="sidebar-top">
          <div className="wordmark" aria-hidden="true">
            <span className="wordmark-mark" />
            <span className="wordmark-text">ORBIT</span>
          </div>
          <button
            type="button"
            className="btn btn-solid btn-new-task"
            onClick={onNewTask}
            aria-keyshortcuts="n"
          >
            <svg width="13" height="13" viewBox="0 0 13 13" aria-hidden="true"><path d="M6.5 1v11M1 6.5h11" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>
            New task
          </button>
        </div>

        <button
          type="button"
          className="workspace"
          aria-label="Workspace: Orbit HQ"
          onClick={() => setExpanded((e) => !e)}
        >
          <span className="workspace-badge">OH</span>
          <span className="workspace-name">Orbit HQ</span>
          <span className="workspace-chevron" aria-hidden="true">/</span>
        </button>

        <nav className="nav" aria-label="Main">
          <button
            type="button"
            className={'nav-item' + (isActive({ kind: 'overview' }, view) ? ' active' : '')}
            onClick={() => go({ kind: 'overview' })}
            aria-current={isActive({ kind: 'overview' }, view) ? 'page' : undefined}
          >
            <span className="nav-glyph" aria-hidden="true">
              <svg width="15" height="15" viewBox="0 0 15 15"><circle cx="7.5" cy="7.5" r="6" fill="none" stroke="currentColor" strokeWidth="1.4" /><circle cx="7.5" cy="7.5" r="2.2" fill="currentColor" /></svg>
            </span>
            Overview
          </button>
          <button
            type="button"
            className={'nav-item' + (isActive({ kind: 'projects' }, view) ? ' active' : '')}
            onClick={() => go({ kind: 'projects' })}
            aria-current={isActive({ kind: 'projects' }, view) ? 'page' : undefined}
          >
            <span className="nav-glyph" aria-hidden="true">
              <svg width="15" height="15" viewBox="0 0 15 15"><rect x="1.5" y="1.5" width="12" height="12" rx="3" fill="none" stroke="currentColor" strokeWidth="1.4" /></svg>
            </span>
            Projects
            <span className="nav-count">{projects.length}</span>
          </button>
          <button
            type="button"
            className={'nav-item' + (isActive({ kind: 'my-tasks' }, view) ? ' active' : '')}
            onClick={() => go({ kind: 'my-tasks' })}
            aria-current={isActive({ kind: 'my-tasks' }, view) ? 'page' : undefined}
          >
            <span className="nav-glyph" aria-hidden="true">
              <svg width="15" height="15" viewBox="0 0 15 15"><path d="M2 8.2l3.2 3.2L13 3.6" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </span>
            My tasks
          </button>
          <button
            type="button"
            className={'nav-item' + (isActive({ kind: 'activity' }, view) ? ' active' : '')}
            onClick={() => go({ kind: 'activity' })}
            aria-current={isActive({ kind: 'activity' }, view) ? 'page' : undefined}
          >
            <span className="nav-glyph" aria-hidden="true">
              <svg width="15" height="15" viewBox="0 0 15 15"><path d="M3 1.5h9M3 7.5h9M3 13.5h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
            </span>
            Activity
          </button>
        </nav>

        <div className="nav-group">
          <div className="nav-group-head">
            <span>Projects</span>
            <button type="button" className="group-add" aria-label="New project" onClick={onNewProject}>+</button>
          </div>
          <div className="nav-list">
            {projects.map((p) => (
              <button
                key={p.id}
                type="button"
                className={'nav-item project-item' + (isActive({ kind: 'project', id: p.id }, view) ? ' active' : '')}
                onClick={() => go({ kind: 'project', id: p.id })}
                aria-current={isActive({ kind: 'project', id: p.id }, view) ? 'page' : undefined}
              >
                <span className="project-key">{p.key}</span>
                <span className="project-name">{p.name}</span>
                {p.stats && p.stats.total > 0 && (
                  <span className="nav-count">{p.stats.progress}%</span>
                )}
              </button>
            ))}
          </div>
        </div>

        <div className="sidebar-bottom">
          <button type="button" className="nav-item" onClick={() => go({ kind: 'overview' })}>
            <span className="nav-glyph" aria-hidden="true">
              <svg width="15" height="15" viewBox="0 0 15 15"><path d="M7.5 2a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11z" fill="none" stroke="currentColor" strokeWidth="1.4" /></svg>
            </span>
            Notifications
          </button>
          <button type="button" className="nav-item" onClick={() => go({ kind: 'overview' })}>
            <span className="nav-glyph" aria-hidden="true">
              <svg width="15" height="15" viewBox="0 0 15 15"><circle cx="7.5" cy="7.5" r="6" fill="none" stroke="currentColor" strokeWidth="1.4" /><path d="M7.5 4.8v3.4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /><circle cx="7.5" cy="10.6" r=".8" fill="currentColor" /></svg>
            </span>
            Settings
          </button>
          <button type="button" className="user-chip" onClick={() => go({ kind: 'my-tasks' })}>
            <Avatar user={me} size={24} />
            <span className="user-chip-name">{me.name}</span>
            {syncing && <span className="sync-dot" role="status" aria-label="Syncing" />}
          </button>
        </div>
      </aside>
    </>
  );
}
