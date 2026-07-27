import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
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

describe('check-rich-text-tags', () => {
	it('fails when a locale file uses a tag outside the RichText registry', async () => {
		const projectRoot = await mkdtemp(join(tmpdir(), 'rich-text-tags-'));
		temporaryRoots.push(projectRoot);
		await mkdir(join(projectRoot, 'project.inlang'), { recursive: true });
		await mkdir(join(projectRoot, 'messages'), { recursive: true });
		await writeFile(
			join(projectRoot, 'project.inlang', 'settings.json'),
			JSON.stringify({
				locales: ['en'],
				'plugin.inlang.messageFormat': { pathPattern: './messages/{locale}.json' }
			})
		);
		await writeFile(
			join(projectRoot, 'messages', 'en.json'),
			JSON.stringify({ notice: '{#em}New{/em}' })
		);

		const result = await runCheck(projectRoot);

		expect(result.exitCode).toBe(1);
		expect(result.stderr).toContain(
			"messages/en.json: message 'notice' uses unsupported rich-text tag 'em'."
		);
	});
});

function runCheck(projectRoot: string): Promise<{ exitCode: number | null; stderr: string }> {
	return new Promise((resolveCheck, reject) => {
		const process = spawn('node', [resolve('scripts/check-rich-text-tags.mjs')], {
			cwd: resolve('.'),
			env: { ...globalThis.process.env, RICH_TEXT_PROJECT_ROOT: projectRoot },
			stdio: ['ignore', 'ignore', 'pipe']
		});
		let stderr = '';
		process.stderr.on('data', (chunk) => {
			stderr += String(chunk);
		});
		process.once('error', reject);
		process.once('close', (exitCode) => resolveCheck({ exitCode, stderr }));
	});
}
