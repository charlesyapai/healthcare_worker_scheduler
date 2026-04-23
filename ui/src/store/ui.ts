/**
 * Client-only UI preferences (theme, collapsed sections, etc.). Persisted to
 * localStorage so a tab refresh restores them. Session data lives in the
 * backend — don't mix it into this store.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

type Theme = "light" | "dark";

interface UIState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  gettingStartedOpen: boolean;
  toggleGettingStarted: () => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      theme: "light",
      setTheme: (theme) => set({ theme }),
      toggleTheme: () => set((s) => ({ theme: s.theme === "dark" ? "light" : "dark" })),
      gettingStartedOpen: false,
      toggleGettingStarted: () =>
        set((s) => ({ gettingStartedOpen: !s.gettingStartedOpen })),
    }),
    { name: "hws-ui" },
  ),
);

/** Apply the current theme to <html>. Call once on app mount. */
export function useThemeEffect(): void {
  const theme = useUIStore((s) => s.theme);
  // Set synchronously so the initial paint is correct.
  if (typeof document !== "undefined") {
    const root = document.documentElement;
    if (theme === "dark") root.classList.add("dark");
    else root.classList.remove("dark");
  }
}
