import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { storage } from "@/src/utils/storage";
import { api, request, setToken, setUnauthorizedHandler, TOKEN_KEY } from "@/src/api";
import { queryClient } from "@/src/query-client";

export type User = { id: string; email: string; name: string; role: "admin" | "cleaner" | "owner"; property_ids?: string[] };
type AuthCtx = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
};
const Ctx = createContext<AuthCtx>(null as any);

export function AuthProvider({ children }: React.PropsWithChildren) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(async () => {
    await storage.secureRemove(TOKEN_KEY);
    setToken(null);
    setUser(null);
    queryClient.clear();
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      logout();
    });
    (async () => {
      const t = await storage.secureGet<string | null>(TOKEN_KEY, null);
      if (t) {
        setToken(t);
        try {
          setUser(await api.get<User>("/auth/me"));
        } catch {
          await logout();
        }
      }
      setLoading(false);
    })();
  }, [logout]);

  const login = async (email: string, password: string) => {
    const res = await request<{ access_token: string; user: User }>("/auth/login", { method: "POST", body: { email, password } });
    await storage.secureSet(TOKEN_KEY, res.access_token);
    setToken(res.access_token);
    setUser(res.user);
    return res.user;
  };

  return <Ctx.Provider value={{ user, loading, login, logout }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
