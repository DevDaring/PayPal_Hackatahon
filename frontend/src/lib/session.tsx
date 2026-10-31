import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import type { Me } from "./types";

type Session = { me: Me | null; loading: boolean; refresh: () => Promise<void>; setMe: (m: Me | null) => void };
const Ctx = createContext<Session>({ me: null, loading: true, refresh: async () => {}, setMe: () => {} });

export function SessionProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const q = useQuery<Me | null>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api<Me>("/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
  });
  useEffect(() => {
    const h = () => qc.setQueryData(["me"], null);
    window.addEventListener("qg:unauthorized", h);
    return () => window.removeEventListener("qg:unauthorized", h);
  }, [qc]);
  const value: Session = {
    me: q.data ?? null,
    loading: q.isLoading,
    refresh: async () => { await qc.invalidateQueries({ queryKey: ["me"] }); },
    setMe: (m) => {
      // Identity or workspace changed: everything cached belongs to the old context.
      qc.removeQueries({ predicate: (x) => x.queryKey[0] !== "me" });
      qc.setQueryData(["me"], m);
    },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useSession = () => useContext(Ctx);
export const useRoles = () => {
  const { me } = useSession();
  const r = new Set(me?.roles ?? []);
  return { isRequester: r.has("requester") || r.has("admin"), isApprover: r.has("approver"), isAdmin: r.has("admin") };
};

export type PublicConfig = {
  paypal_client_id: string | null; paypal_adapter: string; currency: string; paypal_environment: string; demo_mode: boolean; demo_lab_enabled: boolean; timezone: string;
  sandbox_buyer: { email: string; password: string } | null; jury_login: { username: string; password: string } | null;
};
export const usePublicConfig = () => useQuery<PublicConfig>({ queryKey: ["public-config"], queryFn: () => api("/config/public"), staleTime: 300_000 });
