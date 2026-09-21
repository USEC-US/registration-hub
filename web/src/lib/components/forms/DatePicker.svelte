<script lang="ts">
	import { parseDate, type DateValue } from '@internationalized/date';
	import { Calendar } from '$lib/components/ui/calendar';
	import * as Popover from '$lib/components/ui/popover';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import CalendarIcon from '@lucide/svelte/icons/calendar';
	import {
		dateLocale,
		datePlaceholder,
		formatDateOnly,
		parseDisplayDate
	} from '$lib/time/date-format';
	import * as m from '$lib/paraglide/messages';

	let {
		id,
		name,
		value = $bindable(''),
		locale,
		required = false,
		max
	}: {
		id: string;
		name: string;
		value?: string;
		locale: string;
		required?: boolean;
		max?: string;
	} = $props();
	let open = $state(false);
	let input = $state<HTMLInputElement | null>(null);
	let text = $state('');
	let previousValue: string | undefined;
	let previousLocale: string | undefined;
	const selected = $derived(value ? parseDate(value) : undefined);
	const maximum = $derived(max ? parseDate(max) : undefined);
	const hintId = $derived(`${id}-format`);
	const parsedText = $derived(parseDisplayDate(text, locale));
	const invalid = $derived(Boolean(text && (!parsedText || (max && parsedText > max))));

	$effect(() => {
		// Preserve incomplete typing when the published ISO value is cleared.
		if (value !== previousValue || locale !== previousLocale) {
			text = value ? formatDateOnly(value, locale) : '';
			previousValue = value;
			previousLocale = locale;
		}
	});
	$effect(() => {
		input?.setCustomValidity(invalid ? m.date_invalid({ format: datePlaceholder(locale) }) : '');
	});

	function typeDate(event: Event): void {
		text = (event.currentTarget as HTMLInputElement).value;
		const parsed = parseDisplayDate(text, locale);
		const next = parsed && (!max || parsed <= max) ? parsed : '';
		previousValue = next;
		value = next;
	}

	function chooseDate(date: DateValue | undefined): void {
		if (!date) return;
		value = date.toString();
		text = formatDateOnly(value, locale);
		previousValue = value;
		open = false;
		input?.focus();
	}
</script>

<div class="flex min-w-0 gap-2">
	<Input
		bind:ref={input}
		{id}
		{required}
		value={text}
		placeholder={datePlaceholder(locale)}
		inputmode="numeric"
		autocomplete="bday"
		aria-invalid={invalid}
		aria-describedby={hintId}
		oninput={typeDate}
		onblur={() => {
			if (value) text = formatDateOnly(value, locale);
		}}
	/>
	<input type="hidden" {name} {value} />
	<Popover.Root bind:open>
		<Popover.Trigger>
			{#snippet child({ props })}
				<Button
					{...props}
					type="button"
					variant="outline"
					size="icon"
					class="shrink-0"
					aria-label={m.date_open_calendar()}><CalendarIcon aria-hidden="true" /></Button
				>
			{/snippet}
		</Popover.Trigger>
		<Popover.Content class="w-auto max-w-[calc(100vw-2rem)] p-0" align="end">
			<Calendar
				type="single"
				value={selected}
				onValueChange={chooseDate}
				maxValue={maximum}
				locale={dateLocale(locale)}
				captionLayout="dropdown"
				class="[--cell-size:--spacing(9)]"
				initialFocus
				labels={{
					previous: m.date_previous_month(),
					next: m.date_next_month(),
					month: m.date_choose_month(),
					year: m.date_choose_year()
				}}
			/>
		</Popover.Content>
	</Popover.Root>
</div>
<span id={hintId} class="sr-only">{datePlaceholder(locale)}</span>
