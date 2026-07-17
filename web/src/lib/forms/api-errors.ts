import { ApiRequestError } from '$lib/api/client';

export interface FormErrorState {
	fieldErrors: Record<string, string[]>;
	formErrors: string[];
}

export function formErrorsFrom(cause: unknown, fallback: string): FormErrorState {
	if (!(cause instanceof ApiRequestError)) {
		return { fieldErrors: {}, formErrors: [fallback] };
	}

	const formErrors = [...cause.nonFieldErrors];
	if (cause.detail && !formErrors.includes(cause.detail)) formErrors.push(cause.detail);
	if (formErrors.length === 0 && Object.keys(cause.fieldErrors).length === 0) {
		formErrors.push(cause.message || fallback);
	}

	return { fieldErrors: cause.fieldErrors, formErrors };
}
