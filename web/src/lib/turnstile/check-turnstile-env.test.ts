import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

const temporaryRoots: string[] = [];

afterEach(async () => {
	await Promise.all(
		temporaryRoots.splice(0).map((root) => rm(root, { force: true, recursive: true }))
	);
});

describe('check-turnstile-env', () => {
	it('accepts PUBLIC_TURNSTILE_SITE_KEY from .env.production', async () => {
		const projectRoot = await mkdtemp(join(tmpdir(), 'turnstile-env-'));
		temporaryRoots.push(projectRoot);
		await writeFile(
			join(projectRoot, '.env.production'),
			'PUBLIC_TURNSTILE_SITE_KEY=1x00000000000000000000AA\n'
		);

		const result = await runGuard(projectRoot);

		expect(result.exitCode).toBe(0);
		expect(result.stderr).toBe('');
	});
});

function runGuard(projectRoot: string): Promise<{ exitCode: number | null; stderr: string }> {
	return new Promise((resolveGuard, reject) => {
		const env = { ...globalThis.process.env };
		delete env.PUBLIC_TURNSTILE_SITE_KEY;
		const process = spawn('node', [resolve('scripts/check-turnstile-env.mjs')], {
			cwd: projectRoot,
			env,
			stdio: ['ignore', 'ignore', 'pipe']
		});
		let stderr = '';
		process.stderr.on('data', (chunk) => {
			stderr += String(chunk);
		});
		process.once('error', reject);
		process.once('close', (exitCode) => resolveGuard({ exitCode, stderr }));
	});
}
