<script lang="ts" generics="TMessage extends MessageLike<any, any, any>">
	import type { MessageMarkupTag, MessageMetadata } from '@inlang/paraglide-js';
	import {
		ParaglideMessage,
		type MessageLike,
		type MessageOptions as ParaglideMessageOptions
	} from '@inlang/paraglide-js-svelte';
	import type { Snippet } from 'svelte';
	import { RICH_TEXT_TAGS } from './rich-text-tags.js';

	type RichTextTag = (typeof RICH_TEXT_TAGS)[number];
	type FixedMarkupSchema = Record<RichTextTag, MessageMarkupTag>;
	type MessageMetadataOf<T extends MessageLike<any, any, any>> =
		T extends MessageMetadata<infer TInputs, infer TOptions, infer TMarkup>
			? { inputs: TInputs; options: TOptions; markup: TMarkup }
			: never;
	type MessageInputs<T extends MessageLike<any, any, any>> =
		MessageMetadataOf<T> extends {
			inputs: infer TInputs;
		}
			? TInputs
			: Record<string, never>;
	type MessageOptions<T extends MessageLike<any, any, any>> =
		MessageMetadataOf<T> extends {
			options: infer TOptions;
		}
			? TOptions extends ParaglideMessageOptions
				? TOptions
				: ParaglideMessageOptions
			: ParaglideMessageOptions;
	type MarkupTagNames<T extends MessageLike<any, any, any>> =
		MessageMetadataOf<T> extends {
			markup: infer TMarkup;
		}
			? keyof TMarkup & string
			: never;
	type UnsupportedTagNames<T extends MessageLike<any, any, any>> = Exclude<
		MarkupTagNames<T>,
		RichTextTag
	>;
	type UnsupportedTagGuard<T extends MessageLike<any, any, any>> = [
		UnsupportedTagNames<T>
	] extends [never]
		? {}
		: {
				__unsupportedRichTextTags: `Add ${UnsupportedTagNames<T>} to RICH_TEXT_TAGS and RichText before using it in translations.`;
			};
	type MarkupProps = {
		children?: Snippet;
		options: Record<string, unknown>;
		attributes: Record<string, string | true>;
	};
	type InputsProp<TInputs> = keyof TInputs extends never
		? { inputs?: TInputs }
		: { inputs: TInputs };
	type Props<T extends MessageLike<any, any, any>> = {
		message: T;
		options?: MessageOptions<T>;
	} & InputsProp<MessageInputs<T>> &
		UnsupportedTagGuard<T> & {
			linkOverride?: Snippet<[MarkupProps]>;
			strongOverride?: Snippet<[MarkupProps]>;
			boldOverride?: Snippet<[MarkupProps]>;
			iconOverride?: Snippet<[MarkupProps]>;
		};

	let {
		message,
		inputs,
		options,
		linkOverride,
		strongOverride,
		boldOverride,
		iconOverride
	}: Props<TMessage> = $props();

	// The public props above preserve TMessage's exact schema. This adapter is
	// intentionally local: RichText owns every renderer in the fixed registry.
	const rendererMessage = $derived(message as MessageLike<any, any, FixedMarkupSchema>);

	function stringOption(options: Record<string, unknown>, name: string): string | undefined {
		const value = options[name];
		return typeof value === 'string' ? value : undefined;
	}
</script>

<ParaglideMessage
	message={rendererMessage}
	{inputs}
	options={options as ParaglideMessageOptions | undefined}
>
	{#snippet link(p)}
		{#if linkOverride}
			{@render linkOverride(p)}
		{:else}
			{@const href = stringOption(p.options, 'to')}
			{@const target = stringOption(p.options, 'target')}
			<a {href} {target}>{@render p.children?.()}</a>
		{/if}
	{/snippet}

	{#snippet strong(p)}
		{#if strongOverride}
			{@render strongOverride(p)}
		{:else}
			<strong>{@render p.children?.()}</strong>
		{/if}
	{/snippet}

	{#snippet bold(p)}
		{#if boldOverride}
			{@render boldOverride(p)}
		{:else}
			<b>{@render p.children?.()}</b>
		{/if}
	{/snippet}

	{#snippet icon(p)}
		{#if iconOverride}
			{@render iconOverride(p)}
		{:else}
			{@const name = stringOption(p.options, 'name')}
			<span aria-hidden="true" class={name ? `icon-${name}` : undefined}></span>
		{/if}
	{/snippet}
</ParaglideMessage>
