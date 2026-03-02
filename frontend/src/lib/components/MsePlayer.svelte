<script lang="ts">
	let { wsUrl }: { wsUrl: string } = $props();

	let videoEl = $state<HTMLVideoElement | null>(null);
	let status = $state<'connecting' | 'playing' | 'error'>('connecting');
	let errorMsg = $state('');

	$effect(() => {
		if (!videoEl || !wsUrl) return;

		status = 'connecting';
		errorMsg = '';

		const mediaSource = new MediaSource();
		const objectUrl = URL.createObjectURL(mediaSource);
		videoEl.src = objectUrl;

		let ws: WebSocket | null = null;
		let sourceBuffer: SourceBuffer | null = null;
		const queue: ArrayBuffer[] = [];
		let appending = false;

		function appendNext() {
			if (!sourceBuffer || appending || queue.length === 0) return;
			if (sourceBuffer.updating) return;
			appending = true;
			const chunk = queue.shift()!;
			try {
				sourceBuffer.appendBuffer(chunk);
			} catch {
				appending = false;
			}
		}

		mediaSource.addEventListener('sourceopen', () => {
			ws = new WebSocket(wsUrl);
			ws.binaryType = 'arraybuffer';

			ws.onmessage = (event) => {
				if (typeof event.data === 'string') {
					// First message from go2rtc is codec info as JSON
					try {
						const info = JSON.parse(event.data);
						const codecs = info.codecs || info.type;
						if (codecs && !sourceBuffer) {
							const mimeType = `video/mp4; codecs="${codecs}"`;
							if (MediaSource.isTypeSupported(mimeType)) {
								sourceBuffer = mediaSource.addSourceBuffer(mimeType);
								sourceBuffer.mode = 'segments';
								sourceBuffer.addEventListener('updateend', () => {
									appending = false;
									appendNext();
								});
							} else {
								status = 'error';
								errorMsg = `Unsupported codec: ${codecs}`;
							}
						}
					} catch {
						// Not JSON, ignore
					}
					return;
				}

				queue.push(event.data);
				appendNext();

				if (status !== 'playing' && videoEl) {
					videoEl.play().then(() => { status = 'playing'; }).catch(() => {});
				}
			};

			ws.onerror = () => {
				status = 'error';
				errorMsg = 'WebSocket connection failed';
			};

			ws.onclose = () => {
				if (status === 'connecting') {
					status = 'error';
					errorMsg = 'Connection closed';
				}
			};
		});

		return () => {
			ws?.close();
			if (videoEl) {
				videoEl.src = '';
			}
			URL.revokeObjectURL(objectUrl);
		};
	});
</script>

<div class="relative aspect-video w-full overflow-hidden rounded-lg bg-black">
	<!-- svelte-ignore a11y_media_has_caption -->
	<video
		bind:this={videoEl}
		autoplay
		muted
		playsinline
		class="h-full w-full object-contain"
	></video>
	{#if status === 'connecting'}
		<div class="absolute inset-0 flex items-center justify-center">
			<p class="text-sm text-gray-400">Connecting to live stream...</p>
		</div>
	{:else if status === 'error'}
		<div class="absolute inset-0 flex items-center justify-center">
			<p class="text-sm text-red-400">{errorMsg}</p>
		</div>
	{/if}
</div>
