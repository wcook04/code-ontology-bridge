import { useEffect, useState } from "react";
import { readRoute } from "./client";

export type Loaded<T> = { state: "loading" } | { state: "error"; error: Error } | { state: "ready"; data: T };

/** One route's data. A response for a route the component no longer shows is dropped. */
export function useRoute<T>(route: string | null): Loaded<T> {
  const [value, setValue] = useState<{ route: string | null; loaded: Loaded<T> }>({ route, loaded: { state: "loading" } });
  useEffect(() => {
    if (!route) return;
    let current = true;
    setValue({ route, loaded: { state: "loading" } });
    readRoute<T>(route).then(
      (data) => current && setValue({ route, loaded: { state: "ready", data } }),
      (error: Error) => current && setValue({ route, loaded: { state: "error", error } }),
    );
    return () => {
      current = false;
    };
  }, [route]);
  return value.route === route ? value.loaded : { state: "loading" };
}
