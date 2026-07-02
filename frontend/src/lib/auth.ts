import axios from "axios";

const TOKEN_KEY = "crawler_access_token";
const USER_KEY = "crawler_user";

export interface AuthUser {
  id: string;
  email: string;
  username: string;
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function setSession(token: string, user: AuthUser) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  delete axios.defaults.headers.common["Authorization"];
}

/** Call once on app load to restore the session into axios' default headers. */
export function restoreSession(): AuthUser | null {
  const token = getToken();
  const user = getUser();
  if (!token || !user) return null;
  axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  return user;
}
