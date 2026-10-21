import { useEffect, useState } from "react";

// Tiny hash router: "#/explorer/gpt-01" -> ["explorer", "gpt-01"].
// Hash routing needs no server rewrites, so the static site works on any host.
function read(): string[] {
  return window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
}

export function useRoute(): string[] {
  const [route, setRoute] = useState<string[]>(read);
  useEffect(() => {
    const on = () => setRoute(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}
