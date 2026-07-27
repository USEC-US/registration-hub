import { describe, expect, it } from 'vitest';
import en from '../../../messages/en.json';
import vi from '../../../messages/vi.json';
import { validateRichTextMarkup } from './rich-text-tags.js';

describe('validateRichTextMarkup', () => {
	it('accepts every checked-in locale message', () => {
		expect(validateRichTextMarkup(en, 'en.json')).toEqual([]);
		expect(validateRichTextMarkup(vi, 'vi.json')).toEqual([]);
	});

	it('reports the source, message key, and unsupported tag', () => {
		expect(validateRichTextMarkup({ announcement: '{#em}Important{/em}' }, 'en.json')).toEqual([
			"en.json: message 'announcement' uses unsupported rich-text tag 'em'. Add it to RichText before using it in translations."
		]);
	});
});
