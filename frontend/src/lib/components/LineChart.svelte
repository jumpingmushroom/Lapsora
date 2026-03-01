<script lang="ts">
	import uPlot from 'uplot';
	import 'uplot/dist/uPlot.min.css';

	let {
		data,
		series,
		height = 300,
		xFormatter
	}: {
		data: uPlot.AlignedData;
		series: uPlot.Series[];
		height?: number;
		xFormatter?: (v: number) => string;
	} = $props();

	let container: HTMLDivElement;
	let chart: uPlot | null = null;

	$effect(() => {
		if (!container) return;

		const opts: uPlot.Options = {
			width: container.clientWidth,
			height,
			cursor: { show: true, drag: { x: false, y: false } },
			axes: [
				{
					stroke: '#6b7280',
					grid: { stroke: '#1f2937', width: 1 },
					ticks: { stroke: '#374151', width: 1 },
					values: xFormatter ? (_u: uPlot, vals: number[]) => vals.map(xFormatter) : undefined
				},
				{
					stroke: '#6b7280',
					grid: { stroke: '#1f2937', width: 1 },
					ticks: { stroke: '#374151', width: 1 },
					size: 60
				}
			],
			series: [
				{},
				...series
			]
		};

		chart?.destroy();
		chart = new uPlot(opts, data, container);

		const ro = new ResizeObserver(() => {
			chart?.setSize({ width: container.clientWidth, height });
		});
		ro.observe(container);

		return () => {
			ro.disconnect();
			chart?.destroy();
			chart = null;
		};
	});
</script>

<div bind:this={container} class="w-full"></div>
