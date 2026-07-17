import { env } from '$env/dynamic/public';

export interface ApiRequestOptions extends Omit<RequestInit, 'body'> {
	accessToken?: string | null;
	baseUrl?: string;
	body?: BodyInit | object | null;
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

function normalizeErrors(status: number, payload: unknown): ApiRequestError {
	if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
		const fieldErrors: Record<string, string[]> = {};
		let detail: string | undefined;
		const nonFieldErrors: string[] = [];

		for (const [key, value] of Object.entries(payload)) {
			const values = Array.isArray(value) ? value.map(String) : [String(value)];
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
		baseUrl = env.PUBLIC_API_BASE_URL || 'http://localhost:8000/api',
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
		requestHeaders.set('content-type', 'application/json');
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
