<script lang="ts">
	import * as m from '$lib/paraglide/messages';

	interface Props {
		errors: readonly string[];
	}

	let { errors }: Props = $props();
</script>

{#if errors.length > 0}
	<section
		class="border-l-4 border-[var(--error)] bg-[var(--surface-muted)] px-4 py-3"
		role="alert"
	>
		<h2 class="text-base font-semibold text-[var(--error)]">{m.error_summary_title()}</h2>
		<ul class="mt-2 list-disc space-y-1 pl-5 text-sm">
			{#each errors as error, index (`${index}-${error}`)}
				<li>{error}</li>
			{/each}
		</ul>
	</section>
{/if}
