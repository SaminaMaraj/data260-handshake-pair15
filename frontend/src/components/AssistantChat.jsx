import { useState } from "react";
import "./EventsAssistant.css";
export default function AssistantChat(){
  const [draft,setDraft]=useState(''),[messages,setMessages]=useState([]);
  function send(e){e.preventDefault();if(!draft.trim())return;setMessages([...messages,draft.trim()]);setDraft('');}
  return <section aria-labelledby="assistant-title" className="assistant-chat career-assistant">
    <header className="assistant-panel-heading"><span className="assistant-symbol" aria-hidden="true"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"><path d="M3 4h18v13H9l-6 4z M7 9h10 M7 13h6" /></svg></span><div><span className="assistant-eyebrow">YOUR CAREER WORKSPACE</span><h2 id="assistant-title">AI Assistant</h2></div><span className="assistant-connection">Not connected</span></header>
    <p id="assistant-scope" className="assistant-scope">Part A chat interface. Messages stay in this session. AI responses require the Part B agent, which is not connected. Sending a message here does not execute any assistant action.</p>
    {!messages.length && <div className="assistant-empty"><h3>A space for your next career question.</h3><p>You can add messages below. Replies and assistant actions will be available only when the backend agent is connected.</p></div>}
    <div className="assistant-conversation" role="log" aria-live="polite" aria-label="Chat conversation">{messages.map((text,i)=><div className="assistant-message-row" key={i}><div className="assistant-user-bubble"><span>You</span><p>{text}</p></div></div>)}</div>
    <form onSubmit={send} className="assistant-composer"><label htmlFor="assistant-message">Your message</label>
      <textarea id="assistant-message" aria-describedby="assistant-scope" placeholder="Write your career question…" maxLength={2000} value={draft} onChange={e=>setDraft(e.target.value)} required />
      <div className="assistant-composer-footer"><span>{draft.length}/2000 characters</span><div><button className="assistant-clear" type="button" onClick={()=>{setMessages([]);setDraft('');}}>Clear Conversation</button><button type="submit" disabled={!draft.trim()}>Send Message <span aria-hidden="true">↑</span></button></div></div>
    </form>
    {messages.length>0&&<p className="assistant-local-status" role="status">Message added locally. No AI response is generated in Part A.</p>}
  </section>;
}
