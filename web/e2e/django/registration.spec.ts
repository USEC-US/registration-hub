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
	for (const [index, tag] of tags.entries()) {
		const row = page.locator('[data-roster-row]').nth(index);
		await row.getByLabel('First and Middle name', { exact: true }).fill(`Player ${index + 1}`);
		await row.getByLabel('Last name', { exact: true }).fill('Example');
		await row.getByLabel('Date of birth', { exact: true }).fill('2005-01-01');
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
	await fillContacts(page);
	await fillRoster(page, ['Captain#ONE', 'Teammate#ONE']);
	const receipt = await submit(page);
	expect(receipt.members.map((member) => member.is_captain)).toEqual([true, false]);
	expect(receipt.members.map((member) => member.school_snapshot)).toEqual([
		institution,
		institution
	]);
	expect(receipt).not.toHaveProperty('contact_phone_snapshot');
	await expect(
		page.getByRole('heading', { name: 'Registration submitted', exact: true })
	).toBeVisible();
	await expect(page.locator('[data-registration-confirmation]')).toContainText(String(receipt.id));
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
	await fillContacts(page);
	await page.getByRole('button', { name: 'Add substitute', exact: true }).click();
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
	await expect(page.locator('[data-roster-row]')).toHaveCount(1);
	await fillContacts(page);
	await fillRoster(page, ['Solo#ONE']);
	const receipt = await submit(page);
	expect(receipt.members).toHaveLength(1);
	expect(receipt.members[0].is_captain).toBe(true);
});

test('paid guest proof reaches organizer verification and registration approval', async ({
	page,
	request
}) => {
	await page.goto(await registrationUrl(request, 'solo-paid'));
	await fillContacts(page);
	await fillRoster(page, ['PaidGuest#ONE']);
	await page.locator('[data-payment-proof-drop-zone]').evaluate((target, encoded) => {
		const bytes = Uint8Array.from(atob(encoded), (character) => character.charCodeAt(0));
		const transfer = new DataTransfer();
		transfer.items.add(new File([bytes], 'proof.png', { type: 'image/png' }));
		target.dispatchEvent(
			new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: transfer })
		);
	}, proof.buffer.toString('base64'));
	await expect(page.getByAltText('Selected payment proof preview')).toBeVisible();
	const receipt = await submit(page);
	expect(receipt.payment_attempts).toHaveLength(1);
	expect(receipt.payment_attempts[0].status).toBe('PENDING');
	await organizerLogin(page);
	await page.goto(`${api}/admin/registrations/registration/${receipt.id}/change/`);
	const proofLink = page.locator('a[href*="/media/payment-proofs/"]').first();
	await expect(proofLink).toBeVisible();
	const proofUrl = new URL((await proofLink.getAttribute('href'))!, api).href;
	const anonymousProof = await request.get(proofUrl);
	expect([401, 403]).toContain(anonymousProof.status());
	const organizerProof = await page.request.get(proofUrl);
	expect(organizerProof.status()).toBe(200);
	expect(organizerProof.headers()['cache-control']).toBe('private, no-store');
	await adminAction(page, 'paymentattempt', receipt.payment_attempts[0].id, 'verify_selected');
	await adminAction(page, 'registration', receipt.id, 'mark_under_review');
	await adminAction(page, 'registration', receipt.id, 'approve_selected');
	await page.goto(`${api}/admin/registrations/registration/${receipt.id}/change/`);
	await expect(adminField(page, 'Status')).toHaveText('Approved');
});

test('signed-in participant submits and uploads proof from the account page', async ({
	page,
	request
}) => {
	const registrationPath = await registrationUrl(request, 'solo-paid');
	await page.goto(`/en/auth/sign-in?redirect=${encodeURIComponent(registrationPath)}`);
	await page.getByLabel('Email', { exact: true }).fill('journey-player@example.test');
	await page.getByLabel('Password', { exact: true }).fill(password);
	await page.getByRole('button', { name: 'Sign in', exact: true }).click();
	await expect(page).toHaveURL(registrationPath);
	await fillContacts(page);
	await fillRoster(page, ['SignedPlayer#ONE']);
	const receipt = await submit(page);
	await expect(page).toHaveURL(`/en/account/registrations/${receipt.id}`);
	const chooserPromise = page.waitForEvent('filechooser');
	await page.getByRole('button', { name: 'Choose image', exact: true }).focus();
	await page.keyboard.press('Enter');
	await (await chooserPromise).setFiles(proof);
	await expect(page.getByAltText('Selected payment proof preview')).toBeVisible();
	const responsePromise = page.waitForResponse(
		(response) => response.url() === `${api}/api/registrations/${receipt.id}/payment-attempts/`
	);
	const refreshedDetail = page.waitForResponse(
		(response) =>
			response.url() === `${api}/api/registrations/${receipt.id}/` &&
			response.request().method() === 'GET'
	);
	await page.getByRole('button', { name: 'Upload payment proof', exact: true }).click();
	expect((await responsePromise).status()).toBe(201);
	const detail = await (await refreshedDetail).json();
	expect(detail.payment_attempts).toHaveLength(1);
	expect(detail.payment_attempts[0].status).toBe('PENDING');
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
	const replacement = await submit(page);
	expect(replacement.id).not.toBe(receipt.id);
	await expect(
		page.getByRole('heading', { name: 'Registration submitted', exact: true })
	).toBeVisible();
});
