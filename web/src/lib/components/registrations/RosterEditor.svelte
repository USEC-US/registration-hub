<script lang="ts">
	import InstitutionCombobox from '$lib/components/forms/InstitutionCombobox.svelte';
	import type { RegistrationMemberInput, InstitutionChoice, SubmitterRole } from '$lib/api/types';
	import * as m from '$lib/paraglide/messages';
	import * as Field from '$lib/components/ui/field';
	import { Input } from '$lib/components/ui/input';
	import * as RadioGroup from '$lib/components/ui/radio-group';
	import { Button } from '$lib/components/ui/button';

	interface Props {
		submitterRole?: SubmitterRole;
		errors?: string[];
		teamSizeMin: number;
		teamSizeMax: number;
		members?: RegistrationMemberInput[];
	}

	let {
		teamSizeMin,
		teamSizeMax,
		submitterRole = 'captain',
		errors = [],
		members = $bindable([])
	}: Props = $props();
	let captainValue = $derived(
		String(
			Math.max(
				0,
				members.findIndex((member) => member.is_captain)
			)
		)
	);

	function initializeMembers(): void {
		if (members.length === 0) {
			members = Array.from({ length: teamSizeMin }, (_, index) => ({
				gamer_tag_snapshot: '',
				institution_label: '',
				is_captain: index === 0,
				display_order: index + 1
			}));
		}
	}

	initializeMembers();
	let nextRowId = 0;
	let rowIds = $state<number[]>([]);
	function initializeRowIds() {
		rowIds = members.map(() => nextRowId++);
	}
	initializeRowIds();
	$effect(() => {
		if (
			submitterRole === 'captain' &&
			members.some((member, index) => member.is_captain !== (index === 0))
		) {
			selectCaptain(0);
		}
	});

	function addMember(): void {
		if (members.length >= teamSizeMax) return;
		rowIds = [...rowIds, nextRowId++];
		members = [
			...members,
			{
				gamer_tag_snapshot: '',
				institution_label: '',
				is_captain: false,
				display_order: members.length + 1
			}
		];
	}

	function removeMember(index: number): void {
		if (members.length <= teamSizeMin || (submitterRole === 'captain' && index === 0)) return;
		rowIds = rowIds.filter((_, position) => position !== index);
		const remaining = members.filter((_, position) => position !== index);
		const captainRemoved = !remaining.some((member) => member.is_captain);
		members = remaining.map((member, position) => ({
			...member,
			display_order: position + 1,
			is_captain: captainRemoved ? position === 0 : member.is_captain
		}));
	}

	function selectCaptain(selectedIndex: number): void {
		members = members.map((member, index) => ({
			...member,
			is_captain: index === selectedIndex
		}));
	}

	function updateMember(index: number, field: 'gamer_tag_snapshot', event: Event): void {
		const value = (event.currentTarget as HTMLInputElement).value;
		members = members.map((member, memberIndex) =>
			memberIndex === index ? { ...member, [field]: value } : member
		);
	}

	function updateInstitution(index: number, choice: InstitutionChoice | undefined) {
		members = members.map((member, position) =>
			position === index
				? {
						gamer_tag_snapshot: member.gamer_tag_snapshot,
						is_captain: member.is_captain,
						display_order: member.display_order,
						...(choice ?? { institution_label: '' })
					}
				: member
		);
	}
</script>

<section aria-labelledby="roster-heading">
	<header class="mb-4 border-b border-(--line) pb-4">
		<h2 class="font-heading text-2xl font-semibold" id="roster-heading">{m.roster_heading()}</h2>
		<p class="mt-2 text-sm text-(--text-muted)">
			{m.roster_size_note({ minimum: teamSizeMin, maximum: teamSizeMax })}
		</p>
	</header>

	<p class="mb-4 text-sm text-muted-foreground">{m.registration_gamer_tag_hint()}</p>
	{#if errors.length}<div role="alert" class="mb-4 text-sm text-destructive">
			{#each errors as error (error)}<p>{error}</p>{/each}
		</div>{/if}
	<RadioGroup.Root
		value={captainValue}
		onValueChange={(value) => selectCaptain(Number(value))}
		aria-label={m.roster_captain()}
		class="border border-(--line) gap-0"
	>
		{#each members as member, index (rowIds[index])}
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
						value={member.gamer_tag_snapshot}
						oninput={(event) => updateMember(index, 'gamer_tag_snapshot', event)}
					/>
				</Field.Field>
				<InstitutionCombobox
					required
					bind:choice={() => members[index], (choice) => updateInstitution(index, choice)}
					initialLabel={member.institution_label ?? ''}
				/>
				<Field.Label class="flex min-h-11 items-center gap-2 border px-3">
					<RadioGroup.Item
						value={String(index)}
						disabled={submitterRole === 'captain'}
						aria-label={m.roster_set_captain({ number: index + 1 })}
					/>
					<span>{m.roster_captain()}</span>
					<span class="sr-only">{m.roster_set_captain({ number: index + 1 })}</span>
				</Field.Label>
				{#if teamSizeMin < teamSizeMax}
					<Button
						type="button"
						variant="outline"
						disabled={members.length <= teamSizeMin || (submitterRole === 'captain' && index === 0)}
						onclick={() => removeMember(index)}
					>
						{m.roster_remove_member({ number: index + 1 })}
					</Button>
				{/if}
			</Field.Set>
		{/each}
	</RadioGroup.Root>
	{#if teamSizeMin < teamSizeMax}
		<Button
			type="button"
			variant="outline"
			class="mt-4"
			disabled={members.length >= teamSizeMax}
			onclick={addMember}>{m.roster_add_player()}</Button
		>
	{/if}
</section>
