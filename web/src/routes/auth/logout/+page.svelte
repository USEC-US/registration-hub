<script lang="ts">
	import { resolve } from '$app/paths';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { authState } from '$lib/states/auth-state.svelte';
	import { onMount } from 'svelte';

	onMount(() => {
		authState.signOutAndRedirect(resolve(localizeInternalHref('/')));
	});
</script>

<svelte:head>
	<title>{m.nav_logout()} · {m.app_title()}</title>
</svelte:head>

<p class="mt-8 border border-(--line) bg-(--surface-muted) p-6 text-sm" role="status">
	{m.auth_signed_out_redirecting()}
</p>
