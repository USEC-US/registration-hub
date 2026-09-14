<script lang="ts">
	import { page } from '$app/state';
	import RegistrationPaymentPage from '$lib/components/registrations/RegistrationPaymentPage.svelte';
</script>

{#key page.params.id}
	<RegistrationPaymentPage registrationId={Number(page.params.id)} />
{/key}
