import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api, ApiError, type Project, type Task, type User, type Label, type Activity, type Member, type Overview } from './lib/api';
import { useAppStore } from './lib/store';
import { Sidebar, type View } from './components/Sidebar';
import { Board } from './components/Board';
import { TaskDetail } from './components/TaskDetail';
import { NewTaskModal } from './components/NewTaskModal';
import { NewProjectModal } from './components/NewProjectModal';
import { ToastProvider } from './components/Toaster';
import { OverviewPage } from './pages/Overview';
import { ProjectsPage, ProjectDetailPage } from './pages/Projects';
import { MyTasksPage } from './pages/MyTasks';
import { ActivityPage } from './pages/ActivityPage';

function parseHash(): View {
  const h = window.location.hash.replace(/^#\/?/, '');
  const [seg, id] = h.split('/');
  if (seg === 'projects' && id) return { kind: 'project', id: Number(id) };
  if (seg === 'projects') return { kind: 'projects' };
  if (seg === 'my-tasks') return { kind: 'my-tasks' };
  if (seg === 'activity') return { kind: 'activity' };
  return { kind: 'overview' };
}

function hashFor(v: View): string {
  if (v.kind === 'project') return '#/projects/' + v.id;
  if (v.kind === 'projects') return '#/projects';
  if (v.kind === 'my-tasks') return '#/my-tasks';
  if (v.kind === 'activity') return '#/activity';
  return '#/';
}

export default function App() {
  const store = useAppStore();
  const [view, setView] = useState<View>(() => parseHash());
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [newTask, setNewTask] = useState<{ projectId?: number; status?: string } | null>(null);
  const [newProject, setNewProject] = useState(false);
  const [openTaskId, setOpenTaskId] = useState<number | null>(null);
  const [detail, setDetail] = useState<{ project: Project; members: Member[]; activity: Activity[] } | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [overviewError, setOverviewError] = useState<string | null>(null);

  // hash routing
  useEffect(() => {
    const onHash = () => setView(parseHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => { window.location.hash = hashFor(view) === window.location.hash ? window.location.hash : hashFor(view); }, [view]);

  // keyboard shortcut: N opens new task
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      const typing = el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable);
      if (typing) return;
      if (e.key === 'n' || e.key === 'N') { e.preventDefault(); setNewTask({}); }
      if (e.key === '/') { e.preventDefault(); (document.querySelector<HTMLInputElement>('#global-search'))?.focus(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // boot
  useEffect(() => { store.bootstrap(); }, []);
  useEffect(() => {
    let alive = true;
    setOverviewLoading(true);
    api.overview()
      .then((d) => { if (alive) { setOverview(d); setOverviewError(null); } })
      .catch((e) => alive && setOverviewError(e.message))
      .finally(() => alive && setOverviewLoading(false));
    return () => { alive = false; };
  }, []);

  // refresh overview whenever tasks change meaningfully
  const refreshOverview = useCallback(() => {
    api.overview()
      .then((d) => { setOverview(d); setOverviewError(null); })
      .catch(() => {});
  }, []);
  useEffect(() => { refreshOverview(); }, [store.tasksVersion]);

  // project detail data
  useEffect(() => {
    if (view.kind !== 'project') return;
    let alive = true;
    setDetailLoading(true);
    setDetailError(null);
    api.getProject(view.id)
      .then((d) => alive && setDetail({ project: d.project, members: d.members, activity: d.activity }))
      .catch((e) => { if (alive) { setDetailError(e.message); setDetail(null); } })
      .finally(() => alive && setDetailLoading(false));
    return () => { alive = false; };
  }, [view.kind, view.kind === 'project' ? view.id : 0, store.tasksVersion]);

  const tasksForView = useMemo(() => {
    if (view.kind === 'project') return store.tasks.filter((t) => t.projectId === view.id);
    return store.tasks;
  }, [store.tasks, view]);

  const onOpenTask = useCallback((id: number) => setOpenTaskId(id), []);
  const onOpenProject = useCallback((id: number) => setView({ kind: 'project', id }), []);
  const toast = store.toast;

  return (
    <ToastProvider>
      <div className="app">
        <Sidebar
          view={view}
          projects={store.projects}
          me={store.me}
          onNavigate={setView}
          onNewTask={() => setNewTask({ projectId: view.kind === 'project' ? view.id : undefined })}
          onNewProject={() => setNewProject(true)}
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          syncing={store.syncing}
        />

        <main className="main" id="main">
          <TopBar
            view={view}
            projects={store.projects}
            filters={store.filters}
            setFilters={store.setFilters}
            search={store.search}
            setSearch={store.setSearch}
            onNewTask={() => setNewTask({ projectId: view.kind === 'project' ? view.id : undefined })}
            onMenu={() => setSidebarOpen(true)}
            me={store.me}
          />

          <div key={view.kind + (view.kind === 'project' ? view.id : '')} className="view-enter">
            {view.kind === 'overview' && (
              <OverviewPage
                data={overview}
                loading={overviewLoading}
                error={overviewError}
                onOpenTask={onOpenTask}
                onOpenProject={onOpenProject}
              />
            )}
            {view.kind === 'projects' && (
              <ProjectsPage
                projects={store.projects}
                onOpen={onOpenProject}
                onNew={() => setNewProject(true)}
                onToast={toast}
              />
            )}
            {view.kind === 'project' && (
              <ProjectDetailPage
                project={detail ? detail.project : null}
                members={detail ? detail.members : []}
                activity={detail ? detail.activity : []}
                onOpenTask={onOpenTask}
                loading={detailLoading}
                error={detailError}
              />
            )}
            {view.kind === 'my-tasks' && (
              <MyTasksPage
                tasks={store.tasks}
                users={store.users}
                loading={store.loading}
                error={store.error}
                onOpenTask={onOpenTask}
              />
            )}
            {view.kind === 'activity' && <ActivityPage projects={store.projects} />}
          </div>

          {view.kind === 'project' && (
            <Board
              tasks={tasksForView}
              project={detail ? detail.project : null}
              loading={store.loading}
              filters={store.filters}
              onOpenTask={onOpenTask}
              onMove={store.moveTask}
              onToast={toast}
            />
          )}
        </main>

        {newTask && (
          <NewTaskModal
            projects={store.projects}
            users={store.users}
            labels={store.labels}
            defaultProjectId={newTask.projectId}
            defaultStatus={newTask.status}
            onClose={() => setNewTask(null)}
            onCreated={(t) => store.addTask(t)}
            onToast={toast}
          />
        )}
        {newProject && (
          <NewProjectModal
            users={store.users}
            onClose={() => setNewProject(false)}
            onCreated={(p) => { store.addProject(p); setView({ kind: 'project', id: p.id }); }}
            onToast={toast}
          />
        )}
        {openTaskId != null && (
          <TaskDetail
            taskId={openTaskId}
            users={store.users}
            labels={store.labels}
            onClose={() => setOpenTaskId(null)}
            onChanged={(t) => store.updateTask(t)}
            onDeleted={(id) => store.removeTask(id)}
            onToast={toast}
          />
        )}
      </div>
    </ToastProvider>
  );
}

function TopBar({ view, projects, filters, setFilters, search, setSearch, onNewTask, onMenu, me }: {
  view: View;
  projects: Project[];
  filters: Record<string, string>;
  setFilters: (f: Record<string, string>) => void;
  search: string;
  setSearch: (s: string) => void;
  onNewTask: () => void;
  onMenu: () => void;
  me: User;
}) {
  const project = view.kind === 'project' ? projects.find((p) => p.id === view.id) : null;
  const title =
    view.kind === 'overview' ? 'Overview'
    : view.kind === 'projects' ? 'Projects'
    : view.kind === 'my-tasks' ? 'My tasks'
    : view.kind === 'activity' ? 'Activity'
    : project ? project.name : 'Board';

  const activeFilterCount = Object.values(filters).filter((v) => v && v !== 'all').length;

  return (
    <div className="topbar">
      <button className="icon-btn menu-btn" aria-label="Open navigation" onClick={onMenu}>
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
      </button>
      <div className="topbar-title">{title}</div>
      <div className="search-wrap">
        <svg className="search-ico" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="6" cy="6" r="4.4" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M9.4 9.4L12.6 12.6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
        <input
          id="global-search"
          className="search-input"
          type="search"
          placeholder="Search tasks... (press /)"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search tasks"
        />
      </div>
      <div className="filter-selects">
        <select className="filter-sel" value={filters.priority ?? 'all'} onChange={(e) => setFilters({ ...filters, priority: e.target.value === 'all' ? '' : e.target.value })} aria-label="Filter by priority">
          <option value="all">Any priority</option>
          <option value="urgent">Urgent</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <select className="filter-sel" value={filters.assignee ?? 'all'} onChange={(e) => setFilters({ ...filters, assignee: e.target.value })} aria-label="Filter by assignee">
          <option value="all">Anyone</option>
          <option value="none">Unassigned</option>
          <option value={String(me.id)}>{me.name} (you)</option>
        </select>
        <select className="filter-sel" value={filters.due ?? 'all'} onChange={(e) => setFilters({ ...filters, due: e.target.value })} aria-label="Filter by due date">
          <option value="all">Any date</option>
          <option value="overdue">Overdue</option>
          <option value="week">Due this week</option>
          <option value="none">No due date</option>
        </select>
        {(search || activeFilterCount > 0) && (
          <button className="btn btn-ghost btn-clear" onClick={() => { setSearch(''); setFilters({}); }}>Clear</button>
        )}
      </div>
      <button className="btn btn-solid topbar-new" onClick={onNewTask}>New task</button>
    </div>
  );
}
