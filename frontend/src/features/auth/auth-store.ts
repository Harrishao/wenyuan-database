import { create } from "zustand";

import type { User } from "@/contracts/api";
import { api, setAccessToken } from "@/lib/api-client";

interface AuthState {
  user: User | null;
  initializing: boolean;
  bootstrap: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (displayName: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  replaceUser: (user: User) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  initializing: true,
  bootstrap: async () => {
    try {
      const auth = await api.refresh();
      setAccessToken(auth.access_token);
      set({ user: auth.user });
    } catch {
      setAccessToken(null);
      set({ user: null });
    } finally {
      set({ initializing: false });
    }
  },
  login: async (email, password) => {
    const auth = await api.login({ email, password });
    setAccessToken(auth.access_token);
    set({ user: auth.user });
  },
  register: async (displayName, email, password) => {
    const auth = await api.register({ display_name: displayName, email, password });
    setAccessToken(auth.access_token);
    set({ user: auth.user });
  },
  logout: async () => {
    try {
      await api.logout();
    } finally {
      setAccessToken(null);
      set({ user: null });
    }
  },
  replaceUser: (user) => set({ user }),
}));
