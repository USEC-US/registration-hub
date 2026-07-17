<script lang="ts">
	import type { RegistrationRead, RegistrationStatus } from '$lib/api/types';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';

	interface Props {
		events: RegistrationRead['status_events'];
	}

	let { events }: Props = $props();

	function statusLabel(status: RegistrationStatus): string {
		switch (status) {
			case 'SUBMITTED':
				return m.status_SUBMITTED();
			case 'UNDER_REVIEW':
				return m.status_UNDER_REVIEW();
			case 'APPROVED':
				return m.status_APPROVED();
			case 'REJECTED':
				return m.status_REJECTED();
		}
	}

	function formatDate(value: string): string {
		return new Intl.DateTimeFormat(getLocale(), {
			dateStyle: 'medium',
			timeStyle: 'short'
		}).format(new Date(value));
	}
</script>

{#if events.length > 0}
	<ol class="border-l border-[var(--line)]" aria-label={m.status_timeline_label()}>
		{#each events as event, index (`${event.created_at}-${event.to_status}`)}
			<li
				class="relative grid gap-1 pb-6 pl-6 last:pb-0"
				aria-current={index === events.length - 1 ? 'step' : undefined}
			>
				<span
					class="absolute -left-[5px] top-1 h-[9px] w-[9px] border border-[var(--accent)] bg-white"
					aria-hidden="true"
				></span>
				<span class="font-semibold text-[var(--text)]">{statusLabel(event.to_status)}</span>
				<time class="font-mono-data text-xs text-[var(--text-muted)]" datetime={event.created_at}>
					{formatDate(event.created_at)}
				</time>
			</li>
		{/each}
	</ol>
{:else}
	<p class="text-sm text-[var(--text-muted)]">{m.status_timeline_empty()}</p>
{/if}
