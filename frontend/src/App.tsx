import { FormEvent, useEffect, useRef, useState } from "react";
import { ApiError, ChatResponse, sendQuestion } from "./api";

type Message =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "assistant"; data: ChatResponse }
  | { id: number; role: "assistant"; error: string };

const SUGGESTIONS = [
  "¿Cómo configuro la fuente de movimiento a ignición?",
  "¿Cómo configuro el APN del GPRS?",
  "¿Cómo activo la detección de choque?",
  "¿Cómo configuro la calibración automática del acelerómetro?",
];

let nextId = 1;

function AssistantAnswer({ data }: { data: ChatResponse }) {
  if (!data.found) {
    return <p className="bubble-text">{data.answer}</p>;
  }
  return (
    <>
      <code className="answer-code">{data.answer}</code>
      <dl className="answer-meta">
        <div>
          <dt>Parámetro</dt>
          <dd>{data.parameter_name_es}</dd>
        </div>
        {data.option && (
          <div>
            <dt>Opción</dt>
            <dd>{data.option}</dd>
          </div>
        )}
        {data.section && (
          <div>
            <dt>Sección</dt>
            <dd>{data.section}</dd>
          </div>
        )}
      </dl>
      {data.candidates.length > 0 && (
        <details className="candidates">
          <summary>Candidatos consultados ({data.candidates.length})</summary>
          <ul>
            {data.candidates.map((c) => (
              <li key={c.index}>
                <span className="cand-id">ID {c.parameter_id}</span>
                {c.parameter_name_es}
                {c.option && <span className="cand-opt"> · {c.option}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const empty = messages.length === 0;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  async function ask(question: string) {
    const q = question.trim();
    if (q.length < 3 || loading) return;
    setMessages((m) => [...m, { id: nextId++, role: "user", text: q }]);
    setInput("");
    setLoading(true);
    try {
      const data = await sendQuestion(q);
      setMessages((m) => [...m, { id: nextId++, role: "assistant", data }]);
    } catch (err) {
      const text = err instanceof ApiError ? err.message : "Ocurrió un error inesperado.";
      setMessages((m) => [...m, { id: nextId++, role: "assistant", error: text }]);
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void ask(input);
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7z" />
              <circle cx="12" cy="9" r="2.5" />
            </svg>
          </span>
          <div>
            <h1>Soporte FMC130</h1>
            <p>Configuración de parámetros Teltonika</p>
          </div>
        </div>
      </header>

      <main className="chat">
        <div className="chat-inner">
          {empty && (
            <section className="welcome">
              <h2>¿Qué parámetro quieres configurar?</h2>
              <p>Escribe tu pregunta en español. Te responderé con el ID y el valor del parámetro según la documentación oficial.</p>
              <div className="suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" className="chip" onClick={() => void ask(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </section>
          )}

          {messages.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className="row row-user">
                <div className="bubble bubble-user">{m.text}</div>
              </div>
            ) : (
              <div key={m.id} className="row row-assistant">
                <div className={"avatar"} aria-hidden="true">FM</div>
                <div className={"bubble bubble-assistant" + ("error" in m ? " bubble-error" : "")}>
                  {"error" in m ? <p className="bubble-text">{m.error}</p> : <AssistantAnswer data={m.data} />}
                </div>
              </div>
            ),
          )}

          {loading && (
            <div className="row row-assistant">
              <div className="avatar" aria-hidden="true">FM</div>
              <div className="bubble bubble-assistant typing" aria-label="Buscando respuesta">
                <span /><span /><span />
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>
      </main>

      <footer className="composer">
        <form className="composer-inner" onSubmit={onSubmit}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Escribe tu pregunta sobre el FMC130…"
            maxLength={500}
            aria-label="Pregunta"
            disabled={loading}
          />
          <button type="submit" className="send" disabled={loading || input.trim().length < 3}>
            Enviar
          </button>
        </form>
        <p className="disclaimer">Respuestas basadas en la documentación oficial de Teltonika.</p>
      </footer>
    </div>
  );
}
