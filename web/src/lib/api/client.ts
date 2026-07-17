import { dev } from '$app/environment';
import { env } from '$env/dynamic/public';

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
		return new ApiRequestError(
			status,
			nonFieldErrors[0] ?? 'Request failed.',
			{},
			nonFieldErrors
		);
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

	if (accessToken) requestHeaders.set('authorization', `Bearer ${accessToken}`);

	const response = await fetcher(`${baseUrl}${path}`, {
		...init,
		body: requestBody,
		headers: requestHeaders
	});

	if (response.status === 204) return undefined as T;

	const payload = await response.json().catch(() => null);
	if (!response.ok) throw normalizeErrors(response.status, payload);
	return payload as T;
}
