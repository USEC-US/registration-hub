import { browser, dev } from '$app/environment';
import { env } from '$env/dynamic/public';
import {
	getAccessToken,
	getRefreshToken,
	getSessionRevision,
	isSessionAccessToken,
	rotateSession
} from '$lib/auth/session';

const refreshes = new Map<string, Promise<string | null>>();

async function renewAccessToken(baseUrl: string, fetcher: typeof fetch): Promise<string | null> {
	const refresh = getRefreshToken();
	if (!refresh) return null;
	const revision = getSessionRevision();
	const key = JSON.stringify([baseUrl, revision, refresh]);
	let pending = refreshes.get(key);
	if (!pending) {
		pending = (async () => {
			const response = await fetcher(`${baseUrl}/auth/token/refresh/`, {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ refresh })
			});
			const payload = await response.json().catch(() => null);
			if (!response.ok) throw normalizeErrors(response.status, payload);
			if (
				!payload ||
				typeof payload.access !== 'string' ||
				!payload.access ||
				(payload.refresh !== undefined && typeof payload.refresh !== 'string')
			) {
				throw new ApiRequestError(502, 'Invalid token refresh response.');
			}
			return rotateSession(
				{ access: payload.access, refresh: payload.refresh ?? refresh },
				revision,
				refresh
			)
				? payload.access
				: null;
		})().finally(() => {
			refreshes.delete(key);
		});
		refreshes.set(key, pending);
	}
	return pending;
}

function getDefaultApiBaseUrl(): string {
	if (env.PUBLIC_API_BASE_URL) {
		try {
			const configuredUrl = new URL(env.PUBLIC_API_BASE_URL);
			if (configuredUrl.protocol !== 'http:' && configuredUrl.protocol !== 'https:') {
				throw new Error();
			}
			return env.PUBLIC_API_BASE_URL.replace(/\/+$/, '');
		} catch {
			throw new Error('PUBLIC_API_BASE_URL must be an absolute HTTP(S) URL.');
		}
	}
	if (dev) return 'http://localhost:8000/api';
	throw new Error('PUBLIC_API_BASE_URL is required outside development.');
}

export interface ApiRequestOptions extends Omit<RequestInit, 'body'> {
	accessToken?: string | null;
	baseUrl?: string;
	body?: FormData | object | null;
	fetcher?: typeof fetch;
}

export class ApiRequestError extends Error {
	status: number;
	fieldErrors: Record<string, string[]>;
	nonFieldErrors: string[];
	detail?: string;

	constructor(
		status: number,
		message: string,
		fieldErrors: Record<string, string[]> = {},
		nonFieldErrors: string[] = [],
		detail?: string
	) {
		super(message);
		this.name = 'ApiRequestError';
		this.status = status;
		this.fieldErrors = fieldErrors;
		this.nonFieldErrors = nonFieldErrors;
		this.detail = detail;
	}
}

function flattenErrorMessages(value: unknown, path = ''): string[] {
	if (Array.isArray(value)) {
		return value.flatMap((item, index) =>
			item !== null && typeof item === 'object'
				? flattenErrorMessages(item, path + '[' + index + ']')
				: flattenErrorMessages(item, path)
		);
	}

	if (value !== null && typeof value === 'object') {
		return Object.entries(value).flatMap(([key, nestedValue]) =>
			flattenErrorMessages(nestedValue, path ? path + '.' + key : key)
		);
	}

	const message = String(value);
	return [path ? path + ': ' + message : message];
}

function normalizeErrors(status: number, payload: unknown): ApiRequestError {
	if (Array.isArray(payload)) {
		const nonFieldErrors = flattenErrorMessages(payload);
		return new ApiRequestError(status, nonFieldErrors[0] ?? 'Request failed.', {}, nonFieldErrors);
	}

	if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
		const fieldErrors: Record<string, string[]> = {};
		let detail: string | undefined;
		const nonFieldErrors: string[] = [];

		for (const [key, value] of Object.entries(payload)) {
			const values = flattenErrorMessages(value);
			if (key === 'detail') detail = values[0];
			else if (key === 'non_field_errors') nonFieldErrors.push(...values);
			else fieldErrors[key] = values;
		}

		return new ApiRequestError(
			status,
			detail ?? nonFieldErrors[0] ?? 'Request failed.',
			fieldErrors,
			nonFieldErrors,
			detail
		);
	}

	return new ApiRequestError(status, 'Request failed.');
}

export async function requestJson<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
	const {
		accessToken,
		baseUrl = getDefaultApiBaseUrl(),
		body,
		fetcher = fetch,
		headers,
		...init
	} = options;
	const sessionRevision = browser ? getSessionRevision() : null;
	const sessionRequest = browser && !!accessToken && isSessionAccessToken(accessToken);
	if (browser && accessToken && !sessionRequest) {
		throw new ApiRequestError(409, 'Your session changed. Please try again.');
	}
	const requestToken = sessionRequest ? getAccessToken() : accessToken;
	const assertSameSession = () => {
		if (
			sessionRequest &&
			(sessionRevision !== getSessionRevision() || !isSessionAccessToken(accessToken!))
		) {
			throw new ApiRequestError(409, 'Your session changed. Please try again.');
		}
	};
	const requestHeaders = new Headers(headers);

	let requestBody: BodyInit | undefined;
	if (body instanceof FormData) {
		requestBody = body;
	} else if (body != null) {
		if (!requestHeaders.has('content-type')) {
			requestHeaders.set('content-type', 'application/json');
		}
		requestBody = JSON.stringify(body);
	}

	if (requestToken) requestHeaders.set('authorization', `Bearer ${requestToken}`);

	const send = () =>
		fetcher(`${baseUrl}${path}`, {
			...init,
			body: requestBody,
			headers: requestHeaders
		});
	let response = await send();
	assertSameSession();
	if (
		response.status === 401 &&
		sessionRequest &&
		sessionRevision === getSessionRevision() &&
		accessToken &&
		isSessionAccessToken(accessToken) &&
		!init.signal?.aborted
	) {
		const current = getAccessToken();
		const refreshed =
			current !== requestToken
				? current
				: await renewAccessToken(baseUrl, fetcher).catch((error) => {
						assertSameSession();
						throw error;
					});
		assertSameSession();
		if (
			refreshed &&
			sessionRevision === getSessionRevision() &&
			isSessionAccessToken(accessToken) &&
			!init.signal?.aborted
		) {
			requestHeaders.set('authorization', `Bearer ${refreshed}`);
			response = await send();
		}
	}
	assertSameSession();

	if (response.status === 204) return undefined as T;

	const payload = await response.json().catch(() => null);
	assertSameSession();
	if (!response.ok) throw normalizeErrors(response.status, payload);
	return payload as T;
}
