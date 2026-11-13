"use client";

/**
 * Cầu nối VietDub -> OpenCut: mở /editor/<id>/?vietdub=<job> là tự nạp video (đã xóa phụ đề gốc),
 * giọng thuyết minh tiếng Việt và phụ đề Việt (thành chữ sửa được trên dòng thời gian).
 * Dữ liệu lấy từ máy chủ nhỏ của VietDub chạy trên chính máy này (127.0.0.1).
 */
import { useEffect } from "react";
import { toast } from "sonner";
import { useEditor } from "@/editor/use-editor";
import { processMediaAssets } from "@/media/processing";
import { buildElementFromMedia } from "@/timeline/element-utils";
import { AddMediaAssetCommand } from "@/commands/media";
import { InsertElementCommand } from "@/commands/timeline";
import { BatchCommand } from "@/commands";
import { DEFAULT_NEW_ELEMENT_DURATION } from "@/timeline/creation";
import { mediaTimeFromSeconds } from "@/wasm";
import { parseSubtitleFile } from "@/subtitles/parse";
import { insertCaptionChunksAsTextTrack } from "@/subtitles/insert";

type BridgeItem = {
	name: string;
	url: string;
	kind: "video" | "audio" | "image" | "subtitle";
};
type BridgeManifest = {
	job: string;
	title?: string;
	width?: number;
	height?: number;
	items: BridgeItem[];
};

const running = new Set<string>();

export function useVietDubBridge() {
	const editor = useEditor();
	const project = useEditor((e) => e.project.getActiveOrNull());
	const projectId = project?.metadata.id;

	useEffect(() => {
		if (!projectId) return;
		const job = new URLSearchParams(window.location.search).get("vietdub");
		if (!job) return;
		const key = `vietdub-${job}`;
		if (running.has(key) || window.localStorage.getItem(key)) return;
		running.add(key);

		(async () => {
			const toastId = toast.loading("Đang nạp video từ VietDub...");
			try {
				const res = await fetch(
					`/vietdub/manifest.json?job=${encodeURIComponent(job)}`,
					{ cache: "no-store" },
				);
				const manifest = (await res.json()) as BridgeManifest;
				if (!manifest || manifest.job !== job) {
					throw new Error("VietDub không còn mở dự án này - bấm lại nút trong VietDub.");
				}
				if (manifest.width && manifest.height) {
					await editor.project.updateSettings({
						settings: {
							canvasSize: { width: manifest.width, height: manifest.height },
							canvasSizeMode: "custom",
						},
						pushHistory: false,
					});
				}
				const files: File[] = [];
				for (const item of manifest.items.filter((x) => x.kind !== "subtitle")) {
					const blob = await (await fetch(item.url, { cache: "no-store" })).blob();
					files.push(new File([blob], item.name, { type: blob.type }));
				}
				const assets = await processMediaAssets({ files });
				for (const asset of assets) {
					const addMedia = new AddMediaAssetCommand({ projectId, asset });
					const duration =
						asset.duration != null
							? mediaTimeFromSeconds({ seconds: asset.duration })
							: DEFAULT_NEW_ELEMENT_DURATION;
					const element = buildElementFromMedia({
						mediaId: addMedia.getAssetId(),
						mediaType: asset.type,
						name: asset.name,
						duration,
						startTime: mediaTimeFromSeconds({ seconds: 0 }),
						buffer:
							asset.type === "audio"
								? new AudioBuffer({ length: 1, sampleRate: 44100 })
								: undefined,
					});
					const insert = new InsertElementCommand({
						element,
						placement: {
							mode: "auto",
							trackType: asset.type === "audio" ? "audio" : "video",
						},
					});
					editor.command.execute({ command: new BatchCommand([addMedia, insert]) });
				}
				for (const item of manifest.items.filter((x) => x.kind === "subtitle")) {
					const text = await (await fetch(item.url, { cache: "no-store" })).text();
					const { captions } = parseSubtitleFile({ fileName: item.name, input: text });
					insertCaptionChunksAsTextTrack({ editor, captions });
				}
				window.localStorage.setItem(key, "1");
				window.history.replaceState(null, "", window.location.pathname);
				await editor.project.saveCurrentProject();
				toast.success("Đã nạp video, thuyết minh và phụ đề từ VietDub", { id: toastId });
			} catch (error) {
				running.delete(key);
				toast.error("Không nạp được từ VietDub", {
					id: toastId,
					description: error instanceof Error ? error.message : String(error),
				});
			}
		})();
	}, [projectId, editor]);
}
