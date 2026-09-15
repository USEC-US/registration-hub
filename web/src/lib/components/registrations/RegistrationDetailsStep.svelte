<script lang="ts">
	import type { SubmitterRole } from '$lib/api/types';
	import Field from '$lib/components/forms/Field.svelte';
	import * as m from '$lib/paraglide/messages';
	import * as Card from '$lib/components/ui/card';
	import * as FormField from '$lib/components/ui/field';
	import * as RadioGroup from '$lib/components/ui/radio-group';
	import UserRound from '@lucide/svelte/icons/user-round';
	import ClipboardList from '@lucide/svelte/icons/clipboard-list';
	import ShieldCheck from '@lucide/svelte/icons/shield-check';
	let {
		teamRequired,
		teamName = $bindable(''),
		teamTag = $bindable(''),
		submitterRole = $bindable<SubmitterRole>('captain'),
		managerName = $bindable(''),
		facebook = $bindable(''),
		phone = $bindable(''),
		email = $bindable(''),
		discord = $bindable(''),
		fieldErrors = {}
	}: {
		teamRequired: boolean;
		teamName?: string;
		teamTag?: string;
		submitterRole?: SubmitterRole;
		managerName?: string;
		facebook?: string;
		phone?: string;
		email?: string;
		discord?: string;
		fieldErrors?: Record<string, string[]>;
	} = $props();
</script>

<Card.Root class="gap-6 rounded-xl py-6" aria-labelledby="registration-details-heading">
	<Card.Header>
		<div class="flex items-start gap-3">
			<span
				class="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 font-mono-data text-sm font-semibold text-primary"
				aria-hidden="true">01</span
			>
			<div class="flex flex-col gap-1">
				<Card.Title
					><h2 id="registration-details-heading">
						{m.registration_details_heading()}
					</h2></Card.Title
				>
				<Card.Description>{m.registration_details_intro()}</Card.Description>
			</div>
		</div>
	</Card.Header>
	<Card.Content class="flex flex-col gap-6">
		<FormField.Set>
			<FormField.Legend>{m.registration_role_heading()}</FormField.Legend>
			<RadioGroup.Root
				bind:value={submitterRole}
				aria-label={m.registration_role_heading()}
				class="grid gap-3 sm:grid-cols-2"
			>
				<FormField.Label
					class="w-full cursor-pointer items-start gap-3 rounded-lg border p-4 transition-colors hover:bg-muted/50"
				>
					<RadioGroup.Item
						value="captain"
						aria-label={m.registration_role_captain()}
						class="mt-1 shrink-0"
					/>
					<span class="flex flex-col gap-1.5">
						<span class="flex items-center gap-2 font-semibold"
							><UserRound class="size-4" aria-hidden="true" />{m.registration_role_captain()}</span
						>
						<span class="text-sm font-normal text-muted-foreground"
							>{m.registration_captain_hint()}</span
						>
					</span>
				</FormField.Label>
				<FormField.Label
					class="w-full cursor-pointer items-start gap-3 rounded-lg border p-4 transition-colors hover:bg-muted/50"
				>
					<RadioGroup.Item
						value="manager"
						aria-label={m.registration_role_manager()}
						class="mt-1 shrink-0"
					/>
					<span class="flex flex-col gap-1.5">
						<span class="flex items-center gap-2 font-semibold"
							><ClipboardList
								class="size-4"
								aria-hidden="true"
							/>{m.registration_role_manager()}</span
						>
						<span class="text-sm font-normal text-muted-foreground"
							>{m.registration_manager_hint()}</span
						>
					</span>
				</FormField.Label>
			</RadioGroup.Root>
		</FormField.Set>
		{#if teamRequired}
			<FormField.Group class="border-t pt-6 sm:grid sm:grid-cols-[2fr_1fr]">
				<Field
					label={m.field_team_name()}
					name="team_name"
					required
					maxlength={100}
					error={fieldErrors.team_name?.[0]}
					bind:value={teamName}
				/>
				<Field
					label={m.field_team_tag()}
					name="team_tag"
					required
					minlength={2}
					maxlength={5}
					pattern={'[A-Za-z0-9]{2,5}'}
					hint={m.team_tag_hint()}
					error={fieldErrors.team_tag?.[0]}
					bind:value={
						() => teamTag,
						(value) => {
							teamTag = value.replace(/[a-z]/g, (letter) => letter.toUpperCase());
						}
					}
				/>
			</FormField.Group>
		{/if}
		<FormField.Set class="border-t pt-6">
			<FormField.Legend>{m.registration_contact_heading()}</FormField.Legend>
			<FormField.Description class="flex items-start gap-2"
				><ShieldCheck
					class="mt-0.5 size-4 shrink-0"
					aria-hidden="true"
				/>{m.registration_contact_private()}</FormField.Description
			>
			<FormField.Group class="sm:grid sm:grid-cols-2">
				{#if submitterRole === 'manager'}<Field
						label={m.registration_manager_name()}
						name="manager_name_snapshot"
						required
						maxlength={100}
						error={fieldErrors.manager_name_snapshot?.[0]}
						bind:value={managerName}
					/>{/if}
				<Field
					label={m.registration_facebook()}
					name="contact_facebook_snapshot"
					required
					maxlength={255}
					error={fieldErrors.contact_facebook_snapshot?.[0]}
					bind:value={facebook}
				/>
				<Field
					label={m.registration_phone()}
					name="contact_phone_snapshot"
					type="tel"
					required
					maxlength={32}
					error={fieldErrors.contact_phone_snapshot?.[0]}
					bind:value={phone}
				/>
				<Field
					label={m.registration_email()}
					name="contact_email_snapshot"
					type="email"
					maxlength={254}
					error={fieldErrors.contact_email_snapshot?.[0]}
					bind:value={email}
				/>
				<Field
					label={m.registration_discord()}
					name="contact_discord_snapshot"
					maxlength={100}
					error={fieldErrors.contact_discord_snapshot?.[0]}
					bind:value={discord}
				/>
			</FormField.Group>
		</FormField.Set>
	</Card.Content>
</Card.Root>
