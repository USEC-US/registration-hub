import type { CurrentUser } from '$lib/api/types'
import { getAccessToken, getRefreshToken, saveSession, clearSession } from '$lib/auth/session'
import { getCurrentUser, refreshAccessToken, signIn as requestSignIn } from '$lib/api/auth'
import { browser } from '$app/environment'
import { localizeInternalHref } from '$lib/navigation'
import { resolve } from '$app/paths'
import { replaceInternalLocation } from '$lib/auth/navigation'
import { ApiRequestError } from '$lib/api/client'


export type AuthStatus = 'idle' | 'loading' | 'signed-in' | 'signed-out' | 'unavailable'

export type AuthSessionSnapshot = Readonly<{
  accessToken: string
  generation: number
}>

type Initialization = {
  accessToken: string
  generation: number
  operationGeneration: number
  promise: Promise<CurrentUser | null>
}

export class AuthState {
  currentUser = $state<CurrentUser | null>(null)
  status = $state<AuthStatus>('idle')
  #operationGeneration = 0
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
    const operationGeneration = this.#operationGeneration;
    if (
      this.#initialization?.accessToken === accessToken &&
      this.#initialization.generation === generation &&
      this.#initialization.operationGeneration === operationGeneration
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
    initialization = { accessToken, generation, operationGeneration, promise };
    this.#initialization = initialization;
    return promise;
  }

  async signIn(email:string, password: string): Promise<CurrentUser | null> {
    if (!browser) return null;

    const generation = this.beginTokenOperation();
    const tokens = await requestSignIn(email, password).catch((error: unknown) => {
      if (!this.isActiveTokenOperation(generation)) return null;
      void this.initialize();
      throw error;
    });
    if (!tokens || !this.isActiveTokenOperation(generation)) return null;

    saveSession(tokens);
    this.advanceSessionGeneration();
    const user = await this.initialize();
    return this.isActiveTokenOperation(generation) ? user : null;
  }

  signOut(): void {
    this.invalidateAuthWork();
    clearSession();
    this.currentUser = null;
    this.status = 'signed-out'
  }

  async refreshSession(): Promise<string | null> {
    if (!browser) return null;

    const refreshToken = getRefreshToken();
    if (!refreshToken) { this.signOut(); return null; }

    const generation = this.beginTokenOperation();
    const tokens = await refreshAccessToken(refreshToken).catch((error: unknown) => {
      if (!this.isActiveTokenOperation(generation)) return null;
      void this.initialize();
      throw error;
    });
    if (!tokens || !this.isActiveTokenOperation(generation)) return null;

    const { access } = tokens;
    saveSession({ access, refresh: refreshToken });
    this.advanceSessionGeneration();
    await this.initialize();
    return this.isActiveTokenOperation(generation) ? access : null;

  }

  updateCurrentUser(snapshot: AuthSessionSnapshot, user: CurrentUser): boolean {
    if (!this.isSessionSnapshotCurrent(snapshot)) return false;

    this.currentUser = user;
    this.status = 'signed-in';
    return true;
  }

  requireAccessToken(): string | null {
    if (!browser) return null;

    const accessToken = getAccessToken()
    if (accessToken) return accessToken;

    this.signOut();
    this.navigateToSignIn();
    return null;
  }

  requireSessionSnapshot(): AuthSessionSnapshot | null {
    const accessToken = this.requireAccessToken();
    if (!accessToken) return null;

    return { accessToken, generation: this.#sessionGeneration };
  }

  isSessionSnapshotCurrent(snapshot: AuthSessionSnapshot): boolean {
    return this.#sessionGeneration === snapshot.generation &&
      getAccessToken() === snapshot.accessToken
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
      this.#operationGeneration === initialization.operationGeneration &&
      getAccessToken() === initialization.accessToken
  }

  private beginTokenOperation(): number {
    this.#operationGeneration += 1
    return this.#operationGeneration
  }

  private isActiveTokenOperation(generation: number): boolean {
    return this.#operationGeneration === generation
  }

  private advanceSessionGeneration(): void {
    this.#sessionGeneration += 1
    this.#initialization = null
  }

  private invalidateAuthWork(): void {
    this.#operationGeneration += 1
    this.advanceSessionGeneration()
  }
}

export const authState = new AuthState();
