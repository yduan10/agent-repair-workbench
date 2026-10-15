"use client";
import { createContext, useContext } from "react";
import { useEnvironment, type EnvironmentState } from "../../lib/environment";

const EnvironmentContext = createContext<EnvironmentState | null>(null);

/** One shared poller for the whole workspace shell. */
export function EnvironmentProvider({ children }: { children: React.ReactNode }) {
  const environment = useEnvironment();
  return <EnvironmentContext.Provider value={environment}>{children}</EnvironmentContext.Provider>;
}
export function useEnvironmentStatus() {
  const value = useContext(EnvironmentContext);
  if (!value) throw new Error("useEnvironmentStatus must be used inside EnvironmentProvider");
  return value;
}
