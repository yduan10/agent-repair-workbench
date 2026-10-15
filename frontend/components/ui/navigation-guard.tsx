"use client";
import { createContext, useCallback, useContext, useEffect, useRef } from "react";

type Guard = () => boolean;
type GuardApi = { register: (guard: Guard) => () => void; allow: () => boolean };
const GuardContext = createContext<GuardApi>({ register: () => () => {}, allow: () => true });

/** Lets a page (e.g. an unsaved evidence draft) veto in-app navigation from the shell. */
export function NavigationGuardProvider({ children }: { children: React.ReactNode }) {
  const guards = useRef(new Set<Guard>());
  const register = useCallback((guard: Guard) => { guards.current.add(guard); return () => { guards.current.delete(guard); }; }, []);
  const allow = useCallback(() => [...guards.current].every(guard => guard()), []);
  return <GuardContext.Provider value={{ register, allow }}>{children}</GuardContext.Provider>;
}
export function useNavigationGuard(guard: Guard) {
  const { register } = useContext(GuardContext);
  const latest = useRef(guard);
  useEffect(() => { latest.current = guard; });
  useEffect(() => register(() => latest.current()), [register]);
}
export function useAllowNavigation() {
  return useContext(GuardContext).allow;
}
