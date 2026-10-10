import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Platform } from "react-native";
import * as Linking from "expo-linking";
import * as WebBrowser from "expo-web-browser";
import { storage } from "@/src/utils/storage";
import { api, request, setToken, setUnauthorizedHandler, TOKEN_KEY } from "@/src/api";
import { queryClient } from "@/src/query-client";

WebBrowser.maybeCompleteAuthSession();

const AUTH_URL = "https://auth.emergentagent.com/?redirect=";
const extractSid = (url?: string | null) => {
  const m = url?.match(/[?#&]session_id=([^&#]+)/);
  return m ? decodeURIComponent(m[1]) : null;
};

export type User = { id: string; email: string; name: string; role: "admin" | "cleaner" | "supervisor" | "owner"; property_ids?: string[]; phone?: string; picture?: string };
type AuthCtx = {
  user: User | null;
  loading: boolean;
  authError: string;
  login: (email: string, password: string) => Promise<User>;
  googleSignIn: () => Promise<void>;
  logout: () => Promise<void>;
};
const Ctx = createContext<AuthCtx>(null as any);

export function AuthProvider({ children }: React.PropsWithChildren) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState("");
  const sent = useRef(new Set<string>());

  const exchange = useCallback(async (sid: string) => {
    if (sent.current.has(sid)) return false;
    sent.current.add(sid);
    setAuthError("");
    try {
      const res = await request<{ session_token: string; user: User }>("/auth/session", { method: "POST", body: { session_id: sid } });
      await storage.secureSet(TOKEN_KEY, res.session_token);
      setToken(res.session_token);
      setUser(res.user);
      return true;
    } catch (e: any) {
      setAuthError(e.message || "Google sign-in failed");
      return false;
    }
  }, []);

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
      // 1) Process a Google sign-in callback first (web: URL; native cold start: initial deep link)
      let sid: string | null = null;
      if (Platform.OS === "web" && typeof window !== "undefined") {
        sid = extractSid(window.location.hash) || extractSid(window.location.search);
      } else {
        sid = extractSid(await Linking.getInitialURL());
      }
      if (sid && (await exchange(sid))) {
        if (Platform.OS === "web") {
          const u = new URL(window.location.href);
          u.searchParams.delete("session_id");
          const hash = u.hash.replace(/^#/, "").split("&").filter((x) => !x.startsWith("session_id=")).join("&");
          window.history.replaceState(window.history.state, "", u.pathname + u.search + (hash ? `#${hash}` : ""));
        }
        setLoading(false);
        return;
      }
      // 2) Otherwise restore the stored session
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
    if (Platform.OS === "web") return;
    const sub = Linking.addEventListener("url", (e) => {
      const s = extractSid(e.url);
      if (s) exchange(s);
    });
    return () => sub.remove();
  }, [logout, exchange]);

  const login = async (email: string, password: string) => {
    setAuthError("");
    const res = await request<{ access_token: string; user: User }>("/auth/login", { method: "POST", body: { email, password } });
    await storage.secureSet(TOKEN_KEY, res.access_token);
    setToken(res.access_token);
    setUser(res.user);
    return res.user;
  };

  const googleSignIn = async () => {
    setAuthError("");
    if (Platform.OS === "web") {
      window.location.href = AUTH_URL + encodeURIComponent(window.location.origin + "/");
      return;
    }
    const redirect = Linking.createURL("");
    let captured: string | null = null;
    const sub = Linking.addEventListener("url", (e) => {
      captured = e.url;
    });
    try {
      const r = await WebBrowser.openAuthSessionAsync(AUTH_URL + encodeURIComponent(redirect), redirect);
      const url = (r.type === "success" ? r.url : null) || captured || (await Linking.getInitialURL());
      const sid = extractSid(url);
      if (sid) await exchange(sid);
    } catch (e: any) {
      setAuthError(e.message || "Google sign-in failed");
    } finally {
      sub.remove();
    }
  };

  return <Ctx.Provider value={{ user, loading, authError, login, googleSignIn, logout }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
