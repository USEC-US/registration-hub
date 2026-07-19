<script lang="ts">
	import type { RegistrationMemberInput } from '$lib/api/types';
	import * as m from '$lib/paraglide/messages';

	interface Props {
		teamSizeMin: number;
		teamSizeMax: number;
		initialGamerTag: string;
		initialSchool: string;
		members?: RegistrationMemberInput[];
	}

	let {
		teamSizeMin,
		teamSizeMax,
		initialGamerTag,
		initialSchool,
		members = $bindable([])
	}: Props = $props();

	function initializeMembers(): void {
		if (members.length > 0) return;
		members = Array.from({ length: teamSizeMax }, (_, index) => ({
			gamer_tag_snapshot: index === 0 ? initialGamerTag : '',
			school_snapshot: index === 0 ? initialSchool : '',
			is_captain: index === 0,
			display_order: index + 1
		}));
	}

	initializeMembers();

	function selectCaptain(selectedIndex: number): void {
		members = members.map((member, index) => ({
			...member,
			is_captain: index === selectedIndex
		}));
	}
</script>

<section aria-labelledby="roster-heading">
	<header class="mb-4 border-b border-[var(--line)] pb-4">
		<h2 class="font-heading text-2xl font-semibold" id="roster-heading">{m.roster_heading()}</h2>
		<p class="mt-2 text-sm text-[var(--text-muted)]">
			{m.roster_size_note({ minimum: teamSizeMin, maximum: teamSizeMax })}
		</p>
	</header>

	<div class="border border-[var(--line)]">
		{#each members as member, index (member.display_order)}
			<fieldset
				class="grid gap-4 border-b border-[var(--line)] p-4 last:border-b-0 lg:grid-cols-[5rem_minmax(0,1fr)_minmax(0,1fr)_8rem] lg:items-end"
				data-roster-row
			>
				<legend class="sr-only">{m.roster_member_label({ number: index + 1 })}</legend>
				<div class="grid gap-1">
					<span class="font-mono-data text-2xl font-semibold text-[var(--accent)]">
						{String(index + 1).padStart(2, '0')}
					</span>
					<span class="text-xs text-[var(--text-muted)]">
						{m.roster_member_number({ number: index + 1 })}
					</span>
				</div>
				<label class="grid gap-2 text-sm font-semibold" for={`member-${index + 1}-gamer-tag`}>
					{m.field_gamer_tag()}
					<input
						class="min-h-11 border border-[var(--line)] bg-white px-3 py-2 font-normal focus:border-[var(--accent)] focus:ring-0"
						id={`member-${index + 1}-gamer-tag`}
						name={`member-${index + 1}-gamer-tag`}
						required
						maxlength="64"
						bind:value={member.gamer_tag_snapshot}
					/>
				</label>
				<label class="grid gap-2 text-sm font-semibold" for={`member-${index + 1}-school`}>
					{m.field_school()}
					<input
						class="min-h-11 border border-[var(--line)] bg-white px-3 py-2 font-normal focus:border-[var(--accent)] focus:ring-0"
						id={`member-${index + 1}-school`}
						name={`member-${index + 1}-school`}
						required
						maxlength="128"
						bind:value={member.school_snapshot}
					/>
				</label>
				<label
					class="flex min-h-11 items-center gap-2 border border-[var(--line)] px-3 text-sm font-semibold"
				>
					<input
						type="radio"
						name="captain"
						checked={member.is_captain}
						onchange={() => selectCaptain(index)}
					/>
					<span>{m.roster_captain()}</span>
					<span class="sr-only">{m.roster_set_captain({ number: index + 1 })}</span>
				</label>
			</fieldset>
		{/each}
	</div>
</section>
