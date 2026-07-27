/** @type {readonly ['bold', 'strong', 'link', 'icon']} */
export const RICH_TEXT_TAGS = ['bold', 'strong', 'link', 'icon'];

/** @type {Set<string>} */
const supportedRichTextTags = new Set(RICH_TEXT_TAGS);

/**
 * Finds opening markup tags while preserving the message-format escaping and
 * quoted-literal rules relevant to markup placeholders.
 *
 * @param {string} message
 * @returns {string[]}
 */
function markupTagNames(message) {
	const names = [];

	for (let index = 0; index < message.length; index += 1) {
		if (message[index] === '\\' && ['{', '}', '\\'].includes(message[index + 1] ?? '')) {
			index += 1;
			continue;
		}

		if (message[index] !== '{') continue;

		const closingIndex = placeholderClosingIndex(message, index);
		if (closingIndex === -1) continue;

		const placeholder = message.slice(index + 1, closingIndex);
		const match = /^#\s*([^\s=/@]+)/.exec(placeholder);
		if (match) names.push(match[1]);
		index = closingIndex;
	}

	return names;
}

/**
 * @param {string} message
 * @param {number} openingIndex
 */
function placeholderClosingIndex(message, openingIndex) {
	let inQuotedLiteral = false;

	for (let index = openingIndex + 1; index < message.length; index += 1) {
		if (inQuotedLiteral && message[index] === '\\') {
			index += 1;
			continue;
		}
		if (message[index] === '|') inQuotedLiteral = !inQuotedLiteral;
		if (message[index] === '}' && !inQuotedLiteral) return index;
	}

	return -1;
}

/**
 * @param {unknown} messages
 * @param {string} source
 * @returns {string[]}
 */
export function validateRichTextMarkup(messages, source) {
	/** @type {string[]} */
	const errors = [];
	visit(messages, '', source, errors);
	return errors;
}

/**
 * @param {unknown} value
 * @param {string} key
 * @param {string} source
 * @param {string[]} errors
 */
function visit(value, key, source, errors) {
	if (typeof value === 'string') {
		for (const tag of new Set(markupTagNames(value))) {
			if (supportedRichTextTags.has(tag)) continue;
			errors.push(
				`${source}: message '${key}' uses unsupported rich-text tag '${tag}'. Add it to RichText before using it in translations.`
			);
		}
		return;
	}

	if (!value || typeof value !== 'object') return;

	for (const [childKey, childValue] of Object.entries(value)) {
		if (childKey === '$schema') continue;
		visit(childValue, key ? `${key}.${childKey}` : childKey, source, errors);
	}
}
