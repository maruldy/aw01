import { useEffect, useState } from "react";

export function useRunStream(threadId: string | null) {
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);

  useEffect(() => {
    if (!threadId) {
      setEvents([]);
      return;
    }

    const eventSource = new EventSource(`${import.meta.env.VITE_API_BASE_URL ?? ""}/runs/${threadId}/stream`);
    eventSource.onmessage = (event) => {
      setEvents((previous) => [...previous, JSON.parse(event.data)]);
    };

    return () => {
      eventSource.close();
    };
  }, [threadId]);

  return events;
}
