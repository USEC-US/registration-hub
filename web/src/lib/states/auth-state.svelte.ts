import type { CurrentUser } from '$lib/api/types'
import { getAccessToken, getRefreshToken, saveSession, clearSession } from '$lib/auth/session'
import { getCurrentUser, refreshAccessToken, signIn as requestSignIn } from '$lib/api/auth'
import { browser } from '$app/environment'
import { localizeInternalHref } from '$lib/navigation'
import { resolve } from '$app/paths'
import { replaceInternalLocation } from '$lib/auth/navigation'
import { ApiRequestError } from '$lib/api/client'


export type AuthStatus = 'idle' | 'loading' | 'signed-in' | 'signed-out' | 'unavailable'

export class AuthState {
  currentUser = $state<CurrentUser | null>(null)
  status = $state<AuthStatus>('idle')
  #initialization: Promise<CurrentUser | null> | null = null

  async initialize(): Promise<CurrentUser | null> {
    if (!browser) return null;

    const accessToken = getAccessToken();
    if (!accessToken) {
      this.signOut();
      return null;
    }

    if (this.#initialization) return this.#initialization;

    this.status = 'loading';
    this.#initialization = getCurrentUser(accessToken).then((user) => {
      this.currentUser = user;
      this.status = 'signed-in';
      return user;
    })
      .catch((error: unknown) => {
      this.currentUser = null;
      if (this.isAuthenticationError(error)) this.signOut();
      else this.status = 'unavailable';
      return null;
      })
      .finally(() => {
        this.#initialization = null;
      })
    return this.#initialization;
  }

  async signIn(email:string, password: string): Promise<CurrentUser | null> {
    if (!browser) return null;

    const tokens = await requestSignIn(email, password);
    saveSession(tokens);
    return this.initialize();
  }

  signOut(): void {
    clearSession();
    this.currentUser = null;
    this.status = 'signed-out'
  }

  async refreshSession(): Promise<string | null> {
    if (!browser) return null;

    const refreshToken = getRefreshToken();
    if (!refreshToken) { this.signOut(); return null; }

    const { access } = await refreshAccessToken(refreshToken);
    saveSession({ access, refresh: refreshToken });
    return access;

  }

  updateCurrentUser(user: CurrentUser): void {
    this.currentUser = user;
    this.status = 'signed-in';
  }

  requireAccessToken(): string | null {
    if (!browser) return null;

    const accessToken = getAccessToken()
    if (accessToken) return accessToken;

    this.signOut();
    this.redirectToSignIn();
    return null;
  }

  handleAuthenticationError(error: unknown): boolean {
    if (!this.isAuthenticationError(error)) return false;

    this.signOut();
    this.redirectToSignIn();
    return true;
  }

  private redirectToSignIn(): void {
    if (!browser) return;

    const currentHref = window.location.pathname + window.location.search + window.location.hash;
    const signInHref = resolve(localizeInternalHref('/auth/sign-in'));
    replaceInternalLocation(signInHref+"?redirect=" + encodeURIComponent(currentHref))
  }

  private isAuthenticationError(error: unknown): boolean {
    return error instanceof ApiRequestError && (error.status === 401 || error.status === 403)
  }
}

export const authState = new AuthState();
