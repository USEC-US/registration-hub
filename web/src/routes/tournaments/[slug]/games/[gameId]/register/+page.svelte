<script lang="ts">
	import RegistrationWizard from '$lib/components/registrations/RegistrationWizard.svelte';
	import type { PageProps } from './$types';
	let { data }: PageProps = $props();
</script>

{#key `${data.tournament.id}:${data.game.id}`}
	<RegistrationWizard {data} />
{/key}
