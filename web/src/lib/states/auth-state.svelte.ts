import type { CurrentUser } from '$lib/api/types'
import { getAccessToken, getRefreshToken, saveSession, clearSession } from '$lib/auth/session'
import { getCurrentUser, refreshAccessToken, signIn as requestSignIn } from '$lib/api/auth'
import { browser } from '$app/environment'
import { localizeInternalHref } from '$lib/navigation'
import { resolve } from '$app/paths'
import { replaceInternalLocation } from '$lib/auth/navigation'
import { ApiRequestError } from '$lib/api/client'


export type AuthStatus = 'idle' | 'loading' | 'signed-in' | 'signed-out' | 'unavailable'

type Initialization = {
  accessToken: string
  generation: number
  promise: Promise<CurrentUser | null>
}

export class AuthState {
  currentUser = $state<CurrentUser | null>(null)
  status = $state<AuthStatus>('idle')
  #sessionGeneration = 0
  #initialization: Initialization | null = null

  async initialize(): Promise<CurrentUser | null> {
    if (!browser) return null;

    const accessToken = getAccessToken();
    if (!accessToken) {
      this.signOut();
      return null;
    }

    const generation = this.#sessionGeneration;
    if (
      this.#initialization?.accessToken === accessToken &&
      this.#initialization.generation === generation
    ) return this.#initialization.promise;

    this.status = 'loading';
    let initialization: Initialization;
    const promise = getCurrentUser(accessToken).then((user) => {
      if (!this.isActiveInitialization(initialization)) return null;

      this.currentUser = user;
      this.status = 'signed-in';
      return user;
    })
      .catch((error: unknown) => {
        if (this.isActiveInitialization(initialization)) {
          this.currentUser = null;
          if (this.isAuthenticationError(error)) this.signOut();
          else this.status = 'unavailable';
        }
        return null;
      })
      .finally(() => {
        if (this.#initialization === initialization) this.#initialization = null;
      })
    initialization = { accessToken, generation, promise };
    this.#initialization = initialization;
    return promise;
  }

  async signIn(email:string, password: string): Promise<CurrentUser | null> {
    if (!browser) return null;

    const tokens = await requestSignIn(email, password);
    saveSession(tokens);
    this.invalidateInitialization();
    return this.initialize();
  }

  signOut(): void {
    this.invalidateInitialization();
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
    this.invalidateInitialization();
    await this.initialize();
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
    this.navigateToSignIn();
    return null;
  }

  handleAuthenticationError(error: unknown): boolean {
    if (!this.isAuthenticationError(error)) return false;

    this.signOut();
    this.navigateToSignIn();
    return true;
  }

  private navigateToSignIn(): void {
    if (!browser) return;

    const currentHref = window.location.pathname + window.location.search + window.location.hash;
    const signInHref = resolve(localizeInternalHref('/auth/sign-in'));
    replaceInternalLocation(signInHref+"?redirect=" + encodeURIComponent(currentHref))
  }

  private isAuthenticationError(error: unknown): boolean {
    return error instanceof ApiRequestError && (error.status === 401 || error.status === 403)
  }

  private isActiveInitialization(initialization: Initialization): boolean {
    return this.#initialization === initialization &&
      this.#sessionGeneration === initialization.generation &&
      getAccessToken() === initialization.accessToken
  }

  private invalidateInitialization(): void {
    this.#sessionGeneration += 1
    this.#initialization = null
  }
}

export const authState = new AuthState();
