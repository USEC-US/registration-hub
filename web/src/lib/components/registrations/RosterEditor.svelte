<script lang="ts">
	import DatePicker from '$lib/components/forms/DatePicker.svelte';
	import { getLocale } from '$lib/paraglide/runtime';
	import { today, getLocalTimeZone } from '@internationalized/date';
	import InstitutionCombobox from '$lib/components/forms/InstitutionCombobox.svelte';
	import type { RegistrationMemberInput, InstitutionChoice, SubmitterRole } from '$lib/api/types';
	import * as m from '$lib/paraglide/messages';
	import * as Field from '$lib/components/ui/field';
	import { Input } from '$lib/components/ui/input';
	import * as RadioGroup from '$lib/components/ui/radio-group';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import * as Alert from '$lib/components/ui/alert';
	import ShieldCheck from '@lucide/svelte/icons/shield-check';
	import UserPlus from '@lucide/svelte/icons/user-plus';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { cn } from '$lib/utils';

	interface Props {
		submitterRole?: SubmitterRole;
		errors?: string[];
		mainRosterSize: number;
		substituteLimit: number;
		studentsOnly?: boolean;
		members?: RegistrationMemberInput[];
		institutionLabels?: Record<string, string>;
	}

	let {
		mainRosterSize,
		substituteLimit,
		studentsOnly = false,
		submitterRole = 'captain',
		errors = [],
		institutionLabels = $bindable({}),
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
			members = Array.from({ length: mainRosterSize }, (_, index) => ({
				gamer_tag_snapshot: '',
				first_name_snapshot: '',
				last_name_snapshot: '',
				date_of_birth_snapshot: '',
				student_id_snapshot: '',
				institution_label: '',
				is_captain: index === 0,
				roster_role: 'main',
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

	function addMember(role: 'main' | 'substitute' = 'substitute'): void {
		if (
			role === 'substitute' &&
			members.filter((member) => member.roster_role === 'substitute').length >= substituteLimit
		)
			return;
		rowIds = [...rowIds, nextRowId++];
		members = [
			...members,
			{
				gamer_tag_snapshot: '',
				first_name_snapshot: '',
				last_name_snapshot: '',
				date_of_birth_snapshot: '',
				student_id_snapshot: '',
				institution_label: '',
				is_captain: false,
				roster_role: role,
				display_order: members.length + 1
			}
		];
	}

	function removeMember(index: number): void {
		if (
			(members[index].roster_role === 'main' &&
				members.filter((m) => m.roster_role === 'main').length <= mainRosterSize) ||
			(submitterRole === 'captain' && index === 0)
		)
			return;
		rowIds = rowIds.filter((_, position) => position !== index);
		const remainingLabels = members
			.filter((_, position) => position !== index)
			.map(
				(member) =>
					institutionLabels[String(member.display_order)] ?? member.institution_label ?? ''
			);
		institutionLabels = Object.fromEntries(
			remainingLabels.map((label, index) => [String(index + 1), label])
		);
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

	function updateMember(
		index: number,
		field:
			| 'gamer_tag_snapshot'
			| 'first_name_snapshot'
			| 'last_name_snapshot'
			| 'date_of_birth_snapshot'
			| 'student_id_snapshot',
		event: Event
	): void {
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
						first_name_snapshot: member.first_name_snapshot,
						last_name_snapshot: member.last_name_snapshot,
						date_of_birth_snapshot: member.date_of_birth_snapshot,
						student_id_snapshot: member.student_id_snapshot,
						is_captain: member.is_captain,
						roster_role: member.roster_role,
						display_order: member.display_order,
						...(choice ?? { institution_label: '' })
					}
				: member
		);
	}
	const latestBirthDate = today(getLocalTimeZone()).toString();
</script>

<section aria-labelledby="roster-heading">
	<header class="mb-6 flex flex-col gap-4">
		<div class="flex items-start gap-3">
			<span
				class="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 font-mono-data text-sm font-semibold text-primary"
				aria-hidden="true">02</span
			>
			<div class="flex flex-col gap-1">
				<h2 class="font-semibold" id="roster-heading">{m.roster_heading()}</h2>
				<p class="text-sm text-muted-foreground">
					{m.roster_size_note({ main: mainRosterSize, substitutes: substituteLimit })}
				</p>
			</div>
		</div>
		<div class="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
			<p class="flex flex-1 items-start gap-2 text-xs leading-5 text-muted-foreground">
				<ShieldCheck
					class="mt-0.5 size-4 shrink-0"
					aria-hidden="true"
				/>{m.roster_identity_private()}
			</p>
			{#if studentsOnly}<Badge variant="secondary">{m.roster_student_id_required_badge()}</Badge
				>{/if}
		</div>
		<p class="text-xs leading-5 text-muted-foreground">{m.registration_gamer_tag_hint()}</p>
	</header>
	{#if errors.length}
		<Alert.Root variant="destructive" class="mb-4 rounded-lg"
			><Alert.Description
				>{#each errors as error (error)}<p>{error}</p>{/each}</Alert.Description
			></Alert.Root
		>
	{/if}
	<RadioGroup.Root
		value={captainValue}
		onValueChange={(value) => selectCaptain(Number(value))}
		aria-label={m.roster_captain()}
		class="gap-4"
	>
		{#each members as member, index (rowIds[index])}
			{#if index === 0 || member.roster_role !== members[index - 1].roster_role}
				<h3 class="pt-2 text-sm font-semibold first:pt-0">
					{member.roster_role === 'main'
						? m.roster_main_heading({ count: mainRosterSize })
						: m.roster_substitutes_heading({ count: substituteLimit })}
				</h3>
			{/if}
			<Field.Set
				class="flex min-w-0 flex-col gap-0 overflow-hidden rounded-lg border"
				data-roster-row
			>
				<Field.Legend class="sr-only">{m.roster_member_label({ number: index + 1 })}</Field.Legend>
				<div
					class="flex flex-wrap items-center justify-between gap-3 border-b bg-muted/30 px-4 py-3 sm:px-5"
				>
					<div class="flex items-center gap-3">
						<span
							class={cn(
								'flex size-8 items-center justify-center rounded-full font-mono-data text-xs font-semibold',
								member.is_captain
									? 'bg-primary text-primary-foreground'
									: 'bg-muted text-muted-foreground'
							)}>{String(index + 1).padStart(2, '0')}</span
						>
						<span class="text-sm font-medium">{m.roster_member_number({ number: index + 1 })}</span>
					</div>
					<div class="flex flex-wrap items-center gap-3">
						<Field.Label
							class="flex min-h-9 cursor-pointer items-center gap-2 rounded-full border bg-card px-3"
						>
							<RadioGroup.Item
								value={String(index)}
								disabled={submitterRole === 'captain'}
								aria-label={m.roster_set_captain({ number: index + 1 })}
							/>
							<span>{m.roster_captain()}</span>
							<span class="sr-only">{m.roster_set_captain({ number: index + 1 })}</span>
						</Field.Label>
						{#if member.roster_role === 'substitute' || members.filter((m) => m.roster_role === 'main').length > mainRosterSize}
							<Button
								type="button"
								variant="ghost"
								size="icon"
								aria-label={m.roster_remove_member({ number: index + 1 })}
								disabled={submitterRole === 'captain' && index === 0}
								onclick={() => removeMember(index)}><Trash2 aria-hidden="true" /></Button
							>
						{/if}
					</div>
				</div>
				<Field.Group class="grid gap-5 p-4 sm:grid-cols-2 sm:p-5 xl:grid-cols-3">
					<Field.Field>
						<Field.Label for={`member-${index + 1}-last-name`}>{m.roster_last_name()}</Field.Label>
						<Input
							id={`member-${index + 1}-last-name`}
							name={`member-${index + 1}-last-name`}
							required
							maxlength={150}
							value={member.last_name_snapshot}
							oninput={(event) => updateMember(index, 'last_name_snapshot', event)}
						/>
					</Field.Field>
					<Field.Field>
						<Field.Label for={`member-${index + 1}-first-name`}>{m.roster_first_name()}</Field.Label
						>
						<Input
							id={`member-${index + 1}-first-name`}
							name={`member-${index + 1}-first-name`}
							required
							maxlength={150}
							value={member.first_name_snapshot}
							oninput={(event) => updateMember(index, 'first_name_snapshot', event)}
						/>
					</Field.Field>
					<Field.Field>
						<Field.Label for={`member-${index + 1}-birth-date`}
							>{m.roster_date_of_birth()}</Field.Label
						>
						<DatePicker
							id={`member-${index + 1}-birth-date`}
							name={`member-${index + 1}-birth-date`}
							required
							max={latestBirthDate}
							locale={getLocale()}
							bind:value={
								() => members[index].date_of_birth_snapshot,
								(value) => {
									members = members.map((member, position) =>
										position === index ? { ...member, date_of_birth_snapshot: value } : member
									);
								}
							}
						/>
					</Field.Field>
					<Field.Field>
						<Field.Label for={`member-${index + 1}-student-id`}>{m.roster_student_id()}</Field.Label
						>
						<Input
							id={`member-${index + 1}-student-id`}
							name={`member-${index + 1}-student-id`}
							required={studentsOnly}
							maxlength={128}
							value={member.student_id_snapshot}
							oninput={(event) => updateMember(index, 'student_id_snapshot', event)}
						/>
						{#if !studentsOnly}<Field.Description
								>{m.roster_student_id_optional()}</Field.Description
							>{/if}
					</Field.Field>
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
						initialLabel={institutionLabels[String(member.display_order)] ??
							member.institution_label ??
							''}
						onlabel={(label) =>
							(institutionLabels = { ...institutionLabels, [String(member.display_order)]: label })}
					/>
				</Field.Group>
			</Field.Set>
		{/each}
	</RadioGroup.Root>
	{#if members.filter((m) => m.roster_role === 'main').length < mainRosterSize}<Button
			type="button"
			variant="outline"
			onclick={() => addMember('main')}>{m.stages_add_main()}</Button
		>{/if}
	{#if substituteLimit > 0}
		{#if !members.some((member) => member.roster_role === 'substitute')}
			<h3 class="mt-4 font-semibold">{m.roster_substitutes_heading({ count: substituteLimit })}</h3>
			<p class="mt-2 text-sm text-muted-foreground">{m.roster_substitutes_optional()}</p>
		{/if}
		<Button
			type="button"
			variant="outline"
			class="mt-4 min-h-12 w-full rounded-lg border-dashed"
			disabled={members.filter((member) => member.roster_role === 'substitute').length >=
				substituteLimit}
			onclick={() => addMember()}
			><UserPlus data-icon="inline-start" aria-hidden="true" />{m.roster_add_substitute()}</Button
		>
	{/if}
</section>
