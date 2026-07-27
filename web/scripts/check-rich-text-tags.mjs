import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateRichTextMarkup } from '../src/lib/i18n/rich-text-tags.js';

const projectRoot =
	process.env.RICH_TEXT_PROJECT_ROOT ?? resolve(fileURLToPath(new URL('..', import.meta.url)));
const settings = JSON.parse(
	await readFile(resolve(projectRoot, 'project.inlang/settings.json'), 'utf8')
);
const pathPattern = settings['plugin.inlang.messageFormat'].pathPattern;
const errors = [];

for (const locale of settings.locales) {
	const relativePath = pathPattern.replace('{locale}', locale).replace(/^\.\//, '');
	const messages = JSON.parse(await readFile(resolve(projectRoot, relativePath), 'utf8'));
	errors.push(...validateRichTextMarkup(messages, relativePath));
}

if (errors.length > 0) {
	console.error(errors.join('\n'));
	process.exitCode = 1;
}
