/** Match the server's accent removal without changing the saved player identity. */
export function transferContent(template: string, participant: string): string {
	return template
		.replace(/{{|}}|{participant}/g, (match) =>
			match === '{{' ? '{' : match === '}}' ? '}' : participant
		)
		.replace(/đ/g, 'd')
		.replace(/Đ/g, 'D')
		.normalize('NFD')
		.replace(/\p{M}/gu, '')
		.replace(/\s+/gu, ' ')
		.trim();
}
