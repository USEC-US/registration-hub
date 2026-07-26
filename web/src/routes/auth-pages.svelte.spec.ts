import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { goto } from '$app/navigation';
import { page as appPage } from '$app/state';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { ApiRequestError } from '$lib/api/client';
import { getCurrentUser, registerAccount, signIn, updateCurrentUser } from '$lib/api/auth';
import type { CurrentUser, TokenPair } from '$lib/api/types';
import { clearSession, getAccessToken, saveSession } from '$lib/auth/session';
import { replaceInternalLocation } from '$lib/auth/navigation';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import ProfilePage from './account/profile/+page.svelte';
import RegisterPage from './auth/register/+page.svelte';
import SignInPage from './auth/sign-in/+page.svelte';

vi.mock('$env/dynamic/public', () => ({ env: {} }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$app/state', () => ({
	page: { url: new URL('https://usec.test/vi/account/profile?section=identity#school') }
}));
vi.mock('$lib/api/auth', () => ({
	getCurrentUser: vi.fn(),
	registerAccount: vi.fn(),
	signIn: vi.fn(),
	updateCurrentUser: vi.fn()
}));
vi.mock('$lib/auth/session', () => ({
	clearSession: vi.fn(),
	getAccessToken: vi.fn(),
	saveSession: vi.fn()
}));
vi.mock('$lib/auth/navigation', () => ({
	replaceInternalLocation: vi.fn()
}));

const tokens: TokenPair = { access: 'access-token', refresh: 'refresh-token' };
const user: CurrentUser = {
	id: 7,
	email: 'player@example.com',
	first_name: 'Minh',
	last_name: 'Nguyen',
	school: 'HCMUS'
};

beforeEach(() => {
	overwriteGetLocale(() => 'en');
	vi.mocked(goto).mockReset().mockResolvedValue(undefined);
	vi.mocked(getCurrentUser).mockReset();
	vi.mocked(registerAccount).mockReset();
	vi.mocked(signIn).mockReset();
	vi.mocked(updateCurrentUser).mockReset();
	vi.mocked(clearSession).mockReset();
	vi.mocked(getAccessToken).mockReset();
	vi.mocked(saveSession).mockReset();
	vi.mocked(replaceInternalLocation).mockReset();
});

afterEach(() => {
	overwriteGetLocale(() => 'en');
});

describe('sign-in page', () => {
	it('uses login semantics and saves tokens before a locale-safe fallback navigation', async () => {
		const events: string[] = [];
		vi.mocked(signIn).mockImplementation(async () => {
			events.push('sign-in');
			return tokens;
		});
		vi.mocked(saveSession).mockImplementation(() => events.push('save'));
		vi.mocked(goto).mockImplementation(async () => {
			events.push('goto');
		});
		const { container } = render(SignInPage);

		const email = page.getByLabelText('Email');
		const password = page.getByLabelText('Password');
		await expect.element(email).toHaveAttribute('autocomplete', 'username');
		await expect.element(password).toHaveAttribute('autocomplete', 'current-password');
		await email.fill('player@example.com');
		await password.fill('strong-password');
		await page.getByRole('button', { name: 'Sign in' }).click();

		await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/account/registrations'));
		expect(signIn).toHaveBeenCalledWith('player@example.com', 'strong-password');
		expect(saveSession).toHaveBeenCalledWith(tokens);
		expect(events).toEqual(['sign-in', 'save', 'goto']);
		expect(container.querySelector('form')).toHaveAttribute('aria-busy', 'false');
	});

	it('blocks duplicate submissions while authentication is pending', async () => {
		let resolveSignIn!: (value: TokenPair) => void;
		vi.mocked(signIn).mockReturnValue(
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

		await vi.waitFor(() => expect(signIn).toHaveBeenCalledOnce());
		expect(button).toBeDisabled();
		expect(container.querySelector('form')).toHaveAttribute('aria-busy', 'true');
		resolveSignIn(tokens);
		await vi.waitFor(() => expect(saveSession).toHaveBeenCalledWith(tokens));
	});

	it('renders API field and form errors', async () => {
		vi.mocked(signIn).mockRejectedValue(
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
});

describe('account creation page', () => {
	it('uses normalized registration email for automatic sign-in and redirects in locale', async () => {
		overwriteGetLocale(() => 'vi');
		vi.mocked(registerAccount).mockResolvedValue({ ...user, email: 'player@example.com' });
		vi.mocked(signIn).mockResolvedValue(tokens);
		const { container } = render(RegisterPage);

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

		await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/vi/account/profile'));
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
	it('redirects without a token using the encoded current localized path', async () => {
		vi.mocked(getAccessToken).mockReturnValue(null);
		render(ProfilePage);

		await vi.waitFor(() => {
			expect(replaceInternalLocation).toHaveBeenCalledWith(
				'/auth/sign-in?redirectTo=%2Fvi%2Faccount%2Fprofile%3Fsection%3Didentity%23school'
			);
		});
		expect(appPage.url.pathname).toBe('/vi/account/profile');
		expect(getCurrentUser).not.toHaveBeenCalled();
	});

	it('shows email as immutable metadata and saves only editable account identity', async () => {
		vi.mocked(getAccessToken).mockReturnValue(tokens.access);
		vi.mocked(getCurrentUser).mockResolvedValue(user);
		vi.mocked(updateCurrentUser).mockResolvedValue({
			...user,
			school: 'HCMUS - VNU'
		});
		const { container } = render(ProfilePage);

		await expect.element(page.getByText(user.email)).toBeInTheDocument();
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
		await expect.element(page.getByLabelText('First name')).toHaveValue(user.first_name);
		await expect.element(page.getByLabelText('Last name')).toHaveValue(user.last_name);
		await expect.element(page.getByText('Profile saved.')).toBeInTheDocument();
	});

	it('allows the optional school to be cleared', async () => {
		vi.mocked(getAccessToken).mockReturnValue(tokens.access);
		vi.mocked(getCurrentUser).mockResolvedValue(user);
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

	it.each([401, 403])(
		'clears both tokens and redirects when profile loading returns %s',
		async (status) => {
			vi.mocked(getAccessToken).mockReturnValue(tokens.access);
			vi.mocked(getCurrentUser).mockRejectedValue(
				new ApiRequestError(status, 'Authentication failed.')
			);
			render(ProfilePage);

			await vi.waitFor(() => expect(clearSession).toHaveBeenCalledOnce());
			expect(replaceInternalLocation).toHaveBeenCalledWith(
				'/auth/sign-in?redirectTo=%2Fvi%2Faccount%2Fprofile%3Fsection%3Didentity%23school'
			);
		}
	);

	it('clears both tokens and redirects when profile saving returns unauthorized', async () => {
		vi.mocked(getAccessToken).mockReturnValue(tokens.access);
		vi.mocked(getCurrentUser).mockResolvedValue(user);
		vi.mocked(updateCurrentUser).mockRejectedValue(new ApiRequestError(403, 'Forbidden.'));
		render(ProfilePage);

		await page.getByRole('button', { name: 'Save profile' }).click();
		await vi.waitFor(() => expect(clearSession).toHaveBeenCalledOnce());
		expect(replaceInternalLocation).toHaveBeenCalledWith(
			'/auth/sign-in?redirectTo=%2Fvi%2Faccount%2Fprofile%3Fsection%3Didentity%23school'
		);
	});

	it('renders ordinary profile API field errors without clearing the session', async () => {
		vi.mocked(getAccessToken).mockReturnValue(tokens.access);
		vi.mocked(getCurrentUser).mockResolvedValue(user);
		vi.mocked(updateCurrentUser).mockRejectedValue(
			new ApiRequestError(400, 'Invalid profile.', { school: ['Use 128 characters or fewer.'] })
		);
		render(ProfilePage);

		await page.getByRole('button', { name: 'Save profile' }).click();
		await expect.element(page.getByText('Use 128 characters or fewer.')).toBeInTheDocument();
		expect(clearSession).not.toHaveBeenCalled();
		expect(replaceInternalLocation).not.toHaveBeenCalled();
	});
});
