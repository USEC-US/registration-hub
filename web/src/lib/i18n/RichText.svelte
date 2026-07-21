<script lang="ts">
  import { ParaglideMessage, type MessageLike } from "@inlang/paraglide-js-svelte";
  import type { Snippet } from "svelte";

  type MarkupProps = { children?: Snippet; options: Record<string, any>; attributes: Record<string, any> };

  let {
    message,
    inputs = {},
    linkOverride,
    strongOverride,
    boldOverride,
    iconOverride,
  }: {
    message: MessageLike;
    inputs?: Record<string, never>;
    linkOverride?: Snippet<[MarkupProps]>;
    strongOverride?: Snippet<[MarkupProps]>;
    boldOverride?: Snippet<[MarkupProps]>;
    iconOverride?: Snippet<[MarkupProps]>;
  } = $props();
</script>

<ParaglideMessage {message} {inputs}>
  {#snippet link(p)}
    {#if linkOverride}{@render linkOverride(p)}
    {:else}<a href={p.options.to} target={p.options.target}>{@render p.children?.()}</a>{/if}
  {/snippet}

  {#snippet strong(p)}
    {#if strongOverride}{@render strongOverride(p)}
    {:else}<strong>{@render p.children?.()}</strong>{/if}
  {/snippet}

  {#snippet bold(p)}
    {#if boldOverride}{@render boldOverride(p)}
    {:else}<b>{@render p.children?.()}</b>{/if}
  {/snippet}

  {#snippet icon(p)}
    {#if iconOverride}{@render iconOverride(p)}
    {:else}<span aria-hidden="true" class="icon-{p.options.name}"></span>{/if}
  {/snippet}
</ParaglideMessage>
