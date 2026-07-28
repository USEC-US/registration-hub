import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { goto } from '$app/navigation';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { ApiRequestError } from '$lib/api/client';
import { registerAccount, signIn, updateCurrentUser } from '$lib/api/auth';
import type { CurrentUser, TokenPair } from '$lib/api/types';
import { saveSession } from '$lib/auth/session';
import * as m from '$lib/paraglide/messages';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import type { AuthSessionSnapshot } from '$lib/states/auth-state.svelte';
import ProfilePage from './account/profile/+page.svelte';
import RegisterPage from './auth/register/+page.svelte';
import SignInPage from './auth/sign-in/+page.svelte';

const authStateMock = vi.hoisted(() => ({
	status: 'idle',
	currentUser: null as CurrentUser | null,
	initialize: vi.fn(),
	requireAccessToken: vi.fn(),
	requireSessionSnapshot: vi.fn(),
	isSessionSnapshotCurrent: vi.fn(),
	handleAuthenticationError: vi.fn(),
	updateCurrentUser: vi.fn(),
	signIn: vi.fn()
}));
const mockPage = vi.hoisted(() => ({
	url: new URL('https://usec.test/vi/account/profile?section=identity#school')
}));

vi.mock('$env/dynamic/public', () => ({ env: {} }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$app/state', () => ({
	page: mockPage
}));
vi.mock('$lib/api/auth', () => ({
	getCurrentUser: vi.fn(),
	registerAccount: vi.fn(),
	signIn: vi.fn(),
	updateCurrentUser: vi.fn()
}));
vi.mock('$lib/auth/session', () => ({
	saveSession: vi.fn()
}));
vi.mock('$lib/states/auth-state.svelte', () => ({ authState: authStateMock }));

const tokens: TokenPair = { access: 'access-token', refresh: 'refresh-token' };
const sessionSnapshot: AuthSessionSnapshot = {
	accessToken: tokens.access,
	generation: 0
};
const user: CurrentUser = {
	id: 7,
	email: 'player@example.com',
	first_name: 'Minh',
	last_name: 'Nguyen',
	school: 'HCMUS'
};
const newerUser: CurrentUser = {
	id: 8,
	email: 'new@example.com',
	first_name: 'Lan',
	last_name: 'Tran',
	school: 'HCMUT'
};

beforeEach(() => {
	overwriteGetLocale(() => 'en');
	mockPage.url = new URL('https://usec.test/vi/account/profile?section=identity#school');
	vi.mocked(goto).mockReset().mockResolvedValue(undefined);
	vi.mocked(registerAccount).mockReset();
	vi.mocked(signIn).mockReset();
	vi.mocked(updateCurrentUser).mockReset();
	vi.mocked(saveSession).mockReset();
	authStateMock.status = 'idle';
	authStateMock.currentUser = null;
	authStateMock.initialize.mockReset();
	authStateMock.requireAccessToken.mockReset();
	authStateMock.requireSessionSnapshot.mockReset().mockReturnValue(sessionSnapshot);
	authStateMock.isSessionSnapshotCurrent.mockReset().mockReturnValue(true);
	authStateMock.handleAuthenticationError.mockReset().mockReturnValue(false);
	authStateMock.updateCurrentUser.mockReset().mockReturnValue(true);
	authStateMock.signIn.mockReset();
});

afterEach(() => {
	overwriteGetLocale(() => 'en');
});

describe('sign-in page', () => {
	it('delegates sign-in to auth state before a locale-safe fallback navigation', async () => {
		authStateMock.signIn.mockResolvedValue(user);
		const { container } = render(SignInPage);

		const email = page.getByLabelText('Email');
		const password = page.getByLabelText('Password');
		await expect.element(email).toHaveAttribute('autocomplete', 'username');
		await expect.element(password).toHaveAttribute('autocomplete', 'current-password');
		await email.fill('player@example.com');
		await password.fill('strong-password');
		await page.getByRole('button', { name: 'Sign in' }).click();

		await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/en/account/registrations'));
		expect(authStateMock.signIn).toHaveBeenCalledWith('player@example.com', 'strong-password');
		expect(saveSession).not.toHaveBeenCalled();
		expect(container.querySelector('form')).toHaveAttribute('aria-busy', 'false');
	});

	it('restores the localized redirect pathname, query, and hash after sign-in', async () => {
		mockPage.url = new URL(
			'https://usec.test/auth/sign-in?redirect=%2Fvi%2Faccount%2Fregistrations%3Fstatus%3Dpending%23payment'
		);
		authStateMock.signIn.mockResolvedValue(user);
		render(SignInPage);

		await page.getByLabelText('Email').fill('player@example.com');
		await page.getByLabelText('Password').fill('strong-password');
		await page.getByRole('button', { name: 'Sign in' }).click();

		await vi.waitFor(() =>
			expect(goto).toHaveBeenCalledWith('/vi/account/registrations?status=pending#payment')
		);
	});

	it('ignores a legacy redirect parameter and uses the safe fallback', async () => {
		const legacyRedirectParameter = ['redirect', 'To'].join('');
		mockPage.url = new URL(
			`https://usec.test/auth/sign-in?${legacyRedirectParameter}=%2Fvi%2Faccount%2Fregistrations`
		);
		authStateMock.signIn.mockResolvedValue(user);
		render(SignInPage);

		await page.getByLabelText('Email').fill('player@example.com');
		await page.getByLabelText('Password').fill('strong-password');
		await page.getByRole('button', { name: 'Sign in' }).click();

		await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/en/account/registrations'));
	});

	it('blocks duplicate submissions while authentication is pending', async () => {
		let resolveSignIn!: (value: CurrentUser | null) => void;
		authStateMock.signIn.mockReturnValue(
			new Promise((resolve) => {
				resolveSignIn = resolve;
			})
		);
		const { container } = render(SignInPage);
		await page.getByLabelText('Email').fill('player@example.com');
		await page.getByLabelText('Password').fill('strong-password');
		const button = page.getByRole('button', { name: 'Sign in' }).elements()[0] as HTMLButtonElement;

		button.click();
		button.click();

		await vi.waitFor(() => expect(authStateMock.signIn).toHaveBeenCalledOnce());
		expect(button).toBeDisabled();
		expect(button).toHaveAttribute('data-slot', 'button');
		expect(button.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
		expect(container.querySelector('form')).toHaveAttribute('aria-busy', 'true');
		resolveSignIn(user);
		await vi.waitFor(() => expect(goto).toHaveBeenCalledOnce());
	});

	it('renders API field and form errors', async () => {
		authStateMock.signIn.mockRejectedValue(
			new ApiRequestError(400, 'Unable to sign in.', { email: ['Enter a valid email address.'] }, [
				'The email or password is incorrect.'
			])
		);
		render(SignInPage);
		await page.getByLabelText('Email').fill('invalid@example.com');
		await page.getByLabelText('Password').fill('wrong-password');
		await page.getByRole('button', { name: 'Sign in' }).click();

		await expect.element(page.getByText('Enter a valid email address.')).toBeInTheDocument();
		await expect.element(page.getByText('The email or password is incorrect.')).toBeInTheDocument();
	});

	it('stays on the form when sign-in cannot hydrate the current user', async () => {
		authStateMock.signIn.mockResolvedValue(null);
		render(SignInPage);

		await page.getByLabelText('Email').fill('player@example.com');
		await page.getByLabelText('Password').fill('strong-password');
		await page.getByRole('button', { name: 'Sign in' }).click();

		await expect.element(page.getByText(m.auth_sign_in_failed())).toBeVisible();
		expect(goto).not.toHaveBeenCalled();
	});
});

describe('account creation page', () => {
	it('uses normalized registration email for automatic sign-in and redirects in locale', async () => {
		overwriteGetLocale(() => 'vi');
		vi.mocked(registerAccount).mockResolvedValue({ ...user, email: 'player@example.com' });
		vi.mocked(signIn).mockResolvedValue(tokens);
		const { container } = render(RegisterPage);
		expect(container.querySelector('[data-slot="card"]')).not.toBeNull();
		expect(container.querySelector('button[type="submit"]')).toHaveAttribute('data-slot', 'button');

		await expect
			.element(page.getByLabelText('Mật khẩu'))
			.toHaveAttribute('autocomplete', 'new-password');
		expect(container.querySelector('input[name="password"]')).toHaveAttribute('minlength', '8');
		expect(container.querySelector('input[name="first_name"]')).toHaveAttribute('maxlength', '150');
		expect(container.querySelector('input[name="last_name"]')).toHaveAttribute('maxlength', '150');
		expect(container.querySelector('input[name="school"]')).toHaveAttribute('maxlength', '128');
		await page.getByLabelText('Email').fill('PLAYER@EXAMPLE.COM');
		await page.getByLabelText('Mật khẩu').fill('strong-password');
		await page.getByLabelText('Họ').fill('Minh');
		await page.getByLabelText('Tên').fill('Nguyen');
		await page.getByLabelText('Trường').fill('HCMUS');
		await page.getByRole('button', { name: 'Tạo tài khoản' }).click();

		await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/account/profile'));
		expect(registerAccount).toHaveBeenCalledWith({
			email: 'PLAYER@EXAMPLE.COM',
			password: 'strong-password',
			first_name: 'Minh',
			last_name: 'Nguyen',
			school: 'HCMUS'
		});
		expect(signIn).toHaveBeenCalledWith('player@example.com', 'strong-password');
		expect(saveSession).toHaveBeenCalledWith(tokens);
	});

	it('submits a blank optional school with required account names', async () => {
		vi.mocked(registerAccount).mockResolvedValue({ ...user, school: '' });
		vi.mocked(signIn).mockResolvedValue(tokens);
		const { container } = render(RegisterPage);

		const firstName = container.querySelector('input[name="first_name"]');
		const lastName = container.querySelector('input[name="last_name"]');
		const school = container.querySelector('input[name="school"]');
		expect(firstName).toBeRequired();
		expect(lastName).toBeRequired();
		expect(school).not.toBeRequired();
		await page.getByLabelText('Email').fill(user.email);
		await page.getByLabelText('Password').fill('strong-password');
		await page.getByLabelText('First name').fill(user.first_name);
		await page.getByLabelText('Last name').fill(user.last_name);
		await page.getByRole('button', { name: 'Create account' }).click();

		await vi.waitFor(() => {
			expect(registerAccount).toHaveBeenCalledWith({
				email: user.email,
				password: 'strong-password',
				first_name: user.first_name,
				last_name: user.last_name,
				school: ''
			});
		});
	});

	it('renders registration field and form errors together', async () => {
		vi.mocked(registerAccount).mockRejectedValue(
			new ApiRequestError(400, 'Unable to create account.', { email: ['Email is unavailable.'] }, [
				'Check the registration details and try again.'
			])
		);
		render(RegisterPage);
		await page.getByLabelText('Email').fill(user.email);
		await page.getByLabelText('Password').fill('strong-password');
		await page.getByLabelText('First name').fill(user.first_name);
		await page.getByLabelText('Last name').fill(user.last_name);
		await page.getByLabelText('School').fill(user.school);
		await page.getByRole('button', { name: 'Create account' }).click();

		await expect.element(page.getByText('Email is unavailable.')).toBeInTheDocument();
		await expect
			.element(page.getByText('Check the registration details and try again.'))
			.toBeInTheDocument();
	});

	it('shows a recovery state instead of another registration form when auto-sign-in fails', async () => {
		vi.mocked(registerAccount).mockResolvedValue(user);
		vi.mocked(signIn).mockRejectedValue(new ApiRequestError(401, 'Invalid credentials.'));
		render(RegisterPage);
		await page.getByLabelText('Email').fill(user.email);
		await page.getByLabelText('Password').fill('strong-password');
		await page.getByLabelText('First name').fill(user.first_name);
		await page.getByLabelText('Last name').fill(user.last_name);
		await page.getByLabelText('School').fill(user.school);
		await page.getByRole('button', { name: 'Create account' }).click();

		await expect
			.element(page.getByRole('heading', { name: 'Your account was created' }))
			.toBeInTheDocument();
		await expect.element(page.getByRole('link', { name: 'Go to sign in' })).toBeInTheDocument();
		expect(page.getByRole('button', { name: 'Create account' }).elements()).toHaveLength(0);
		expect(document.querySelector('input[name="password"]')).toBeNull();
		expect(registerAccount).toHaveBeenCalledOnce();
	});
});

describe('profile page', () => {
	it('delegates missing tokens to auth state and renders its redirecting UI', async () => {
		authStateMock.requireAccessToken.mockReturnValue(null);
		render(ProfilePage);

		await vi.waitFor(() => expect(authStateMock.requireAccessToken).toHaveBeenCalledOnce());
		await expect.element(page.getByText(m.auth_redirecting_to_sign_in())).toBeVisible();
	});

	it('shows email as immutable metadata and saves only editable account identity', async () => {
		authStateMock.requireAccessToken.mockReturnValue(tokens.access);
		authStateMock.initialize.mockResolvedValue(user);
		authStateMock.currentUser = user;
		vi.mocked(updateCurrentUser).mockResolvedValue({
			...user,
			school: 'HCMUS - VNU'
		});
		const { container } = render(ProfilePage);
		await vi.waitFor(() => expect(authStateMock.initialize).toHaveBeenCalledOnce());
		authStateMock.updateCurrentUser.mockClear();

		await expect.element(page.getByText(user.email)).toBeInTheDocument();
		expect(container.querySelector('[data-slot="card"]')).not.toBeNull();
		expect(container.querySelector('button[type="submit"]')).toHaveAttribute('data-slot', 'button');
		expect(container.querySelector('input[name="email"]')).toBeNull();
		await page.getByLabelText('First name').fill(' Minh ');
		await page.getByLabelText('Last name').fill(' Nguyen ');
		await page.getByLabelText('School').fill('HCMUS - VNU');
		await page.getByRole('button', { name: 'Save profile' }).click();

		await vi.waitFor(() => {
			expect(updateCurrentUser).toHaveBeenCalledWith(tokens.access, {
				first_name: ' Minh ',
				last_name: ' Nguyen ',
				school: 'HCMUS - VNU'
			});
		});
		expect(authStateMock.requireSessionSnapshot).toHaveBeenCalledOnce();
		expect(authStateMock.updateCurrentUser).toHaveBeenCalledWith(sessionSnapshot, {
			...user,
			school: 'HCMUS - VNU'
		});
		await expect.element(page.getByLabelText('First name')).toHaveValue(user.first_name);
		await expect.element(page.getByLabelText('Last name')).toHaveValue(user.last_name);
		await expect.element(page.getByText('Profile saved.')).toBeInTheDocument();
	});

	it('rejects a late profile response after the shared session changes', async () => {
		authStateMock.requireAccessToken.mockReturnValue(tokens.access);
		authStateMock.initialize.mockResolvedValue(user);
		authStateMock.currentUser = user;
		let resolveUpdate!: (value: CurrentUser) => void;
		vi.mocked(updateCurrentUser).mockReturnValue(
			new Promise<CurrentUser>((resolve) => {
				resolveUpdate = resolve;
			})
		);
		render(ProfilePage);
		await vi.waitFor(() => expect(authStateMock.initialize).toHaveBeenCalledOnce());

		await page.getByRole('button', { name: 'Save profile' }).click();
		await vi.waitFor(() => expect(updateCurrentUser).toHaveBeenCalledOnce());
		authStateMock.currentUser = newerUser;
		authStateMock.updateCurrentUser.mockReturnValue(false);
		resolveUpdate({ ...user, first_name: 'Stale' });

		await vi.waitFor(() =>
			expect(authStateMock.updateCurrentUser).toHaveBeenCalledWith(sessionSnapshot, {
				...user,
				first_name: 'Stale'
			})
		);
		expect(authStateMock.currentUser).toEqual(newerUser);
		await expect.element(page.getByLabelText('First name')).toHaveValue(user.first_name);
		expect(document.body.textContent).not.toContain('Profile saved.');
	});

	it('ignores a stale authentication error from a deferred profile save', async () => {
		authStateMock.requireAccessToken.mockReturnValue(tokens.access);
		authStateMock.initialize.mockResolvedValue(user);
		authStateMock.currentUser = user;
		let rejectUpdate!: (reason: unknown) => void;
		vi.mocked(updateCurrentUser).mockReturnValue(
			new Promise<CurrentUser>((_, reject) => {
				rejectUpdate = reject;
			})
		);
		authStateMock.handleAuthenticationError.mockReturnValue(true);
		render(ProfilePage);
		await vi.waitFor(() => expect(authStateMock.initialize).toHaveBeenCalledOnce());

		await page.getByRole('button', { name: 'Save profile' }).click();
		await vi.waitFor(() => expect(updateCurrentUser).toHaveBeenCalledOnce());
		authStateMock.currentUser = newerUser;
		authStateMock.isSessionSnapshotCurrent.mockReturnValue(false);
		rejectUpdate(new ApiRequestError(403, 'Forbidden.'));
		await vi.waitFor(() =>
			expect(
				authStateMock.handleAuthenticationError.mock.calls.length +
					authStateMock.isSessionSnapshotCurrent.mock.calls.length
			).toBeGreaterThan(0)
		);

		expect(authStateMock.handleAuthenticationError).not.toHaveBeenCalled();
		expect(document.body.textContent).not.toContain(m.auth_redirecting_to_sign_in());
		expect(authStateMock.currentUser).toEqual(newerUser);
	});

	it('ignores stale ordinary errors from a deferred profile save', async () => {
		authStateMock.requireAccessToken.mockReturnValue(tokens.access);
		authStateMock.initialize.mockResolvedValue(user);
		authStateMock.currentUser = user;
		let rejectUpdate!: (reason: unknown) => void;
		vi.mocked(updateCurrentUser).mockReturnValue(
			new Promise<CurrentUser>((_, reject) => {
				rejectUpdate = reject;
			})
		);
		render(ProfilePage);
		await vi.waitFor(() => expect(authStateMock.initialize).toHaveBeenCalledOnce());

		await page.getByRole('button', { name: 'Save profile' }).click();
		await vi.waitFor(() => expect(updateCurrentUser).toHaveBeenCalledOnce());
		authStateMock.currentUser = null;
		authStateMock.isSessionSnapshotCurrent.mockReturnValue(false);
		rejectUpdate(
			new ApiRequestError(400, 'Stale profile error.', {
				school: ['This school error belongs to the old session.']
			})
		);
		await vi.waitFor(() =>
			expect(
				authStateMock.handleAuthenticationError.mock.calls.length +
					authStateMock.isSessionSnapshotCurrent.mock.calls.length
			).toBeGreaterThan(0)
		);

		expect(authStateMock.handleAuthenticationError).not.toHaveBeenCalled();
		expect(document.body.textContent).not.toContain(
			'This school error belongs to the old session.'
		);
		expect(document.body.textContent).not.toContain(m.profile_save_failed());
	});

	it('allows the optional school to be cleared', async () => {
		authStateMock.requireAccessToken.mockReturnValue(tokens.access);
		authStateMock.initialize.mockResolvedValue(user);
		authStateMock.currentUser = user;
		vi.mocked(updateCurrentUser).mockResolvedValue({ ...user, school: '' });
		const { container } = render(ProfilePage);

		await page.getByLabelText('School').fill('');
		expect(container.querySelector('input[name="school"]')).not.toBeRequired();
		await page.getByRole('button', { name: 'Save profile' }).click();

		await vi.waitFor(() => {
			expect(updateCurrentUser).toHaveBeenCalledWith(tokens.access, {
				first_name: user.first_name,
				last_name: user.last_name,
				school: ''
			});
		});
	});

	it('shows a localized failure when profile hydration is unavailable', async () => {
		authStateMock.requireAccessToken.mockReturnValue(tokens.access);
		authStateMock.initialize.mockResolvedValue(null);
		authStateMock.status = 'unavailable';
		render(ProfilePage);

		await expect.element(page.getByText(m.profile_load_failed())).toBeVisible();
		expect(authStateMock.handleAuthenticationError).not.toHaveBeenCalled();
	});

	it('delegates unauthorized profile saves to auth state', async () => {
		authStateMock.requireAccessToken.mockReturnValue(tokens.access);
		authStateMock.initialize.mockResolvedValue(user);
		authStateMock.currentUser = user;
		authStateMock.handleAuthenticationError.mockReturnValue(true);
		vi.mocked(updateCurrentUser).mockRejectedValue(new ApiRequestError(403, 'Forbidden.'));
		render(ProfilePage);

		await page.getByRole('button', { name: 'Save profile' }).click();
		await vi.waitFor(() => expect(authStateMock.handleAuthenticationError).toHaveBeenCalledOnce());
	});

	it('renders ordinary profile API field errors without clearing the session', async () => {
		authStateMock.requireAccessToken.mockReturnValue(tokens.access);
		authStateMock.initialize.mockResolvedValue(user);
		authStateMock.currentUser = user;
		vi.mocked(updateCurrentUser).mockRejectedValue(
			new ApiRequestError(400, 'Invalid profile.', { school: ['Use 128 characters or fewer.'] })
		);
		render(ProfilePage);

		await page.getByRole('button', { name: 'Save profile' }).click();
		await expect.element(page.getByText('Use 128 characters or fewer.')).toBeInTheDocument();
		expect(authStateMock.handleAuthenticationError).toHaveBeenCalledOnce();
	});
});
