"use client";

import { useCallback, useEffect, useReducer, useState } from "react";

import { streamUrl } from "./api";
import { EVENT_NAMES, isFinal, type StreamEvent } from "./events";
import { initialState, reduce, type ReportState } from "./reportState";

type Run = { nonce: number; refresh: boolean };

/**
 * Open the research stream for a ticker and fold its events into report state.
 *
 * The stream is closed after `report` or a terminal `error`, so the browser never reconnects and starts another run.
 * A connection failure before any event means the backend is unreachable; after some events, the connection was lost.
 */
export function useResearchStream(ticker: string): {
  state: ReportState;
  retry: () => void;
  refresh: () => void;
} {
  const [state, dispatch] = useReducer(reduce, undefined, initialState);
  const [run, setRun] = useState<Run>({ nonce: 0, refresh: false });

  useEffect(() => {
    const source = new EventSource(streamUrl(ticker, run.refresh));
    let received = 0;
    let finished = false;

    const listener = (name: StreamEvent["event"]) => (message: Event) => {
      // The server's `event: error` shares its name with EventSource's own connection error, which has no data.
      if (finished || !(message instanceof MessageEvent) || typeof message.data !== "string") return;
      let event: StreamEvent;
      try {
        const data: unknown = JSON.parse(message.data);
        if (data === null || typeof data !== "object" || Array.isArray(data)) {
          throw new Error("Research event data must be an object");
        }
        event = { event: name, data } as StreamEvent;
      } catch {
        finished = true;
        source.close();
        dispatch({
          type: "event",
          event: {
            event: "error",
            data: { stage: "stream", message: "The backend sent an invalid research event. Please retry.", terminal: true },
          },
        });
        return;
      }
      received += 1;
      dispatch({ type: "event", event });
      if (isFinal(event)) {
        finished = true;
        source.close();
      }
    };
    for (const name of EVENT_NAMES) source.addEventListener(name, listener(name));
    source.onopen = () => {
      if (!finished) dispatch({ type: "connection", status: "open" });
    };
    source.onerror = (message) => {
      // Named application errors also invoke onerror; only a transport error has no message payload.
      if (finished || message instanceof MessageEvent) return;
      finished = true;
      source.close();
      dispatch({ type: "connection", status: received === 0 ? "unreachable" : "lost" });
    };
    return () => {
      finished = true;
      source.close();
    };
  }, [ticker, run]);

  const restart = useCallback((refresh: boolean) => {
    dispatch({ type: "reset" });
    setRun((current) => ({ nonce: current.nonce + 1, refresh }));
  }, []);

  return { state, retry: () => restart(false), refresh: () => restart(true) };
}
