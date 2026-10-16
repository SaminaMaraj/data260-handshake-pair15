import { useState } from "react";
export default function AssistantChat(){
  const [draft,setDraft]=useState(''),[messages,setMessages]=useState([]);
  function send(e){e.preventDefault();if(!draft.trim())return;setMessages([...messages,draft.trim()]);setDraft('');}
  return <section aria-labelledby="assistant-title" className="assistant-chat card p-3 mt-4">
    <h2 id="assistant-title">AI Assistant</h2>
    <p id="assistant-scope">Part A chat interface. Messages stay in this session. AI responses require the Part B agent, which is not connected.</p>
    <div role="log" aria-live="polite" aria-label="Chat conversation">{messages.map((text,i)=><p key={i}><strong>You:</strong> {text}</p>)}</div>
    <form onSubmit={send}><label htmlFor="assistant-message">Your message</label>
      <textarea id="assistant-message" aria-describedby="assistant-scope" maxLength={2000} value={draft} onChange={e=>setDraft(e.target.value)} required />
      <button type="submit" disabled={!draft.trim()}>Send Message</button>
      <button type="button" onClick={()=>{setMessages([]);setDraft('');}}>Clear Conversation</button>
    </form>
    {messages.length>0&&<p role="status">Message added. No AI response is generated in Part A.</p>}
  </section>;
}
