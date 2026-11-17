/** (VietDub) Thêm file từ VietDub vào dự án OpenCut: video / âm thanh vào rãnh, phụ đề .srt thành chữ sửa được. */
import type { EditorCore } from "@/core";
import { processMediaAssets } from "@/media/processing";
import { buildElementFromMedia } from "@/timeline/element-utils";
import { AddMediaAssetCommand } from "@/commands/media";
import { InsertElementCommand } from "@/commands/timeline";
import { BatchCommand } from "@/commands";
import { DEFAULT_NEW_ELEMENT_DURATION } from "@/timeline/creation";
import { mediaTimeFromSeconds } from "@/wasm";
import { parseSubtitleFile } from "@/subtitles/parse";
import { insertCaptionChunksAsTextTrack } from "@/subtitles/insert";

export type VietDubItem = {
	name: string;
	url: string;
	kind: "video" | "audio" | "image" | "subtitle";
};

export const VD_HEADERS = { "X-VietDub": "1" };

export async function importVietDubItems({
	editor,
	projectId,
	items,
	startSeconds = 0,
}: {
	editor: EditorCore;
	projectId: string;
	items: VietDubItem[];
	startSeconds?: number;
}): Promise<void> {
	const files: File[] = [];
	for (const item of items.filter((x) => x.kind !== "subtitle")) {
		const res = await fetch(item.url, { cache: "no-store", headers: VD_HEADERS });
		if (!res.ok) throw new Error(`Không lấy được ${item.name}`);
		const blob = await res.blob();
		files.push(new File([blob], item.name, { type: blob.type }));
	}
	const assets = files.length ? await processMediaAssets({ files }) : [];
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
			startTime: mediaTimeFromSeconds({ seconds: startSeconds }),
			buffer:
				asset.type === "audio"
					? new AudioBuffer({ length: 1, sampleRate: 44100 })
					: undefined,
		});
		const insert = new InsertElementCommand({
			element,
			placement: { mode: "auto", trackType: asset.type === "audio" ? "audio" : "video" },
		});
		editor.command.execute({ command: new BatchCommand([addMedia, insert]) });
	}
	for (const item of items.filter((x) => x.kind === "subtitle")) {
		const res = await fetch(item.url, { cache: "no-store", headers: VD_HEADERS });
		const text = await res.text();
		const { captions } = parseSubtitleFile({ fileName: item.name, input: text });
		insertCaptionChunksAsTextTrack({
			editor,
			captions: captions.map((c) => ({ ...c, startTime: c.startTime + startSeconds })),
		});
	}
}
