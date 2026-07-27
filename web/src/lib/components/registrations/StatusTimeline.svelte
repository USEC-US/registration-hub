<script lang="ts">
	import type { RegistrationRead, RegistrationStatus } from '$lib/api/types';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import { Badge } from '$lib/components/ui/badge';

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

	function statusClass(status: RegistrationStatus): string {
		switch (status) {
			case 'APPROVED':
				return 'border-success text-success';
			case 'REJECTED':
				return 'border-destructive text-destructive';
			default:
				return '';
		}
	}
</script>

{#if events.length > 0}
	<ol class="border-l border-(--line)" aria-label={m.status_timeline_label()}>
		{#each events as event, index (`${event.created_at}-${event.to_status}`)}
			<li
				class="relative grid gap-1 pb-6 pl-6 last:pb-0"
				aria-current={index === events.length - 1 ? 'step' : undefined}
			>
					<span class="absolute -left-1.25 top-1 size-2.25 border border-primary bg-background" aria-hidden="true"></span>
					<Badge variant={event.to_status === 'REJECTED' ? 'destructive' : 'outline'} class={statusClass(event.to_status)}>
						{statusLabel(event.to_status)}
					</Badge>
					<time class="font-mono-data text-xs text-muted-foreground" datetime={event.created_at}>
					{formatDate(event.created_at)}
				</time>
			</li>
		{/each}
	</ol>
{:else}
	<p class="text-sm text-muted-foreground">{m.status_timeline_empty()}</p>
{/if}
