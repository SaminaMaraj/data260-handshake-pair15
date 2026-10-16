import { useEffect, useRef, useState } from 'react';

const items = {
  student: [['dashboard', 'Dashboard', 'grid'], ['jobs', 'Jobs', 'briefcase'], ['saved', 'Saved Jobs', 'bookmark'], ['applications', 'Applications', 'file'], ['events', 'Events', 'calendar'], ['directory', 'Student Directory', 'users'], ['assistant', 'AI Assistant', 'chat'], ['profile', 'Profile', 'user'], ['preferences', 'Preferences', 'settings']],
  company: [['dashboard', 'Dashboard', 'grid'], ['company-jobs', 'My Job Posts', 'briefcase'], ['post-job', 'Post a Job', 'plus'], ['applicants', 'Applicants', 'file'], ['events', 'Events', 'calendar'], ['directory', 'Student Directory', 'users'], ['assistant', 'AI Assistant', 'chat'], ['profile', 'Company Profile', 'user']],
};
const paths = {
  grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  briefcase: 'M8 6V3h8v3 M3 7h18v14H3z M3 12c6 3 12 3 18 0 M12 11v5',
  bookmark: 'M6 3h12v18l-6-4-6 4z',
  file: 'M14 3H5v18h14V8z M14 3v5h5 M8 12h8 M8 16h6',
  calendar: 'M3 5h18v16H3z M7 3v4 M17 3v4 M3 10h18 M7 14h2 M14 14h2 M7 17h2',
  users: 'M16 21v-3c0-4-12-4-12 0v3 M20 21v-4c0-2-1-3-3-3 M8 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M16 3a4 4 0 0 1 0 8',
  user: 'M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M4 21v-3c0-6 16-6 16 0v3',
  chat: 'M3 4h18v13H9l-6 4z M7 9h10 M7 13h6',
  settings: 'M4 7h16 M4 17h16 M8 4v6 M16 14v6',
  plus: 'M12 4v16 M4 12h16', menu: 'M4 6h16 M4 12h16 M4 18h16',
  close: 'M6 6l12 12 M6 18L18 6', logout: 'M9 4H4v16h5 M9 12h12 M16 7l5 5-5 5',
};
function Icon({ name }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}

export default function AppShell({ user, page, onNavigate, onLogout, children }) {
  const [open, setOpen] = useState(false);
  const sidebar = useRef(null);
  const toggle = useRef(null);
  const heading = useRef(null);
  const name = user.full_name || user.company_name || user.name || user.email;
  const initials = name.split(/\s+|@/).filter(Boolean).slice(0, 2).map(word => word[0]).join('').toUpperCase();
  const role = user.role === 'company' ? 'Company' : 'Student';
  const active = page === 'job-details' ? 'jobs' : page;
  const title = page === 'job-details' ? 'Job Details' : items[user.role]?.find(([key]) => key === page)?.[1] || 'Dashboard';

  useEffect(() => {
    const media = window.matchMedia('(min-width: 1024px)');
    const resize = () => { if (media.matches) setOpen(false); };
    media.addEventListener('change', resize);
    return () => media.removeEventListener('change', resize);
  }, []);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    sidebar.current.querySelector('button').focus();
    function keyboard(event) {
      if (event.key === 'Escape') {
        setOpen(false);
        toggle.current.focus();
      }
      if (event.key === 'Tab') {
        const controls = [...sidebar.current.querySelectorAll('button, a[href]')];
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    }
    document.addEventListener('keydown', keyboard);
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener('keydown', keyboard); };
  }, [open]);

  function navigate(target) {
    setOpen(false);
    onNavigate(target === 'assistant' ? 'dashboard' : target);
    requestAnimationFrame(() => {
      const destination = target === 'assistant' ? document.getElementById('assistant-title') : heading.current;
      if (destination) {
        destination.setAttribute('tabindex', '-1');
        destination.focus({ preventScroll: true });
        destination.scrollIntoView({ block: 'start' });
      }
    });
  }

  return <div className="portal-shell">
    <a className="skip-link" href="#portal-content">Skip to content</a>
    {open && <div className="sidebar-backdrop" onClick={() => { setOpen(false); toggle.current.focus(); }} aria-hidden="true" />}
    <aside id="portal-sidebar" ref={sidebar} className={`portal-sidebar${open ? ' is-open' : ''}`} aria-label={`${role} navigation`}>
      <div className="sidebar-brand"><span className="brand-mark" aria-hidden="true">H<span>.</span></span><div><strong>Handshake</strong><span>PAIR 15 · CAREER PORTAL</span></div>
        <button className="sidebar-close" aria-label="Close navigation" onClick={() => { setOpen(false); toggle.current.focus(); }}><Icon name="close" /></button>
      </div>
      <p className="sidebar-caption">{role} workspace</p>
      <nav aria-label="Main navigation" className="sidebar-links">
        {(items[user.role] || []).map(([key, label, icon]) => <button key={key} className={`sidebar-link${(active === key) ? ' is-active' : ''}`}
          aria-current={(active === key) ? 'page' : undefined}
          onClick={() => navigate(key)}><Icon name={icon} /><span>{label}</span></button>)}
      </nav>
      <div className="sidebar-account"><div className="account-summary"><span className="portal-avatar" aria-hidden="true">{initials}</span><div><strong title={name}>{name}</strong><span>{role} account</span></div></div>
        <button className="sidebar-link logout-link" onClick={onLogout}><Icon name="logout" /><span>Logout</span></button>
      </div>
    </aside>
    <div className="portal-workspace" inert={open ? true : undefined}>
      <header className="portal-header"><div className="header-title"><button ref={toggle} className="sidebar-toggle" aria-label="Open navigation" aria-controls="portal-sidebar" aria-expanded={open} onClick={() => setOpen(true)}><Icon name="menu" /></button>
        <div><span className="header-eyebrow">{role} portal</span><h1 ref={heading} tabIndex={-1}>{title}</h1></div></div>
        <div className="header-account"><div><strong title={name}>{name}</strong><span>{role}</span></div><span className="portal-avatar" aria-hidden="true">{initials}</span></div>
      </header>
      <main id="portal-content" className="dashboard portal-content" tabIndex={-1}>{children}</main>
    </div>
  </div>;
}
