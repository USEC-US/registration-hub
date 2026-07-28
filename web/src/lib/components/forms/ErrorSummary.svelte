<script lang="ts">
	import * as Alert from '$lib/components/ui/alert';
	import * as m from '$lib/paraglide/messages';

	interface Props {
		errors: readonly string[];
	}

	let { errors }: Props = $props();
</script>

{#if errors.length > 0}
	<Alert.Root variant="destructive" role="alert">
		<Alert.Title role="heading" aria-level={2}>{m.error_summary_title()}</Alert.Title>
		<Alert.Description>
			<ul class="mt-2 ml-4 flex list-disc flex-col gap-1">
				{#each errors as error, index (`${index}-${error}`)}
					<li>{error}</li>
				{/each}
			</ul>
		</Alert.Description>
	</Alert.Root>
{/if}
