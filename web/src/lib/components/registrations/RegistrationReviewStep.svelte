<script lang="ts">
	import type { RegistrationSubmissionPayload } from '$lib/api/types';
	import * as Card from '$lib/components/ui/card';
	import * as m from '$lib/paraglide/messages';
	let {
		fields,
		institutionLabels,
		fee,
		holdMinutes
	}: {
		fields: RegistrationSubmissionPayload;
		institutionLabels: Record<string, string>;
		fee: string;
		holdMinutes: number;
	} = $props();
</script>

<Card.Root class="rounded-xl py-6"
	><Card.Header>
		<div class="flex items-start gap-3">
			<span
				class="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 font-mono-data text-sm font-semibold text-primary"
				aria-hidden="true">03</span
			>
			<div class="flex flex-col gap-1">
				<Card.Title><h2>{m.stages_review()}</h2></Card.Title><Card.Description
					>{m.registration_corrections()}</Card.Description
				>
			</div>
		</div></Card.Header
	>
	<Card.Content class="flex flex-col gap-4 break-words">
		<dl class="grid gap-5 rounded-lg bg-muted/30 p-4 sm:grid-cols-2">
			{#each [[m.field_team_name(), fields.team_name], [m.field_team_tag(), fields.team_tag], [m.registration_role_heading(), fields.submitter_role === 'manager' ? m.registration_role_manager() : m.registration_role_captain()], [m.registration_manager_name(), fields.manager_name_snapshot], [m.registration_facebook(), fields.contact_facebook_snapshot], [m.registration_phone(), fields.contact_phone_snapshot], [m.registration_email(), fields.contact_email_snapshot], [m.registration_discord(), fields.contact_discord_snapshot]] as [label, value] (label)}
				{#if value}<div>
						<dt class="text-sm text-muted-foreground">{label}</dt>
						<dd class="mt-1 font-medium">{value}</dd>
					</div>{/if}{/each}
		</dl>
		<ol class="flex flex-col gap-3">
			{#each fields.members as member (member.display_order)}<li class="rounded-lg border p-4">
					<p class="font-semibold">
						{member.gamer_tag_snapshot}
						{member.is_captain ? `· ${m.roster_captain()}` : ''}
					</p>
					<p>
						{member.last_name_snapshot}
						{member.first_name_snapshot} · {member.date_of_birth_snapshot}
					</p>
					{#if institutionLabels[String(member.display_order)] || member.institution_label}
						<p>{institutionLabels[String(member.display_order)] ?? member.institution_label}</p>
					{/if}
					{#if member.student_id_snapshot}<p>{member.student_id_snapshot}</p>{/if}
					<p>
						{member.roster_role === 'main'
							? m.roster_main_heading({ count: 1 })
							: m.roster_substitutes_heading({ count: 1 })}
					</p>
				</li>{/each}
		</ol>
	</Card.Content><Card.Footer class="flex-col items-start gap-2 border-t"
		><p>{m.game_fee()}: {fee}</p>
		<p>{m.stages_hold({ minutes: holdMinutes })}</p></Card.Footer
	></Card.Root
>
