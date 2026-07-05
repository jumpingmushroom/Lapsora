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
		let appendFailures = 0;

		// Keep only this many seconds of media behind the playhead. Without
		// eviction the SourceBuffer grows unbounded on a long-running live view
		// and eventually hits the MSE quota, freezing playback.
		const MAX_BUFFER_BEHIND = 30;

		function trimBuffer(): boolean {
			// Returns true if a remove() was started (its updateend will fire and
			// re-drive the queue). Never trims while the buffer is updating.
			if (!sourceBuffer || sourceBuffer.updating || !videoEl) return false;
			const buffered = sourceBuffer.buffered;
			if (buffered.length === 0) return false;
			const start = buffered.start(0);
			const target = videoEl.currentTime - MAX_BUFFER_BEHIND;
			if (target > start + 1) {
				try {
					sourceBuffer.remove(start, target);
					return true;
				} catch {
					return false;
				}
			}
			return false;
		}

		function appendNext() {
			if (!sourceBuffer || appending || queue.length === 0) return;
			if (sourceBuffer.updating) return;
			appending = true;
			const chunk = queue.shift()!;
			try {
				sourceBuffer.appendBuffer(chunk);
				appendFailures = 0;
			} catch {
				appending = false;
				appendFailures++;
				// A quota error should have been prevented by trimming; if appends
				// keep failing, surface it rather than freezing silently.
				if (appendFailures >= 5) {
					status = 'error';
					errorMsg = 'Live stream buffer error';
				}
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
									// Evict old media first; the remove() fires another
									// updateend that then drains the append queue.
									if (trimBuffer()) return;
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
				// Bound the buffer: if the SourceBuffer never initialized (e.g.
				// unsupported codec) or stalls, drop the oldest chunks instead of
				// growing without limit for the life of the socket.
				if (queue.length > 240) queue.splice(0, queue.length - 240);
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
