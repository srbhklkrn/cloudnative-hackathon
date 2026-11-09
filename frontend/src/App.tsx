import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgendaResponse, Event, Meta, Plan, Preferences, Session } from './types';

const labels: Record<string, string> = { kubernetes: 'Kubernetes', networking: 'Networking', ebpf: 'eBPF', security: 'Security', observability: 'Observability', ai: 'AI infrastructure', platform: 'Platform engineering', gitops: 'GitOps', step_free: 'Step-free access', captions: 'Live captions', hearing_loop: 'Hearing loop', quiet_space: 'Quiet space' };
const emptyPreferences: Preferences = { topics: [], accessibility: [] };
const paths: Record<string, string> = {
  arrow: 'M5 12h14m-6-6 6 6-6 6', search: 'm21 21-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  grid: 'M3 3h7v7H3zm11 0h7v7h-7zM3 14h7v7H3zm11 0h7v7h-7z',
  calendar: 'M5 5h14a2 2 0 0 1 2 2v13H3V7a2 2 0 0 1 2-2Zm2-3v6m10-6v6M3 11h18',
  settings: 'M4 7h16M4 17h16M8 3v8m8 2v8', clock: 'M12 7v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  pin: 'M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0ZM15 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  plus: 'M12 5v14M5 12h14', check: 'm5 12 4 4L19 6', close: 'm6 6 12 12M6 18 18 6',
  alert: 'm12 3 10 18H2L12 3Zm0 5v6m0 3v1', refresh: 'M20 7v5h-5M4 17v-5h5M5 7a8 8 0 0 1 14-1l1 6M4 12l1 6a8 8 0 0 0 14-1',
  route: 'M5 21V9h14m-6-6 6 6-6 6', leaf: 'M20 3c0 12-5 17-12 14C1 11 6 3 20 3ZM4 21l10-11',
};
function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.arrow} /></svg>;
}
async function api<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', signal,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status}). Please try again.`);
  }
  return response.json() as Promise<T>;
}
const time = (iso: string, zone: string) => new Intl.DateTimeFormat('en-US', { timeZone: zone, hour: 'numeric', minute: '2-digit' }).format(new Date(iso));
const topicClass = (s: Session) => s.topics.includes('ebpf') ? 'network' : s.topics.includes('security') ? 'security' : s.topics.includes('ai') ? 'ai' : s.topics.includes('observability') ? 'observe' : 'platform';

export default function App() {
  const [view, setView] = useState<'discover' | 'agenda' | 'organizer'>('discover');
  const [meta, setMeta] = useState<Meta | null>(null);
  const [allSessions, setAllSessions] = useState<Session[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [agenda, setAgenda] = useState<AgendaResponse | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [results, setResults] = useState<Session[]>([]);
  const [query, setQuery] = useState('');
  const [submitted, setSubmitted] = useState('');
  const [topic, setTopic] = useState('');
  const [level, setLevel] = useState('');
  const [after, setAfter] = useState('');
  const [mode, setMode] = useState('hybrid');
  const [zone, setZone] = useState('America/Denver');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState('');
  const [searching, setSearching] = useState(true);
  const [initializing, setInitializing] = useState(true);
  const [editing, setEditing] = useState<string | null>(null);
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const refreshing = useRef(false);
  const planKey = useRef('');
  const preferences = agenda?.agenda.preferences || emptyPreferences;
  const savedIds = agenda?.agenda.session_ids || [];
  const stamp = allSessions.map(s => `${s.id}:${s.revision}`).join(',');
  const accessKey = preferences.accessibility.join(',');

  const refresh = useCallback(async (force = false) => {
    if (refreshing.current) return;
    refreshing.current = true;
    try {
      // Establish the HttpOnly attendee cookie before concurrent requests or writes.
      const nextAgenda = await api<AgendaResponse>('/api/agenda');
      setAgenda(nextAgenda);
      const [nextMeta, data] = await Promise.all([api<Meta>('/api/meta'), api<{ sessions: Session[]; disruptions: Event[] }>('/api/sessions')]);
      setMeta(nextMeta); setAllSessions(data.sessions); setEvents(data.disruptions);
      const key = JSON.stringify([nextAgenda.affected, nextAgenda.agenda.preferences, nextAgenda.agenda.session_ids]);
      if (!nextAgenda.affected.length) { setPlan(null); planKey.current = ''; }
      else if (force || key !== planKey.current) {
        const nextPlan = await api<Plan>('/api/replan', {});
        setPlan(nextPlan); planKey.current = key;
      }
      setError('');
    } catch (e) { setError((e as Error).message); }
    finally { refreshing.current = false; setInitializing(false); }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => { if (!document.hidden) void refresh(); }, 8000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!meta?.ready) return;
    const controller = new AbortController();
    const params = new URLSearchParams({ q: submitted, mode, topic, level });
    if (after) params.set('after', `2026-11-09T${after}:00-07:00`);
    preferences.accessibility.forEach(x => params.append('accessibility', x));
    setSearching(true);
    api<{ results: { session: Session }[] }>(`/api/search?${params}`, undefined, controller.signal)
      .then(data => { setResults(data.results.map(x => x.session)); setSearching(false); })
      .catch(e => { if (e.name !== 'AbortError') { setError(e.message); setSearching(false); } });
    return () => controller.abort();
  }, [submitted, mode, topic, level, after, stamp, accessKey, meta?.ready]);

  async function mutate(path: string, body: unknown, message: string, key: string) {
    setBusy(key); setError(''); setNotice('Saving your change…');
    try {
      await api(path, body);
      setNotice(message);
      // Let an in-flight poll finish before refreshing mutation results.
      if (refreshing.current) planKey.current = '';
      else await refresh(true);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(''); }
  }
  function togglePreference(kind: keyof Preferences, value: string) {
    const values = preferences[kind];
    const next = { ...preferences, [kind]: values.includes(value) ? values.filter(x => x !== value) : [...values, value] };
    void mutate('/api/agenda', { action: 'preferences', preferences: next }, 'Preferences updated. Your agenda has been checked again.', 'preferences');
  }
  function save(s: Session) {
    const isSaved = savedIds.includes(s.id);
    void mutate('/api/agenda', { action: isSaved ? 'remove' : 'save', session_id: s.id }, isSaved ? 'Session removed from your agenda.' : 'Added to your agenda.', s.id);
  }
  function performSearch(value: string) { setQuery(value); setSubmitted(value); setView('discover'); }

  const agendaPanel = (large = false) => <section className={`agenda-panel ${large ? 'expanded' : ''}`} aria-label="Your saved agenda">
    <div className="panel-title"><div><span className="eyebrow">MADE FOR YOU</span><h2>Your agenda <span className="count">{savedIds.length}</span></h2></div><Icon name="calendar" size={22} /></div>
    <p className="muted agenda-date">Monday, November 9 <span>· {zone === 'UTC' ? 'UTC' : zone === 'America/Denver' ? 'Mountain Time' : 'Your time'}</span></p>
    {!agenda?.sessions.length ? <div className="empty-agenda"><div className="empty-icon"><Icon name="calendar" size={25} /></div><h3>A day with possibilities.</h3><p>Save a session that catches your eye.<br />We’ll help you make the most of it.</p></div> :
      <div className="timeline">{agenda.sessions.map(s => {
        const disrupted = agenda.affected.find(x => x.session_id === s.id);
        return <article key={s.id} className={`timeline-item ${disrupted ? 'disrupted' : ''}`}>
          <span className="timeline-dot" /><div className="timeline-time">{time(s.start, zone)} – {time(s.end, zone)}</div>
          <h3>{s.title}</h3><p><Icon name="pin" size={13} /> {s.room} · {s.building}</p>
          {disrupted && <div className="timeline-warning"><Icon name="alert" size={14} /> {disrupted.reason}</div>}
          <button className="text-button remove" onClick={() => save(s)} disabled={!!busy} aria-label={`Remove ${s.title} from agenda`}>Remove</button>
        </article>;
      })}</div>}
    {view !== 'agenda' && !!savedIds.length && <button className="wide-button" onClick={() => setView('agenda')}>View my full agenda <Icon name="arrow" /></button>}
    <div className="agenda-note"><Icon name="route" size={21} /><p><strong>Plans can change. Your day goes on.</strong><br />If a session fills up, we’ll find a new direction.</p></div>
  </section>;

  return <div className="app-shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <aside className={`sidebar ${preferencesOpen ? 'preferences-open' : ''}`}>
      <a href="#" className="brand" onClick={e => { e.preventDefault(); setView('discover'); }}><span className="brand-mark"><Icon name="route" size={27} /></span>detour<span className="brand-period">.</span></a>
      <div className="event-label"><span className="live-dot" /> CLOUD NATIVE · DEMO EDITION</div>
      <nav aria-label="Main navigation">{([['discover', 'grid', 'Discover sessions'], ['agenda', 'calendar', 'My agenda'], ['organizer', 'settings', 'Organizer']] as const).map(([id, icon, label]) =>
        <button key={id} className={`nav-item ${view === id ? 'active' : ''}`} aria-current={view === id ? 'page' : undefined} onClick={() => setView(id)}><Icon name={icon} />{label}{id === 'agenda' && !!savedIds.length && <span className="nav-count">{savedIds.length}</span>}</button>)}</nav>
      <button className="preferences-toggle" onClick={() => setPreferencesOpen(!preferencesOpen)} aria-expanded={preferencesOpen}><Icon name="settings" size={15} /> Interests & accessibility</button>
      <div className="sidebar-preferences"><span className="eyebrow">YOUR INTERESTS</span><p>A little more you.<br />A better next recommendation.</p><div className="interest-list">{['kubernetes', 'networking', 'ebpf', 'security', 'observability', 'ai', 'platform', 'gitops'].map(t =>
        <button key={t} aria-pressed={preferences.topics.includes(t)} className={preferences.topics.includes(t) ? 'selected' : ''} disabled={!!busy || initializing} onClick={() => togglePreference('topics', t)}>{labels[t]}{preferences.topics.includes(t) && <Icon name="check" size={12} />}</button>)}</div></div>
      <fieldset className="accessibility"><legend>WHAT WORKS FOR YOU</legend><p>Use fictional venue metadata to filter sessions.</p>{['step_free', 'captions', 'hearing_loop', 'quiet_space'].map(a => <label key={a}><input type="checkbox" checked={preferences.accessibility.includes(a)} disabled={!!busy || initializing} onChange={() => togglePreference('accessibility', a)} />{labels[a]}</label>)}</fieldset>
      <div className="sidebar-bottom"><span className="avatar">D</span><div>Curious by default.<small>Your anonymous demo agenda</small></div></div>
    </aside>
    <div className="page-shell">
      <header className="topbar"><div className="breadcrumb">Cloud Native Conference <span>/</span> <strong>{view === 'discover' ? 'Discover' : view === 'agenda' ? 'My agenda' : 'Organizer'}</strong></div><div className="topbar-right"><span className="demo-pill">DEMO DATA</span><label className="timezone"><span className="sr-only">Display time zone</span><Icon name="clock" size={15} /><select value={zone} onChange={e => setZone(e.target.value)}><option value="America/Denver">Mountain Time</option><option value="UTC">UTC</option><option value={Intl.DateTimeFormat().resolvedOptions().timeZone}>Your time zone</option></select></label></div></header>
      <main id="main" tabIndex={-1}>
        {error && <div className="error-banner" role="alert"><Icon name="alert" /><span>{error}</span><button onClick={() => { setError(''); void refresh(true); }} aria-label="Retry loading"><Icon name="refresh" /></button></div>}
        <div className="notice" role="status" aria-live="polite">{notice}</div>
        {view === 'discover' && <>
          <section className="hero"><div><div className="eyebrow"><span className="small-line" /> FOLLOW YOUR CURIOSITY</div><h1>A change of plans.<br /><em>A world of possibilities.</em></h1><p>Find the talks that move you forward.<br className="mobile-break" /> We’ll take care of the detours.</p></div><div className="route-art" aria-hidden="true"><svg viewBox="0 0 240 180"><path d="M25 155V80q0-20 20-20h65q20 0 20 20v35q0 20 20 20h35q20 0 20-20V30" fill="none" stroke="#cad8b4" strokeWidth="26" strokeLinecap="round"/><path d="M25 155V80q0-20 20-20h65q20 0 20 20v35q0 20 20 20h35q20 0 20-20V30" fill="none" stroke="#f6f7ee" strokeWidth="2" strokeDasharray="5 6"/><circle cx="25" cy="155" r="8" fill="#254b3d"/><circle cx="205" cy="30" r="18" fill="#254b3d"/><path d="m197 31 6 6 10-12" fill="none" stroke="#d9edab" strokeWidth="3"/></svg><span className="art-caption">GOOD THINGS HAPPEN<br />OFF THE ORIGINAL PATH.</span></div></section>
          <section className="search-box" aria-label="Find sessions"><form onSubmit={e => { e.preventDefault(); setSubmitted(query); }}><Icon name="search" size={24} /><label className="sr-only" htmlFor="session-search">Search sessions</label><input id="session-search" type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="What would you love to learn?" maxLength={500} /><button className="primary" type="submit" disabled={initializing}>Find my sessions <Icon name="arrow" /></button></form><div className="search-examples"><span>A little inspiration</span>{['Kubernetes security', 'eBPF & networking', 'AI infrastructure'].map(q => <button key={q} onClick={() => performSearch(q)}>{q} <span>↗</span></button>)}</div></section>
          {!!agenda?.affected.length && <div className="disruption-banner"><span className="disruption-icon"><Icon name="route" size={25} /></span><div><strong>A little detour is in order.</strong><p>{agenda.affected.length} saved session{agenda.affected.length === 1 ? ' has' : 's have'} changed. Let’s find your next best experience.</p></div><button className="primary" onClick={() => { setView('agenda'); void refresh(true); }}>Find my detour <Icon name="arrow" /></button></div>}
          <div className="content-grid"><section aria-label="Session results"><div className="section-heading"><div><span className="eyebrow">THE PROGRAM</span><h2>{submitted ? 'Your discoveries' : 'Find your next spark'} <span className="count">{results.length}</span></h2></div><span className="muted">30 fictional sessions · 5 rooms</span></div>
            <div className="filters"><label><span className="sr-only">Filter topic</span><select value={topic} onChange={e => setTopic(e.target.value)}><option value="">All topics</option>{(meta?.topics || []).map(t => <option value={t} key={t}>{labels[t]}</option>)}</select></label><label><span className="sr-only">Filter level</span><select value={level} onChange={e => setLevel(e.target.value)}><option value="">All levels</option><option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select></label><label><span className="sr-only">Sessions starting after</span><select value={after} onChange={e => setAfter(e.target.value)}><option value="">Any time</option><option value="13:00">After lunch · 1 PM MT</option><option value="14:00">After 2 PM MT</option></select></label><label className="retrieval"><span className="sr-only">Search method</span><select value={mode} onChange={e => setMode(e.target.value)}><option value="hybrid">{meta?.semantic_search ? 'Meaning + keywords' : 'Keyword preview'}</option><option value="keyword">Keywords only</option>{meta?.semantic_search && <option value="semantic">Meaning only</option>}</select></label></div>
            <div className="results-note" role="status">{searching ? 'Finding your next possibility…' : submitted ? `${results.length} available sessions for “${submitted}”` : 'A full day of fresh perspectives. Where will you start?'}</div>
            <div className={`session-grid ${searching ? 'loading' : ''}`} aria-busy={searching}>{results.map(s => <article className={`session-card ${topicClass(s)}`} key={s.id} data-testid={`session-${s.id}`}><div className="card-top"><span className="topic-label">{labels[s.topics[0]]}</span><span className="level">{s.level}</span></div><h3>{s.title}</h3><p className="abstract">{s.abstract}</p><div className="speaker"><span className="speaker-avatar">{s.speaker.split(' ').at(-1)}</span>{s.speaker}<span className="fictional">fictional</span></div><div className="card-meta"><span><Icon name="clock" size={14} />{time(s.start, zone)} – {time(s.end, zone)}</span><span><Icon name="pin" size={14} />{s.room} · {s.building}</span></div><div className="card-bottom"><div className="access-tags">{s.accessibility_verified_demo && s.accessibility.step_free && <span title="Fictional demo metadata">Step-free</span>}{s.accessibility_verified_demo && s.accessibility.captions && <span title="Fictional demo metadata">CC</span>}{!s.accessibility_verified_demo && <span>Access unverified</span>}</div><button className={`save-button ${savedIds.includes(s.id) ? 'saved' : ''}`} disabled={!!busy || initializing} onClick={() => save(s)} aria-label={`${savedIds.includes(s.id) ? 'Remove' : 'Save'} ${s.title}`}><Icon name={savedIds.includes(s.id) ? 'check' : 'plus'} size={15} />{savedIds.includes(s.id) ? 'Saved' : 'Save session'}</button></div></article>)}</div>
            {!searching && !results.length && <div className="empty-state"><Icon name="search" size={32} /><h3>A different path awaits.</h3><p>Try another phrase, a broader topic, or fewer filters.</p><button className="wide-button" onClick={() => { setQuery(''); setSubmitted(''); setTopic(''); setLevel(''); setAfter(''); }}>Clear search filters</button></div>}
          </section>{agendaPanel()}</div>
        </>}
        {view === 'agenda' && <><section className="page-heading"><span className="eyebrow">A DAY THAT FITS YOU</span><h1>Your plans, <em>with possibilities.</em></h1><p>Keep the sessions you love. Find a fresh direction when things change.</p></section><div className="agenda-layout">{agendaPanel(true)}<section className="replan-panel" aria-label="Replacement recommendations"><div className="panel-title"><div><span className="eyebrow">YOUR NEXT BEST EXPERIENCE</span><h2>A good day has options.</h2></div><Icon name="route" size={25} /></div>
          {plan?.disruption ? <><div className="original-session"><span className="status-badge"><Icon name="alert" size={14} /> PLAN CHANGED</span><h3>{plan.disruption.session?.title || 'Unavailable session'}</h3><p>{plan.disruption.reason}</p></div><p className="recommendation-intro">{plan.recommendations.length ? 'Here are a few paths worth taking. Every option is checked against your current agenda.' : plan.message}</p>{plan.recommendations.map((r, i) => <article className="recommendation" key={r.session.id}><div className="recommendation-rank">{i === 0 ? '↗ YOUR RECOMMENDED DETOUR' : `ANOTHER POSSIBILITY · 0${i + 1}`}</div><h3>{r.session.title}</h3><div className="rec-meta">{time(r.session.start, zone)} – {time(r.session.end, zone)} · {r.session.room}, {r.session.building}</div><p>{r.session.abstract}</p><ul>{r.explanation.map(line => <li key={line}><Icon name="check" size={15} />{line}</li>)}</ul><div className="recommendation-actions"><button className="primary" disabled={!!busy} onClick={() => void mutate('/api/agenda', { action: 'accept', session_id: plan.disruption!.session_id, replacement_id: r.session.id }, 'Detour accepted. Your agenda is up to date.', r.session.id)}>Take this detour <Icon name="arrow" /></button><button className="text-button" disabled={!!busy} onClick={() => void mutate('/api/agenda', { action: 'reject', session_id: plan.disruption!.session_id, replacement_id: r.session.id }, 'Alternative dismissed.', r.session.id)} aria-label={`Dismiss ${r.session.title}`}>Not for me</button></div></article>)}{plan.remaining_disruptions > 1 && <p className="muted">We’ll check the next affected session after this one is resolved.</p>}</> : <div className="empty-state"><div className="empty-icon"><Icon name="check" size={28} /></div><h3>{savedIds.length ? 'You’re on a good path.' : 'Your next adventure starts here.'}</h3><p>{savedIds.length ? 'Your saved sessions fit together. We’ll check for changes while you explore.' : 'Discover a session and add it to your day.'}</p><button className="wide-button" onClick={() => setView('discover')}>Explore the program <Icon name="arrow" /></button></div>}
        </section></div></>}
        {view === 'organizer' && <><section className="page-heading organizer-heading"><div><span className="eyebrow">BEHIND THE SCENES</span><h1>Plans change.<br /><em>Keep everyone moving.</em></h1><p>Changes here update search and attendee recommendations.</p></div><button className="reset-button" disabled={!!busy} onClick={() => { if (window.confirm('Reset the fictional program, disruptions and all demo agendas for everyone?')) void mutate('/api/demo/reset', {}, 'Demo program and agendas reset.', 'reset'); }}><Icon name="refresh" />Reset demo</button></section><div className="demo-callout"><Icon name="leaf" size={24} /><div><strong>A safe place for a change of plans.</strong><p>All sessions, speakers, occupancy states, transfer times and accessibility details are fictional. Organizer controls affect shared demonstration data only.</p></div></div>
          <div className="organizer-stats"><div><strong>{allSessions.length}</strong><span>fictional sessions</span></div><div><strong>{allSessions.filter(s => s.status === 'scheduled' && s.capacity_state === 'available').length}</strong><span>available sessions</span></div><div><strong>{events.length}</strong><span>recorded changes</span></div></div>
          <div className="organizer-table" role="region" aria-label="Manage demo sessions" tabIndex={0}><table><thead><tr><th>Session</th><th>Time</th><th>Room</th><th>Status</th><th>Demo controls</th></tr></thead><tbody>{allSessions.map(s => <tr key={s.id}><td><strong>{s.title}</strong><small>{s.topics.map(t => labels[t]).join(' · ')}</small>{editing === s.id && <SessionEditor session={s} busy={!!busy} onClose={() => setEditing(null)} onSave={body => { setEditing(null); void mutate('/api/demo/disruptions', body, 'Session updated. Affected agendas will be checked.', s.id); }} />}</td><td>{time(s.start, zone)}<small>{time(s.end, zone)}</small></td><td>{s.room}<small>{s.building}</small></td><td><span className={`availability ${s.status === 'canceled' || s.capacity_state === 'full' ? 'unavailable' : ''}`}>{s.status === 'canceled' ? 'Canceled' : s.capacity_state === 'full' ? 'Room full' : 'Available'}</span></td><td><div className="table-actions">{s.status === 'scheduled' && s.capacity_state === 'available' ? <><button disabled={!!busy} onClick={() => void mutate('/api/demo/disruptions', { session_id: s.id, event_type: 'room_full' }, 'Room marked full for this session.', s.id)} aria-label={`Mark ${s.title} full`}>Mark full</button><button disabled={!!busy} onClick={() => void mutate('/api/demo/disruptions', { session_id: s.id, event_type: 'cancel' }, 'Session canceled. Affected agendas will be checked.', s.id)} aria-label={`Cancel ${s.title}`}>Cancel</button></> : <button disabled={!!busy} onClick={() => void mutate('/api/demo/disruptions', { session_id: s.id, event_type: 'reopen' }, 'Session reopened.', s.id)} aria-label={`Reopen ${s.title}`}>Reopen</button>}<button disabled={!!busy} onClick={() => setEditing(editing === s.id ? null : s.id)} aria-label={`Edit ${s.title}`}>Edit</button></div></td></tr>)}</tbody></table></div>
          {events.length > 0 && <section className="change-log"><span className="eyebrow">RECENT CHANGES</span>{events.slice(0, 6).map(e => <div key={e.id}><span className="change-dot" /><strong>{allSessions.find(s => s.id === e.session_id)?.title || e.session_id}</strong><span>{e.event_type.replace('_', ' ')} · {time(e.timestamp, zone)}</span></div>)}</section>}
        </>}
        <footer><span><span className="footer-brand">detour.</span> A little flexibility. A better conference.</span><span>{meta?.store === 'elasticsearch' && meta.ready ? 'Elasticsearch connected · Jina semantic search' : 'Local preview · keyword search · temporary state'} <span className="footer-version">{meta?.version}</span></span></footer>
      </main>
    </div>
  </div>;
}

function SessionEditor({ session, busy, onSave, onClose }: { session: Session; busy: boolean; onSave: (body: unknown) => void; onClose: () => void }) {
  const localTime = (iso: string) => new Intl.DateTimeFormat('en-GB', { timeZone: 'America/Denver', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(iso));
  const [start, setStart] = useState(localTime(session.start));
  const [end, setEnd] = useState(localTime(session.end));
  const [room, setRoom] = useState(session.room);
  const [building, setBuilding] = useState(session.building);
  return <form className="session-editor" onSubmit={e => { e.preventDefault(); const values: Record<string, string> = { session_id: session.id, event_type: 'update' }; if (start !== localTime(session.start)) values.start = `2026-11-09T${start}:00-07:00`; if (end !== localTime(session.end)) values.end = `2026-11-09T${end}:00-07:00`; if (room !== session.room) values.room = room; if (building !== session.building) values.building = building; onSave(values); }}><div className="editor-times"><label>Starts · Mountain Time<input aria-label="New start time" type="time" value={start} required onChange={e => setStart(e.target.value)} /></label><label>Ends · Mountain Time<input aria-label="New end time" type="time" value={end} required onChange={e => setEnd(e.target.value)} /></label></div><label>Room<input value={room} maxLength={60} required onChange={e => setRoom(e.target.value)} /></label><label>Building<select value={building} onChange={e => setBuilding(e.target.value)}><option>Summit</option><option>Canyon</option></select></label><p>Moving rooms clears the previous accessibility verification.</p><div className="table-actions"><button type="submit" disabled={busy}>Save changes</button><button type="button" onClick={onClose}>Close editor</button></div></form>;
}
