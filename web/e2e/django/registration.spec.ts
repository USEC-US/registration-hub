import { readFileSync } from 'node:fs';
import { expect, test, type Page, type APIRequestContext } from '@playwright/test';

const api = 'http://127.0.0.1:8015';
const password = 'Journey-test-password-2026';
const institution = 'Journey Test University';
const proof = {
	name: 'proof.png',
	mimeType: 'image/png',
	buffer: Buffer.from(
		'iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAE0lEQVR4nGP8//8/AwwwwVl4OQCWbgMF7ZjH1AAAAABJRU5ErkJggg==',
		'base64'
	)
};

interface Receipt {
	payment_reference: string;
	id: number;
	status: string;
	members: {
		gamer_tag_snapshot: string;
		school_snapshot: string;
		is_captain: boolean;
		roster_role: string;
		display_order: number;
	}[];
	payment_attempts: { id: number; status: string }[];
}

async function registrationUrl(request: APIRequestContext, slug: string) {
	const response = await request.get(`${api}/api/tournaments/registration-journey-test/`);
	expect(response.ok()).toBeTruthy();
	const tournament = await response.json();
	const division = tournament.tournament_games.find(
		(game: { game_slug: string }) => game.game_slug === slug
	);
	return `/en/tournaments/registration-journey-test/games/${division.id}/register`;
}

async function fillRoster(page: Page, tags: string[]) {
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	if (tags.length === 3)
		await page.getByRole('button', { name: 'Add substitute', exact: true }).click();
	for (const [index, tag] of tags.entries()) {
		const row = page.locator('[data-roster-row]').nth(index);
		await row.getByLabel('First and Middle name', { exact: true }).fill(`Player ${index + 1}`);
		await row.getByLabel('Last name', { exact: true }).fill('Example');
		await row.getByLabel('Date of birth', { exact: true }).fill('01/01/2005');
		await expect(row.getByLabel('Student ID', { exact: true })).toHaveJSProperty('required', true);
		await row.getByLabel('Student ID', { exact: true }).fill(`000${index + 1}`);
		await row.getByLabel('Gamer tag', { exact: true }).fill(tag);
		await row.getByRole('combobox', { name: 'Institution' }).fill('Journey Test');
		await page.getByRole('option').filter({ hasText: institution }).click();
	}
}

async function fillContacts(page: Page) {
	await page.getByLabel('Facebook', { exact: true }).fill('https://facebook.com/journey-captain');
	await page.getByLabel('Phone', { exact: true }).fill('+84901234567');
}

async function submit(page: Page, expectedStatus = 201): Promise<Receipt> {
	if (await page.getByRole('button', { name: 'Continue', exact: true }).count())
		await page.getByRole('button', { name: 'Continue', exact: true }).click();
	const responsePromise = page.waitForResponse(
		(response) =>
			response.url() === `${api}/api/registrations/submit/` &&
			response.request().method() === 'POST'
	);
	await page.getByRole('button', { name: 'Submit registration', exact: true }).click();
	const response = await responsePromise;
	expect(response.status(), await response.text()).toBe(expectedStatus);
	return response.json();
}

async function organizerLogin(page: Page) {
	await page.goto(`${api}/admin/`);
	await page.locator('#id_username').fill('journey-organizer@example.test');
	await page.locator('#id_password').fill(password);
	await page.locator('button[type=submit], input[type=submit]').click();
	await expect(page).toHaveURL(`${api}/admin/`);
}

async function adminAction(page: Page, model: string, id: number, action: string) {
	await page.goto(`${api}/admin/registrations/${model}/`);
	await page.locator(`input[name="_selected_action"][value="${id}"]`).check();
	await page.locator('select[name="action"]').first().selectOption(action);
	await page.locator('button[name="index"]').first().click();
	await expect(
		page.getByText(
			model === 'paymentattempt'
				? 'Reviewed 1 payment attempt(s).'
				: 'Applied transition to 1 registration(s).',
			{ exact: true }
		)
	).toBeVisible();
}

function adminField(page: Page, label: string) {
	return page
		.locator('.field-line')
		.filter({
			has: page.locator('label').filter({ hasText: new RegExp(`^\\s*${label}:?\\s*$`) })
		})
		.locator('.readonly');
}

test('credential forms use POST and stay disabled before hydration', async ({ browser }) => {
	const context = await browser.newContext({ javaScriptEnabled: false });
	try {
		const page = await context.newPage();
		for (const route of ['sign-in', 'register']) {
			await page.goto(`http://127.0.0.1:4175/en/auth/${route}`);
			const form = page.locator('main form');
			await expect(form).toHaveAttribute('method', /^post$/i);
			await expect(form.locator('button[type="submit"]')).toBeDisabled();
		}
	} finally {
		await context.close();
	}
});

test('guest captain submits a team with catalogue snapshots and private contacts', async ({
	page,
	request
}) => {
	await page.goto(await registrationUrl(request, 'team-free'));
	await page.getByLabel('Team name', { exact: true }).fill('Guest Captains');
	await page.getByLabel('Team tag', { exact: true }).fill('gcap');
	await fillContacts(page);
	await fillRoster(page, ['Captain#ONE', 'Teammate#ONE']);
	const receipt = await submit(page);
	expect(receipt).toHaveProperty('team_tag', 'GCAP');
	expect(receipt.members.map((member) => member.is_captain)).toEqual([true, false]);
	expect(receipt.members.map((member) => member.school_snapshot)).toEqual([
		institution,
		institution
	]);
	expect(receipt).not.toHaveProperty('contact_phone_snapshot');
	await expect(
		page.getByRole('heading', { name: 'Registration submitted', exact: true })
	).toBeVisible();
	await expect(
		page.getByText(`Registration reference: ${receipt.id}`, { exact: true })
	).toBeVisible();
	const detail = await request.get(`${api}/api/registrations/${receipt.id}/`);
	expect([401, 403]).toContain(detail.status());
});

test('guest manager registers main players and a substitute representative', async ({
	page,
	request
}) => {
	await page.goto(await registrationUrl(request, 'team-free'));
	await page.getByRole('radio', { name: 'Manager', exact: true }).click();
	await page.getByLabel('Manager name', { exact: true }).fill('Journey Manager');
	await page.getByLabel('Team name', { exact: true }).fill('Managed Team');
	await page.getByLabel('Team tag', { exact: true }).fill('MGT');
	await fillContacts(page);
	await fillRoster(page, ['Managed#ONE', 'Managed#TWO', 'Managed#THREE']);
	await page.getByRole('radio', { name: 'Set member 3 as captain', exact: true }).click();
	const receipt = await submit(page);
	expect(receipt.members).toHaveLength(3);
	expect(receipt.members.map((member) => member.roster_role)).toEqual([
		'substitute',
		'main',
		'main'
	]);
	expect(receipt.members[0]).toMatchObject({
		gamer_tag_snapshot: 'Managed#THREE',
		display_order: 1
	});
	expect(receipt.members.map((member) => member.is_captain)).toEqual([true, false, false]);
	await organizerLogin(page);
	await page.goto(`${api}/admin/registrations/registration/${receipt.id}/change/`);
	await expect(adminField(page, 'Manager name snapshot')).toHaveText('Journey Manager');
	await expect(page.locator('td.field-first_name_snapshot').first()).toHaveText('Player 3');
	await expect(page.locator('td.field-last_name_snapshot').first()).toHaveText('Example');
	await expect(page.locator('td.field-student_id_snapshot').first()).toHaveText('0003');
	await expect(page.locator('td.field-date_of_birth_snapshot').first()).toContainText('2005');
	await expect(adminField(page, 'Contact phone snapshot')).toHaveText('+84901234567');
});

test('guest solo uses one captain slot and no team name', async ({ page, request }) => {
	await page.goto(await registrationUrl(request, 'solo-free'));
	await expect(page.getByLabel('Team name', { exact: true })).toHaveCount(0);

	await fillContacts(page);
	await fillRoster(page, ['Solo#ONE']);
	await page.getByRole('button', { name: 'Open date picker' }).click();
	await page.getByRole('combobox', { name: 'Choose year' }).selectOption('2004');
	await page.getByRole('combobox', { name: 'Choose month' }).selectOption('2');
	await page.locator('[data-calendar-day][data-value="2004-02-29"]').click();
	await expect(page.getByLabel('Date of birth', { exact: true })).toHaveValue('02/29/2004');
	const submission = page.waitForRequest(
		(request) => request.url() === `${api}/api/registrations/submit/` && request.method() === 'POST'
	);
	const receipt = await submit(page);
	expect((await submission).postDataJSON().members[0].date_of_birth_snapshot).toBe('2004-02-29');
	expect(receipt.members).toHaveLength(1);
	expect(receipt.members[0].is_captain).toBe(true);
});

async function uploadProof(page: Page, id: number) {
	await page.locator('input[type=file]').setInputFiles(proof);
	const response = page.waitForResponse(
		(r) =>
			r.url() === `${api}/api/registrations/${id}/payment-proof/` && r.request().method() === 'POST'
	);
	await page.getByRole('button', { name: 'Upload payment proof', exact: true }).click();
	const result = await response;
	expect(result.status(), await result.text()).toBe(200);
	return result.json();
}

test('paid guest returns in a new tab, replaces rejected proof, and receives separate verification and approval', async ({
	page,
	request,
	context,
	browser
}) => {
	const path = await registrationUrl(request, 'solo-paid');
	await page.goto(path);
	await fillContacts(page);
	await fillRoster(page, ['PaidGuest#ONE']);
	const receipt = await submit(page);
	expect(receipt.payment_attempts).toHaveLength(0);
	await expect(page).toHaveURL(`/en/registrations/${receipt.id}/payment`);
	await expect(page.getByAltText('VietQR payment code')).toBeVisible();
	const returned = await context.newPage();
	await returned.goto(path);
	await returned
		.getByRole('link', { name: `View registration ${receipt.id} / payment`, exact: true })
		.click();
	await expect(returned.getByAltText('VietQR payment code')).toBeVisible();
	const pending = await uploadProof(returned, receipt.id);
	expect(pending.payment_state).toBe('PENDING');
	await expect(
		returned.getByText(
			'Payment proof is pending verification. Your reservation is protected during review.'
		)
	).toBeVisible();
	await expect(returned.getByAltText('VietQR payment code')).toHaveCount(0);
	const staffContext = await browser.newContext();
	try {
		const staff = await staffContext.newPage();
		await organizerLogin(staff);
		const attempt = pending.registration.payment_attempts[0].id;
		await staff.goto(`${api}/admin/registrations/registration/${receipt.id}/change/`);
		const proofLink = staff.locator('a[href*="/media/payment-proofs/"]').first();
		const proofUrl = new URL((await proofLink.getAttribute('href'))!, api).href;
		expect([401, 403]).toContain((await request.get(proofUrl)).status());
		const privateProof = await staff.request.get(proofUrl);
		expect(privateProof.status()).toBe(200);
		expect(privateProof.headers()['cache-control']).toBe('private, no-store');
		await staff.goto(`${api}/admin/registrations/paymentattempt/`);
		await staff.locator(`input[name="_selected_action"][value="${attempt}"]`).check();
		await staff.locator('select[name="action"]').first().selectOption('reject_selected');
		await staff.locator('button[name="index"]').first().click();
		await staff.getByLabel('Reason').fill('Test-only: upload a clearer image.');
		await staff.getByRole('button', { name: 'Reject proof', exact: true }).click();
		await returned.getByRole('button', { name: 'Refresh status', exact: true }).click();
		await expect(
			returned.getByText('Test-only: upload a clearer image.', { exact: true })
		).toBeVisible();
		const replacement = await uploadProof(returned, receipt.id);
		const replacementAttempt = replacement.registration.payment_attempts.find(
			(p: { id: number }) => p.id !== attempt
		);
		await adminAction(staff, 'paymentattempt', replacementAttempt.id, 'verify_selected');
		await returned.getByRole('button', { name: 'Refresh status', exact: true }).click();
		await expect(
			returned.getByText('Payment verified. Eligibility approval is a separate organizer decision.')
		).toBeVisible();
		await adminAction(staff, 'registration', receipt.id, 'mark_under_review');
		await adminAction(staff, 'registration', receipt.id, 'approve_selected');
		await staff.goto(`${api}/admin/registrations/registration/${receipt.id}/change/`);
		await expect(adminField(staff, 'Status')).toHaveText('Approved');
	} finally {
		await staffContext.close();
	}
});

test('signed-in participant submits then accesses payment from the account page', async ({
	page,
	request
}) => {
	const path = await registrationUrl(request, 'solo-paid');
	await page.goto(`/en/auth/sign-in?redirect=${encodeURIComponent(path)}`);
	await page.getByLabel('Email', { exact: true }).fill('journey-player@example.test');
	await page.getByLabel('Password', { exact: true }).fill(password);
	await page.getByRole('button', { name: 'Sign in', exact: true }).click();
	await expect(page).toHaveURL(path);
	await fillContacts(page);
	await fillRoster(page, ['SignedPlayer#ONE']);
	const receipt = await submit(page);
	await expect(page).toHaveURL(`/en/registrations/${receipt.id}/payment`);
	await page.goto(`/en/account/registrations/${receipt.id}`);
	await page.getByRole('link', { name: 'Registration payment', exact: true }).click();
	const pending = await uploadProof(page, receipt.id);
	expect(pending.payment_state).toBe('PENDING');
});

test('lost real submission response recovers the same persisted registration', async ({
	page,
	request
}) => {
	await page.goto(await registrationUrl(request, 'solo-paid'));
	await fillContacts(page);
	await fillRoster(page, ['LostResponse#ONE']);
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	let persistedId = 0;
	let submissions = 0;
	await page.route(`${api}/api/registrations/submit/`, async (route) => {
		submissions++;
		const response = await route.fetch();
		expect(response.status()).toBe(201);
		persistedId = (await response.json()).id;
		await route.abort('failed');
	});
	await page.getByRole('button', { name: 'Submit registration', exact: true }).click();
	await expect(
		page.locator('form').getByRole('button', { name: 'Recover pending submission', exact: true })
	).toBeVisible();
	await page
		.locator('form')
		.getByRole('button', { name: 'Recover pending submission', exact: true })
		.click();
	await expect(page).toHaveURL(new RegExp(`/en/registrations/${persistedId}/payment$`));
	expect(submissions).toBe(1);
	const saved = await page.evaluate(() =>
		Object.entries(localStorage)
			.filter(([key]) => key.startsWith('usec-registration-access:v1:'))
			.map(([, value]) => JSON.parse(value))
	);
	expect(saved).toHaveLength(1);
	const resumed = await request.post(`${api}/api/registrations/resume/`, {
		headers: { 'X-Registration-Access': saved[0].credential }
	});
	expect((await resumed.json()).registration.id).toBe(persistedId);
});

test('expired entry remains visible and produces an editable retry with a new registration', async ({
	page
}) => {
	const fixture = JSON.parse(
		readFileSync('/tmp/hcmusec-registration-journey-fixture.json', 'utf8')
	);
	await page.goto('/en/auth/sign-in');
	await page.evaluate(
		(entry) =>
			localStorage.setItem(
				`usec-registration-access:v1:${entry.credential}`,
				JSON.stringify(entry)
			),
		fixture
	);
	await page.goto(`/en/registrations/${fixture.registrationId}/payment`);
	await expect(
		page.getByText('This registration is expired or rejected. Do not transfer money for it.')
	).toBeVisible();
	await expect(page.getByAltText('VietQR payment code')).toHaveCount(0);
	await expect(page.getByRole('button', { name: 'Upload payment proof', exact: true })).toHaveCount(
		0
	);
	await page.getByRole('button', { name: 'Create a new editable draft', exact: true }).click();
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	await expect(page.getByLabel('Phone', { exact: true })).toHaveValue('+84901234567');
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	await expect(page.getByLabel('Gamer tag', { exact: true })).toHaveValue('Expired#ONE');
	const receipt = await submit(page);
	expect(receipt.id).not.toBe(fixture.registrationId);
	await page.goto(`/en/registrations/${fixture.registrationId}/payment`);
	await expect(
		page.getByText('This registration is expired or rejected. Do not transfer money for it.')
	).toBeVisible();
});

test('duplicate player is blocked until organizer rejection permits resubmission', async ({
	page,
	request,
	browser
}) => {
	const path = await registrationUrl(request, 'solo-free');
	await page.goto(path);
	await fillContacts(page);
	await fillRoster(page, ['Resubmit#ONE']);
	const receipt = await submit(page);
	await page.goto(path);
	await fillContacts(page);
	await fillRoster(page, ['  resubmit#one  ']);
	await submit(page, 400);
	await expect(page.locator('[data-registration-confirmation]')).toHaveCount(0);
	const organizerContext = await browser.newContext();
	try {
		const organizerPage = await organizerContext.newPage();
		await organizerLogin(organizerPage);
		await adminAction(organizerPage, 'registration', receipt.id, 'mark_under_review');
		await adminAction(organizerPage, 'registration', receipt.id, 'reject_selected');
	} finally {
		await organizerContext.close();
	}
	// A server validation error may return to details or roster; choose review explicitly.
	await page.getByRole('button', { name: '3. Review registration', exact: true }).click();
	const replacement = await submit(page);
	expect(replacement.id).not.toBe(receipt.id);
	await expect(
		page.getByRole('heading', { name: 'Registration submitted', exact: true })
	).toBeVisible();
});

test('migrated payment quote requires an unpaid choice and survives a lost response until confirmed recovery', async ({
	page,
	request
}) => {
	const path = await registrationUrl(request, 'solo-paid');
	const divisionId = Number(path.split('/games/')[1].split('/')[0]);
	const quoteResponse = await request.post(`${api}/api/payment-references/`, {
		data: { tournament_game: divisionId }
	});
	expect(quoteResponse.ok()).toBeTruthy();
	const oldToken = (await quoteResponse.json()).token;
	const oldKey = `usec-payment-intent:${divisionId}`;
	await page.goto('/en/auth/sign-in');
	await page.evaluate(({ oldKey, oldToken }) => sessionStorage.setItem(oldKey, oldToken), {
		oldKey,
		oldToken
	});
	let submissions = 0;
	let persistedId = 0;
	await page.route(`${api}/api/registrations/submit/`, async (route) => {
		submissions++;
		const payload = route.request().postDataJSON();
		expect(payload).not.toHaveProperty('payment_intent_token');
		expect(payload).not.toHaveProperty('proof_file');
		const response = await route.fetch();
		expect(response.status()).toBe(201);
		persistedId = (await response.json()).id;
		await route.abort('failed');
	});
	await page.goto(path);
	await expect(page.getByText('Earlier payment instructions saved', { exact: true })).toBeVisible();
	await expect(
		page.getByText(/If you already transferred, contact the organizers with your proof/)
	).toBeVisible();
	await expect(page.getByRole('button', { name: 'Submit registration', exact: true })).toHaveCount(
		0
	);
	expect(submissions).toBe(0);
	await page
		.getByRole('button', { name: 'I haven’t paid — start a new registration', exact: true })
		.click();
	await fillContacts(page);
	await fillRoster(page, ['LegacyMigration#ONE']);
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	await page.getByRole('button', { name: 'Submit registration', exact: true }).click();
	const recovery = page
		.locator('form')
		.getByRole('button', { name: 'Recover pending submission', exact: true });
	await expect(recovery).toBeVisible();
	expect(await page.evaluate((key) => sessionStorage.getItem(key), oldKey)).toBe(oldToken);
	await recovery.click();
	await expect(page).toHaveURL(new RegExp(`/en/registrations/${persistedId}/payment$`));
	expect(submissions).toBe(1);
	expect(await page.evaluate((key) => sessionStorage.getItem(key), oldKey)).toBeNull();
	// The old server-side quote is retained, still independently addressable.
	const oldQuote = await request.post(`${api}/api/payment-references/`, {
		data: { tournament_game: divisionId, token: oldToken }
	});
	expect(oldQuote.ok()).toBeTruthy();
	expect((await oldQuote.json()).token).toBe(oldToken);
});
