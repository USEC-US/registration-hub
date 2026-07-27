<script lang="ts">
	import type { RegistrationMemberInput } from '$lib/api/types';
	import * as m from '$lib/paraglide/messages';
	import * as Field from '$lib/components/ui/field';
	import { Input } from '$lib/components/ui/input';
	import * as RadioGroup from '$lib/components/ui/radio-group';

	interface Props {
		teamSizeMin: number;
		teamSizeMax: number;
		members?: RegistrationMemberInput[];
	}

	let {
		teamSizeMin,
		teamSizeMax,
		members = $bindable([])
	}: Props = $props();
	let captainValue = $derived(String(Math.max(0, members.findIndex((member) => member.is_captain))));

	function initializeMembers(): void {
		if (members.length === 0) {
			members = Array.from({ length: teamSizeMax }, (_, index) => ({
				gamer_tag_snapshot: '',
				school_snapshot: '',
				is_captain: index === 0,
				display_order: index + 1
			}));
		}

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
	<header class="mb-4 border-b border-(--line) pb-4">
		<h2 class="font-heading text-2xl font-semibold" id="roster-heading">{m.roster_heading()}</h2>
		<p class="mt-2 text-sm text-(--text-muted)">
			{m.roster_size_note({ minimum: teamSizeMin, maximum: teamSizeMax })}
		</p>
	</header>

	<RadioGroup.Root
		value={captainValue}
		onValueChange={(value) => selectCaptain(Number(value))}
		aria-label={m.roster_captain()}
		class="border border-(--line) gap-0"
	>
		{#each members as member, index (member.display_order)}
			<Field.Set
				class="grid gap-4 border-b border-(--line) p-4 last:border-b-0 lg:grid-cols-[5rem_minmax(0,1fr)_minmax(0,1fr)_8rem] lg:items-end"
				data-roster-row
			>
				<Field.Legend class="sr-only">{m.roster_member_label({ number: index + 1 })}</Field.Legend>
				<div class="grid gap-1">
					<span class="font-mono-data text-2xl font-semibold text-accent">
						{String(index + 1).padStart(2, '0')}
					</span>
					<span class="text-xs text-muted-foreground">
						{m.roster_member_number({ number: index + 1 })}
					</span>
				</div>
				<Field.Field>
					<Field.Label for={`member-${index + 1}-gamer-tag`}>{m.field_gamer_tag()}</Field.Label>
					<Input
						id={`member-${index + 1}-gamer-tag`}
						name={`member-${index + 1}-gamer-tag`}
						required
						maxlength={64}
						bind:value={member.gamer_tag_snapshot}
					/>
				</Field.Field>
				<Field.Field>
					<Field.Label for={`member-${index + 1}-school`}>{m.field_school()}</Field.Label>
					<Input
						id={`member-${index + 1}-school`}
						name={`member-${index + 1}-school`}
						required
						maxlength={128}
						bind:value={member.school_snapshot}
					/>
				</Field.Field>
				<Field.Label class="flex min-h-11 items-center gap-2 border px-3">
					<RadioGroup.Item value={String(index)} aria-label={m.roster_set_captain({ number: index + 1 })} />
					<span>{m.roster_captain()}</span>
					<span class="sr-only">{m.roster_set_captain({ number: index + 1 })}</span>
				</Field.Label>
			</Field.Set>
		{/each}
	</RadioGroup.Root>
</section>
