import { useEffect, useRef, useState } from 'react';
import { apiRequest } from '../api';
import './EventsAssistant.css';

export default function AssistantChat({ user, onUnauthorized }) {
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState([]);
  const [conversation, setConversation] = useState([]);
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [sending, setSending] = useState('');
  const locked = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const available = user?.role === 'student' && !!user?.access_token;

  function accept(result, userMessage) {
    if (!Array.isArray(result.conversation) || typeof result.answer !== 'string' ||
        (result.status === 'pending_confirmation' && !result.pending_id)) {
      throw new Error('The assistant returned an invalid response. Please retry.');
    }
    setConversation(result.conversation);
    setMessages(previous => [...previous, { role: 'user', content: userMessage }, { role: 'assistant', content: result.answer }]);
    setPending(result.status === 'pending_confirmation' ? result.pending_id : null);
  }
  async function send(event) {
    event.preventDefault();
    if (!available || locked.current || pending || !draft.trim()) return;
    const message = draft.trim();
    locked.current = true; setBusy(true); setError(''); setSending(message);
    try {
      const result = await apiRequest('/assistant/chat', { method: 'POST', token: user.access_token,
        onUnauthorized, body: { message, conversation } });
      if (!mounted.current) return;
      accept(result, message); setDraft('');
    } catch (err) { if (mounted.current) setError(err.message); }
    finally {
      locked.current = false;
      if (mounted.current) { setBusy(false); setSending(''); }
    }
  }
  async function confirm(approve) {
    if (!available || !pending || locked.current) return;
    locked.current = true; setBusy(true); setError('');
    try {
      const result = await apiRequest('/assistant/confirm', { method: 'POST', token: user.access_token,
        onUnauthorized, body: { pending_id: pending, approve } });
      if (mounted.current) accept(result, approve ? 'Yes, approve this save.' : 'No, cancel this save.');
    } catch (err) {
      if (mounted.current) {
        setError(err.message);
        if ([404, 409, 410].includes(err.status)) setPending(null);
      }
    } finally { locked.current = false; if (mounted.current) setBusy(false); }
  }
  function clear() {
    if (locked.current) return;
    setMessages([]); setConversation([]); setDraft(''); setPending(null); setError('');
  }
  return <section aria-labelledby="assistant-title" className="assistant-chat career-assistant">
    <header className="assistant-panel-heading"><span className="assistant-symbol" aria-hidden="true"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"><path d="M3 4h18v13H9l-6 4z M7 9h10 M7 13h6" /></svg></span><div><span className="assistant-eyebrow">YOUR CAREER WORKSPACE</span><h2 id="assistant-title">AI Assistant</h2></div><span className="assistant-connection">{available ? 'Student assistant' : 'Student accounts only'}</span></header>
    <p id="assistant-scope" className="assistant-scope">{available ? 'Ask about jobs, events, and your preferences. Saving an opportunity requires your explicit Yes approval. Replies require the backend assistant service to be available.' : 'Sign in with a student account to use the career assistant.'}</p>
    {!messages.length && !busy && <div className="assistant-empty"><h3>A space for your next career question.</h3><p>Ask a question to explore real opportunities and continue with follow-up questions.</p></div>}
    <div className="assistant-conversation" role="log" aria-live="polite" aria-label="Chat conversation">{messages.map((message, index) => <div className={`assistant-message-row${message.role === 'assistant' ? ' is-assistant' : ''}`} key={index}><div className={message.role === 'assistant' ? 'assistant-answer-bubble' : 'assistant-user-bubble'}><span>{message.role === 'assistant' ? 'Assistant' : 'You'}</span><p>{message.content}</p></div></div>)}</div>
    {busy && <p className="assistant-local-status" role="status">{sending ? 'Waiting for the assistant…' : 'Processing your decision…'}</p>}
    {pending && <section className="assistant-confirmation" aria-label="Confirm save"><h3>Approve this save?</h3><p>Choose Yes to save the opportunity described above, or No to cancel. Approval expires after 10 minutes.</p><div><button type="button" disabled={busy} onClick={() => confirm(true)}>Yes</button><button type="button" className="assistant-clear" disabled={busy} onClick={() => confirm(false)}>No</button></div></section>}
    {error && <p className="assistant-error" role="alert">{error}</p>}
    <form onSubmit={send} className="assistant-composer"><label htmlFor="assistant-message">Your message</label><textarea id="assistant-message" aria-describedby="assistant-scope" placeholder="Write your career question…" maxLength={2000} value={draft} onChange={event => setDraft(event.target.value)} disabled={!available || busy || !!pending} required />
      <div className="assistant-composer-footer"><span>{draft.length}/2000 characters</span><div><button className="assistant-clear" type="button" disabled={busy} onClick={clear}>Clear Conversation</button><button type="submit" disabled={!available || busy || !!pending || !draft.trim()}>{busy ? 'Please wait…' : 'Send Message'} <span aria-hidden="true">↑</span></button></div></div>
    </form>
  </section>;
}
