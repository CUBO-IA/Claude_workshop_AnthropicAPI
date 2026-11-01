export interface Candidate {
  index: number;
  parameter_id: string;
  parameter_name_es: string;
  option: string | null;
  score: number;
}

export interface ChatResponse {
  answer: string;
  found: boolean;
  parameter_id: string | null;
  value: string | null;
  parameter_name_es: string | null;
  option: string | null;
  section: string | null;
  candidates: Candidate[];
}

export class ApiError extends Error {}

/** Envía una pregunta al backend (mismo origen; en desarrollo Vite lo reenvía). */
export async function sendQuestion(question: string): Promise<ChatResponse> {
  let res: Response;
  try {
    res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
  } catch {
    throw new ApiError("No se pudo conectar con el servicio de soporte. Intenta de nuevo.");
  }

  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : "";
    } catch {
      /* respuesta sin JSON */
    }
    throw new ApiError(detail || `Error del servicio (HTTP ${res.status}).`);
  }
  return (await res.json()) as ChatResponse;
}
