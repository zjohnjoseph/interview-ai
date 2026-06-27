// JWT lives in localStorage. Interviewer pages only — the candidate flow
// authenticates via the invite token in the URL, not this.

const TOKEN_KEY = "interviewai_token";

export function saveToken(token: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem(TOKEN_KEY, token);
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function clearToken(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function isAuthenticated(): boolean {
  const token = getToken();
  if (!token) return false;
  // Best-effort expiry check from the JWT payload; treat unparseable as valid
  // (the API still rejects bad tokens with a 401, which clears the session).
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    if (typeof payload.exp === "number" && payload.exp * 1000 < Date.now()) {
      return false;
    }
  } catch {
    return true;
  }
  return true;
}
