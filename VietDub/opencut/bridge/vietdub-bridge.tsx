"use client";

/**
 * Cầu nối VietDub -> OpenCut: mở /editor/<id>/?vietdub=<job> là tự nạp video (đã xóa phụ đề gốc),
 * giọng thuyết minh tiếng Việt và phụ đề Việt (thành chữ sửa được trên dòng thời gian).
 * Dữ liệu lấy từ máy chủ nhỏ của VietDub chạy trên chính máy này (127.0.0.1).
 */
import { useEffect } from "react";
import { toast } from "sonner";
import { useEditor } from "@/editor/use-editor";
import { importVietDubItems, type VietDubItem } from "./import";

type BridgeItem = VietDubItem;
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
				await importVietDubItems({ editor, projectId, items: manifest.items });
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
